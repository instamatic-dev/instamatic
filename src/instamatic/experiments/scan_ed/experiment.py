from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from glob import glob
from itertools import count, cycle
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any

import pandas as pd

from instamatic.calibrate import CalibMovieDelays
from instamatic.calibrate.calibrate_stage_translation import *
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.experiments.fast_adt.experiment import FastADTMissingCalibError
from instamatic.experiments.scan_ed.artist import overlay_scan_hits
from instamatic.experiments.scan_ed.dispatch import DiffHuntDispatcher
from instamatic.experiments.scan_ed.journal import Journal
from instamatic.experiments.scan_ed.profile import ScanProfile
from instamatic.experiments.scan_ed.progress import ProgressTable
from instamatic.experiments.scan_ed.region import Regionalization
from instamatic.experiments.scan_ed.state import State
from instamatic.experiments.scan_ed.utils import SaveName
from instamatic.formats import read_tiff
from instamatic.grid.artist import plot_grid
from instamatic.grid.finder import GridFinder
from instamatic.grid.grid import GRID_REGISTRY
from instamatic.gui.click_dispatcher import ClickListener

if TYPE_CHECKING:
    from instamatic.gui import videostream_frame as vsf_type

SCAN_ED_MODE = Literal['start', 'continue', 'reprocess']


class Experiment(ExperimentBase):
    name = 'SPED'

    def __init__(
        self,
        ctrl,
        path: AnyPath,
        log: logging.Logger,
        flatfield: Optional[np.ndarray] = None,
        progress: Optional[ProgressTable] = None,
        mode: SCAN_ED_MODE = 'start',
        videostream_frame: Optional[vsf_type] = None,
        stop_event: Optional[Event] = None,
    ):
        super().__init__()
        self.ctrl = ctrl
        self.path: Path = Path(path)
        self.log: logging.Logger = log
        self.flatfield: Optional[np.ndarray] = flatfield
        self.progress: Optional[ProgressTable] = progress
        self.mode: SCAN_ED_MODE = mode
        self._state: Optional[State] = None
        self.start_time = datetime.now()
        self.videostream_frame: Optional[vsf_type] = videostream_frame
        self.stop_event: Optional[Event] = stop_event

        # attributes initialized once an experiment starts
        self.params: dict[str, Any] = {}
        self.dispatcher: Optional[DiffHuntDispatcher] = None
        self.grid_finder: Optional[GridFinder] = None
        self.reg: Optional[Regionalization] = None

    def initialize_state(self) -> None:
        """Initialize, fill a state if first access; raise at load issues."""
        journal_path = self.path / 'journal.jsonl'
        journal = Journal(path=journal_path)

        grid_yaml_path = journal.path.parent / 'grid.yaml'
        state = State(journal=journal, progress=self.progress)
        if self.mode in ('continue', 'reprocess'):
            grid = GridFinder.from_yaml(grid_yaml_path)
            if not journal_path.exists() or not journal_path.is_file():
                raise FileNotFoundError(f'No journal file found at {journal_path=}')
            state.load_from_journal(fill=self.mode == 'reprocess')
        else:
            grid_cls = GRID_REGISTRY[self.params.get('grid_geometry', 'square')]
            grid = grid_cls(0, 0, 0, 50_000, 50_000)

        self.grid_finder = GridFinder(grid)
        self.grid_finder.path = grid_yaml_path
        self._state = state

    @property
    def state(self) -> State:
        return self._state

    def get_dead_time(
        self,
        exposure: float = 0.0,
        header_keys_variable: tuple = (),
        header_keys_common: tuple = (),
    ) -> float:
        """Get time between get_movie frames from any source available or 0."""
        try:
            return self.ctrl.cam.dead_time
        except AttributeError:
            pass
        print('`cam.dead_time` not found. Looking for calibrated estimate...')
        try:
            c = CalibMovieDelays.from_file(exposure, header_keys_variable, header_keys_common)
        except RuntimeWarning:
            return 0.0
        else:
            return c.dead_time

    def get_dispatcher_live(self) -> DiffHuntDispatcher:
        """Start a multiprocessing helper once you have full access to cam."""
        i, _ = self.ctrl.get_image()
        return DiffHuntDispatcher(state=self.state, shape=i.shape, dtype=i.dtype)

    def get_dispatcher_from_file(self) -> DiffHuntDispatcher:
        """Start a multiprocessing helper using a sample frame on the disk."""
        sample_path = next((self.path / 'all').glob('*.tiff'))
        i, _ = read_tiff(str(sample_path))
        return DiffHuntDispatcher(state=self.state, shape=i.shape, dtype=i.dtype)

    def get_stage_translation(self) -> CalibStageMotion:
        """Get rotation calibration if present; otherwise warn & terminate."""
        try:
            if self.params['scan_geometry'].lower().startswith('x'):
                return CalibStageTranslationX.from_file()
            return CalibStageTranslationY.from_file()
        except OSError:
            print(m1 := 'This script requires stage rotation to be calibrated.')
            print(m2 := 'Please run `instamatic.calibrate_stage_rotation` first.')
            raise FastADTMissingCalibError(m1 + ' ' + m2)

    def determine_timing(self, step_size: int_nm) -> tuple[float, float, float]:
        """Determine exposure/reachable speed/total delay expected from TEM."""
        detector_dead_time = self.get_dead_time(self.params['scan_exposure'])
        time_for_one_frame = self.params['scan_exposure'] + detector_dead_time
        trans_calib = self.get_stage_translation()
        motion_plan = trans_calib.plan_motion(time_for_one_frame / step_size)
        exposure = abs(motion_plan.pace * step_size) - detector_dead_time
        return exposure, motion_plan.speed, motion_plan.total_delay

    def start_collection(self, **params) -> None:
        """Method that governs the entirety of scan ED experiment work flow."""

        # Save parameters to a variable, load the journal and dispatcher
        self.params = params
        self.initialize_state()
        if self.mode == 'reprocess':
            self.reprocess_collection()
            return
        if self.dispatcher is None:
            self.dispatcher = self.get_dispatcher_live()
        self.state.dispatcher = self.dispatcher
        self.state.configure_dispatcher(**params)

        # if allowed, add manually as many windows as the user desires.
        self.ctrl.stage.set(a=0)
        if not self.grid_finder.intercepts:
            method = self.params.get('grid_finding', 'All automatically')
            if method != 'All automatically':
                d = self.videostream_frame.click_dispatcher
                n = self.name
                cl: ClickListener = c if (c := d.listeners.get(n)) else d.add_listener(n)
                self.grid_finder.refine_by_manual_clicking(ctrl=self.ctrl, cl=cl)

        # Whenever any new window is added manually, draw it and then whole grid
        for window_idx in self.grid_finder.intercepts:
            self.draw_window_to_file(window_idx=window_idx)
        self.draw_grid_to_file()

        # Introduce the logic for grouping windows by regions
        rs = params.get('regionalization', '1 x 1')
        self.reg = Regionalization.from_str(grid=self.grid_finder.grid, shape=rs)

        # MAIN LOOP: define new region and request locating all windows in it
        try:
            for region_idx in count():
                windows_idx = list(self.reg.windows(region_idx=region_idx))
                if region_idx not in self.progress._region_totals:  # = was added
                    self.state.add_region(region_idx, windows_idx)
                for window_idx in windows_idx:
                    if window_idx not in self.grid_finder.intercepts:
                        try:
                            self.grid_finder.refine_by_auto_sweeping(
                                ctrl=self.ctrl,
                                window_idx=window_idx,
                                x_lim=self.params.get('target_x'),
                                y_lim=self.params.get('target_y'),
                            )
                        except IndexError:
                            continue  # break if no more windows are in limits
                        self.draw_window_to_file(window_idx=window_idx)
                        self.draw_grid_to_file()
                        if self.stop_event.is_set():
                            break

                # once region is located, add and run the scans over it
                if not self.state.has_any_scans(region_idx):
                    self.add_scans(region_idx=region_idx)
                for _, line_idx, scan_idx in self.state.untouched_scans(region=region_idx):
                    self.run_scan(region_idx, line_idx, scan_idx)
                    self.finalize_scan(region_idx, line_idx, scan_idx)
                    self.set_stop_event_if_target_met()
                    if self.stop_event.is_set():
                        break
                self.draw_hits_to_file()
        finally:
            self.ctrl.stage.wait()
            self.ctrl.stage.set(a=0)
            self.draw_hits_to_file()
        self.teardown()

    def add_scans(self, region_idx: int) -> None:
        """Add scans for window, asserting it does not have scans yet."""

        p = self.params
        windows_idx = self.reg.windows(region_idx=region_idx)
        windows = [self.grid_finder.grid.window(idx) for idx in windows_idx]

        if p['scan_geometry'].lower().startswith('x'):
            axis = 0
            step = p['scan_x_step']
            spacing = p['scan_y_step']
        else:  # params['scan_geometry'].lower().startswith('y'):
            axis = 1
            step = p['scan_y_step']
            spacing = p['scan_x_step']

        _, _, total_delay = self.determine_timing(step)
        error_margin = max(step * total_delay / p['scan_exposure'], 0)

        # prepare the limits to be scanned over the slow axis
        slow_min = np.min([w.corners[:, 1 - axis] for w in windows])
        slow_max = np.max([w.corners[:, 1 - axis] for w in windows])
        slows = np.arange(slow_min + spacing, slow_max, spacing, dtype=int)

        # Scan the region at every tilt, going along the same line each time
        for scan_id, tilt in enumerate(self.tilt_list()):
            scan_dirs = cycle([1] if 'raster' in p['scan_geometry'] else [1, -1])
            for line_id, slow in enumerate(slows):
                shared_id = {'region': int(region_idx), 'line': int(line_id)}
                scan_profile = ScanProfile(windows=windows, **{'xy'[axis]: slow})
                fast_min, fast_max = scan_profile.envelope(margin=error_margin)
                direction = next(scan_dirs)
                fast_start, fast_stop = [fast_min, fast_max][::direction]
                if tuple(shared_id.values()) not in self.state.lines.index:
                    self.state.add_line(
                        x0=int(slow if axis else fast_start),
                        y0=int(fast_start if axis else slow),
                        axis=int(axis),
                        step=int(step * direction),
                        n_steps=int(np.ceil(abs((fast_stop - fast_start) / step))),
                        **shared_id,
                    )
                self.state.add_scan(scan=int(scan_id), tilt=tilt, **shared_id)

    def draw_window_to_file(self, window_idx: int) -> None:
        """Use grid.artist.plot to draw window into its own file for debug."""
        file_path = self.path / 'windows' / f'window_{window_idx:04d}.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        intercepts = {window_idx: self.grid_finder.intercepts[window_idx]}
        fig, ax = plot_grid(self.grid_finder.grid, intercepts=intercepts)
        if not file_path.exists():  # don't overwrite previous img with _edge_xys
            fig.savefig(file_path)

    def draw_grid_to_file(self):
        """Use grid.artist.plot to draw grid into its own file for debug."""
        file_path = self.path / 'windows' / 'windows_all.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        fig, ax = plot_grid(
            self.grid_finder.grid,
            intercepts=self.grid_finder.intercepts,
            limit_x=self.params.get('target_x'),
            limit_y=self.params.get('target_y'),
        )
        fig.savefig(file_path)

    def draw_hits_to_file(self):
        """Overlay, save a heatmap of hits onto the plot of grid geometry."""
        file_path = self.path / 'windows' / 'heat_all.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        fig, ax = plot_grid(
            self.grid_finder.grid,
            intercepts=self.grid_finder.intercepts,
            limit_x=self.params.get('target_x'),
            limit_y=self.params.get('target_y'),
        )
        overlay_scan_hits(ax, self.state.lines, self.state.scans, self.state.steps)
        fig.savefig(file_path)

    def set_stop_event_if_target_met(self) -> None:
        th: Optional[int] = self.params.get('target_hits', None)
        tt: Optional[int] = self.params.get('target_time', None)
        hits_found = self.state.steps['hits'].sum()
        hits_target = th if th else float('inf')
        time_passed = datetime.now() - self.start_time
        time_target = timedelta(hours=tt) if tt else timedelta.max
        if time_passed > time_target or hits_found > hits_target:
            self.stop_event.set()

    def run_scan(self, region_idx: int, line_idx: int, scan_idx: int) -> None:
        """Run a single scan previously added to state on the grid."""
        idx = pd.IndexSlice[region_idx, line_idx, scan_idx, :]
        if np.any(self.state.steps.loc[idx, 'n_peaks'] != -1):
            return  # non-op for a scans that has been already done
        n_frames = int(self.state.lines.loc[(region_idx, line_idx), 'n_steps'])
        line = self.state.lines.loc[(region_idx, line_idx)]
        self.ctrl.stage.set(x=line['x0'], y=line['y0'])

        scan = self.state.scans.loc[(region_idx, line_idx, scan_idx)]
        if abs(self.ctrl.stage.a - scan['tilt']) > 0.05:  # epsilon:
            self.ctrl.stage.a = scan['tilt']

        name = str(SaveName().append(region_idx, line_idx, scan_idx))
        self.dispatcher.begin_scan(region_idx, line_idx, scan_idx, n_frames)

        exposure, speed, _ = self.determine_timing(line['step'])
        axis = line['axis']  # x: 0, y: 1
        fast0 = line['y0' if axis else 'x0']
        fast1 = fast0 + line['step'] * line['n_steps']
        setter_kwargs = {'xy'[axis]: fast1, 'speed': speed}
        self.ctrl.stage.set_with_speed(**setter_kwargs, wait=False)

        m = self.ctrl.get_movie(n_frames=n_frames, exposure=exposure, header_keys=None)
        # kw = {'region': region_idx, 'line': line_idx, 'scan': scan_idx}
        self.dispatcher.process_scan(m)
        self.ctrl.stage.wait()

        all_ = self.params.get('save_all', False)
        self.dispatcher.write_scan(path=self.path, all_=all_)
        self.dispatcher.end_scan()

    def finalize_scan(self, region_idx: int, line_idx: int, scan_idx: int) -> None:
        """Calculate scan offset, finalize it, save state to journal etc."""

        windows_idx = self.reg.windows(region_idx=region_idx)
        windows = [self.grid_finder.grid.window(idx) for idx in windows_idx]
        line = self.state.lines.loc[(region_idx, line_idx)]
        axis = 'xy'[line['axis']]
        fast0 = line['x0'] if axis == 'x' else line['y0']
        slow0 = line['y0'] if axis == 'x' else line['x0']
        scan_profile = ScanProfile(windows=windows, **{axis: slow0})

        fast = fast0 + (0.5 + np.arange(line['n_steps'])) * line['step']
        light = self.state.steps.loc[(region_idx, line_idx, scan_idx), 'light']
        offset, _ = scan_profile.fit(x=fast, light=light)

        self.state.finalize_scan(region_idx, line_idx, scan_idx, offset=offset)
        self.ctrl.stage.wait()

    def reprocess_collection(self) -> None:
        """Re-evaluate frames already saved in `all/` with current detection
        params, rewriting the journal's hit data and `tiff/`; Never drives the
        microscope and never resumes collection afterward."""

        if self.dispatcher is None:
            self.dispatcher = self.get_dispatcher_from_file()
        self.state.dispatcher = self.dispatcher
        self.state.configure_dispatcher(**self.params)

        rs = self.params.get('region_shape', '1x1')
        self.reg = Regionalization.from_str(grid=self.grid_finder.grid, shape=rs)

        shutil.rmtree(self.path / 'tiff', ignore_errors=True)

        for region_idx, line_idx, scan_idx in self.state.scans.index:
            self.reprocess_scan(region_idx, line_idx, scan_idx)
            if self.stop_event.is_set():
                break

        self.draw_hits_to_file()
        self.teardown()

    def reprocess_scan(self, region_idx, line_idx, scan_idx) -> None:
        """Re-run detection on one previously collected scan's saved frames."""

        n_frames = int(self.state.lines.loc[(region_idx, line_idx), 'n_steps'])
        name = str(SaveName().append(region_idx, line_idx, scan_idx))
        frame_paths = glob(str(self.path / 'all' / f'{name}*.tiff'))
        if not frame_paths:
            return

        self.dispatcher.begin_scan(region_idx, line_idx, scan_idx, n_frames)
        self.dispatcher.process_scan(frame_paths)
        self.dispatcher.write_scan(path=self.path, all_=True)
        self.dispatcher.end_scan()

        self.finalize_scan(region_idx, line_idx, scan_idx)

    def teardown(self) -> None:
        """Close all threads and safely shut down when requested."""
        self.dispatcher.terminate_workers()
        self.stop_event.clear()

    def tilt_list(self) -> Sequence[float]:
        """Return a list of tilts from - to + params[tilt_range] for scans."""
        tilt_extent = self.params.get('max_tilt', 0)
        tilt_count = np.round(2 * tilt_extent / 1).astype(int) + 1
        return np.linspace(-tilt_extent, tilt_extent, num=tilt_count, endpoint=True)

    def finalize(self) -> None:
        ...
        # TODO
