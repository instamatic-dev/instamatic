from __future__ import annotations

import time
from datetime import datetime, timedelta
from itertools import count, cycle, product
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Iterator

import numpy as np
import pandas as pd

from instamatic.calibrate import CalibMovieDelays
from instamatic.calibrate.calibrate_stage_translation import *
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.experiments.fast_adt.experiment import FastADTMissingCalibError
from instamatic.experiments.scan_ed.dispatch import DiffHuntDispatcher
from instamatic.experiments.scan_ed.journal import Journal
from instamatic.experiments.scan_ed.profile import ScanProfile
from instamatic.experiments.scan_ed.progress import ProgressTable
from instamatic.experiments.scan_ed.region import Regionalization
from instamatic.experiments.scan_ed.state import State
from instamatic.grid.artist import plot
from instamatic.grid.geometry import (
    GRID_REGISTRY,
    PeriodicConvexPolygonGridGeometry,
    WindowType,
)
from instamatic.grid.sweeping import star_sweep
from instamatic.gui.click_dispatcher import ClickListener, MouseButton

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

        # attributes initialized once an experiment starts
        self.params: dict[str, Any] = {}
        self.dispatcher: Optional[DiffHuntDispatcher] = None
        self.regionalization: Optional[Regionalization] = None

    def initialize_state(self) -> None:
        """Initialize, fill a state if first access; raise at load issues."""
        journal_path = self.path / 'journal.jsonl'
        journal = Journal(path=journal_path)
        grid = GRID_REGISTRY[self.params['grid_geometry']](0, 0, 0, 50_000, 50_000)
        state = State(journal=journal, grid=grid, progress=self.progress)
        if self.mode == 'continue':
            if not journal_path.exists() or not journal_path.is_file():
                raise FileNotFoundError(f'No journal file found at {journal_path=}')
            state.load_from_journal()
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

    def get_dispatcher(self) -> DiffHuntDispatcher:
        """Start a multiprocessing helper once you have full access to cam."""
        image, h = self.ctrl.get_image()
        return DiffHuntDispatcher(shape=image.shape, dtype=image.dtype)

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
        if self.dispatcher is None:
            self.dispatcher = self.get_dispatcher()
        self.state.configure_dispatcher(params=params)

        # if allowed, add manually as many windows as the user desires.
        self.ctrl.stage.set(a=0)
        if not self.state.intercepts:
            grid, intercepts = self.determine_grid_manually()
            self.state.update_grid(grid.to_params())
            for idx, idx_intercepts in intercepts.items():
                self.state.add_intercepts(idx, idx_intercepts)

        # Whenever any new window is added manually, draw it and then whole grid
        for window_idx in self.state.intercepts:
            self.draw_window_to_file(window_idx=window_idx)
        self.draw_grid_to_file()

        # Introduce the logic for grouping windows by regions
        rs = params.get('region_shape', '1x1')
        self.regionalization = Regionalization.from_str(grid=self.state.grid, shape=rs)

        # MAIN LOOP: define new region and request locating all windows in it
        try:
            for region_idx in count():
                windows_idx = list(self.regionalization.windows(region_idx=region_idx))
                self.state.add_region(region_idx, windows_idx)
                for window_idx in windows_idx:
                    if window_idx not in self.state.intercepts:
                        try:
                            _, intercepts = self.locate_window(window_idx)
                        except IndexError:
                            intercepts = np.zeros(shape=(0, 2), dtype=float)
                        self.state.add_intercepts(window_idx, intercepts)
                        self.state.grid.refine(intercepts=self.state.intercepts)
                        self.state.update_grid(self.state.grid.to_params())
                        self.draw_window_to_file(window_idx=window_idx)
                        self.draw_grid_to_file()
                        if params['stop_event'].is_set():
                            break

                # sanitation step: assert the current region is in limits
                if sum(self.state.intercepts[i].shape[0] for i in windows_idx) == 0:
                    continue  # should break if no more windows are in limits

                # once region is located, add and run the scans over it
                if not self.state.has_any_scans(region_idx):
                    self.add_scans(region_idx=region_idx)
                for _, line_idx, scan_idx in self.state.untouched_scans(region=region_idx):
                    self.run_scan(region_idx, line_idx, scan_idx)
                    self.finalize_scan(region_idx, line_idx, scan_idx)
                    self.set_stop_event_if_target_met()
                    if params['stop_event'].is_set():
                        break
                self.draw_hits_to_file()
        finally:
            self.ctrl.stage.set(a=0)
            self.draw_hits_to_file()
        self.teardown()

    def add_scans(self, region_idx: int) -> None:
        """Add scans for window, asserting it does not have scans yet."""

        p = self.params
        windows_idx = self.regionalization.windows(region_idx=region_idx)
        windows = [self.state.grid.window(idx) for idx in windows_idx]

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

    def determine_grid_manually(self) -> tuple[PeriodicConvexPolygonGridGeometry, dict]:
        grid = self.state.grid
        method = self.params.get('grid_finder', 'All automatically')
        if method == 'All automatically':
            return grid, {}

        d = self.videostream_frame.click_dispatcher
        n = self.name
        cl: ClickListener = c if (c := d.listeners.get(n)) else d.add_listener(n)

        print('Please navigate the stage to as many points on one windows edge as possible')
        print('(at least the corners and midpoints). At each point, position the edge at')
        print('the center of the screen and LMB to add the point. RMB to finish.')

        candidates: dict[int, np.ndarray] = {}
        intercepts: dict[int, np.ndarray] = {}
        window_idx: int = 0
        while True:
            edge_xys = []
            with cl:
                while True:
                    c = cl.get_click()
                    if c.button == MouseButton.RIGHT:
                        break
                    edge_xys.append(self.ctrl.stage.xy)
            edge_xys = np.asarray(edge_xys, dtype=float)

            if 0 in intercepts:
                new_center = (np.max(edge_xys, axis=0) - np.min(edge_xys, axis=0)) / 2
                window_idx = grid.nearest_index(*new_center)
                print(f'Adding another window: estimated index {window_idx}')
                if window_idx in candidates:
                    print(f'Warning: window {window_idx} was already added! Overwriting...')
            candidates[window_idx] = np.asarray(edge_xys, dtype=float)

            grid = grid.guess(candidates)
            grid.refine(candidates)
            fig, ax = plot(grid, show_intercepts=True)
            with self.videostream_frame.processor.temporary(figure=fig), cl:
                print('LMB to accept and finish, RMB to retry, MMB to accept and new window')
                c = cl.get_click()
                if c.button == MouseButton.LEFT:
                    intercepts[window_idx] = candidates[window_idx]
                    return grid, intercepts
                elif c.button == MouseButton.RIGHT:
                    continue
                else:  # middle or any other
                    intercepts[window_idx] = candidates[window_idx]
                    continue

    def locate_window(self, idx: int = -1) -> tuple[int, np.ndarray]:
        """Find intersects with a next window, raise if no window be found."""
        if self.params.get('grid_finder') == 'All manually':
            raise IndexError('Experiment params disallow locating new windows')
        if not self.state.intercepts:
            return 0, star_sweep(arms=3, order=4)

        x_lim = tx if (tx := self.params['target_x']) is not None else 1_000_000
        y_lim = ty if (ty := self.params['target_y']) is not None else 1_000_000

        in_limits = self.state.grid.windows_in_limits(x=x_lim, y=y_lim)
        if idx == -1:
            try:
                idx = min([i for i in in_limits if i not in self.state.intercepts])
            except ValueError:
                raise IndexError('Could not locate next window within limits')
        else:
            if idx not in in_limits:
                raise IndexError(f'Requested window {idx} is not within limits')

        self.ctrl.stage.set(*[int(xy) for xy in self.state.grid.window(idx).center])
        return idx, star_sweep(arms=3, order=2, offset=11 * idx)

    def draw_window_to_file(self, window_idx: int) -> None:
        """Use grid.artist.plot to draw window into its own file for debug."""
        file_path = self.path / 'windows' / f'window_{window_idx:04d}.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        intercepts = {window_idx: self.state.intercepts[window_idx]}
        fig, ax = plot(self.state.grid, intercepts=intercepts, show_intercepts=True)
        if not file_path.exists():  # don't overwrite previous img with _edge_xys
            fig.savefig(file_path)

    def draw_grid_to_file(self):
        """Use grid.artist.plot to draw grid into its own file for debug."""
        file_path = self.path / 'windows' / 'windows_all.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        fig, ax = plot(self.state.grid, intercepts=self.state.intercepts)
        fig.savefig(file_path)

    def draw_hits_to_file(self):
        """Overlay, save a heatmap of hits onto the plot of grid geometry."""
        file_path = self.path / 'windows' / 'heat_all.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        fig, ax = plot(
            self.state.grid,
            lines=self.state.lines,
            scans=self.state.scans,
            steps=self.state.steps,
            figsize=(10, 10),
        )
        fig.savefig(file_path)

    def set_stop_event_if_target_met(self) -> None:
        th: Optional[int] = self.params.get('target_hits', None)
        tt: Optional[int] = self.params.get('target_time', None)
        hits_found = self.state.steps['hits'].sum()
        hits_target = th if th else float('inf')
        time_passed = datetime.now() - self.start_time
        time_target = timedelta(hours=tt) if tt else timedelta.max
        if time_passed > time_target or hits_found > hits_target:
            self.params['stop_event'].set()

    def run_scan(self, region_idx: int, line_idx: int, scan_idx: int) -> None:
        """Run a single scan previously added to state on the grid."""

        idx = pd.IndexSlice[region_idx, line_idx, scan_idx, :]
        if np.any(self.state.steps.loc[idx, 'n_peaks'] != -1):
            return  # none-op for a scans that has been already done
        n_frames = int(self.state.lines.loc[(region_idx, line_idx), 'n_steps'])

        line = self.state.lines.loc[(region_idx, line_idx)]
        self.ctrl.stage.set(x=line['x0'], y=line['y0'])

        scan = self.state.scans.loc[(region_idx, line_idx, scan_idx)]
        if abs(self.ctrl.stage.a - scan['tilt']) > 0.05:  # epsilon:
            self.ctrl.stage.a = scan['tilt']

        name = f'r{region_idx:03d}_l{line_idx:06d}_s{scan_idx:03d}'
        self.dispatcher.begin_scan(n_frames, name=name)
        kw = {'state': self.state, 'region': region_idx, 'line': line_idx, 'scan': scan_idx}
        fb_thread = Thread(target=self.dispatcher.handle_feedback, kwargs=kw)
        fb_thread.start()

        exposure, speed, _ = self.determine_timing(line['step'])  # loc of 'step' does not work
        axis = line['axis']  # x: 0, y: 1
        fast0 = line['y0' if axis else 'x0']
        fast1 = fast0 + line['step'] * line['n_steps']
        setter_kwargs = {'xy'[axis]: fast1, 'speed': speed}
        self.ctrl.stage.set_with_speed(**setter_kwargs, wait=False)

        movie = self.ctrl.get_movie(n_frames=n_frames, exposure=exposure, header_keys=None)
        for frame, header in movie:
            self.dispatcher.process(frame, header)
        self.dispatcher.scan_finished.set()  # signals no more data is coming
        self.dispatcher.scan_processed.wait(timeout=60)  # should process live
        self.ctrl.stage.wait()

        self.dispatcher.write_scan(path=self.path, all_=self.params.get('save_all', False))
        self.dispatcher.handle_feedback(self.state, region_idx, line_idx, scan_idx)
        self.dispatcher.end_scan()

    def finalize_scan(self, region_idx: int, line_idx: int, scan_idx: int) -> None:
        """Calculate scan offset, finalize it, save state to journal etc."""

        windows_idx = self.regionalization.windows(region_idx=region_idx)
        windows = [self.state.grid.window(idx) for idx in windows_idx]
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

    def teardown(self) -> None:
        """Close all threads and safely shut down when requested."""
        self.dispatcher.terminate_workers()
        self.params['stop_event'].clear()

    def tilt_list(self) -> Sequence[float]:
        """Return a list of tilts from - to + params[tilt_range] for scans."""
        tilt_extent = self.params.get('tilt_extent', 0)
        tilt_step = self.params.get('tilt_step', 1)
        tilt_count = np.round(2 * tilt_extent / tilt_step).astype(int) + 1
        return np.linspace(-tilt_extent, tilt_extent, num=tilt_count, endpoint=True)

    def finalize(self) -> None:
        ...
        # TODO


# TODO: something tries adding a window at every load
# Exception in Tkinter callback
# Traceback (most recent call last):
#   File "C:\Program Files\Instamatic\Python312\Lib\tkinter\__init__.py", line 1968, in __call__
#     return self.func(*args)
#            ^^^^^^^^^^^^^^^^
#   File "C:\Program Files\Instamatic\Python312\Lib\tkinter\__init__.py", line 862, in callit
#     func(*args)
#   File "C:\Program Files\Instamatic\instamatic\src\instamatic\experiments\scan_ed\progress.py", line 261, in _drain
#     getattr(self._target, name)(*args, **kwargs)
#   File "C:\Program Files\Instamatic\instamatic\src\instamatic\experiments\scan_ed\progress.py", line 88, in add_region
#     self.tree.insert('', tk.END, iid=region_iid, text=region_name, values=values)
#   File "C:\Program Files\Instamatic\Python312\Lib\tkinter\ttk.py", line 1339, in insert
#     res = self.tk.call(self._w, "insert", parent, index,
#           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# _tkinter.TclError: Item r:0 already exists
