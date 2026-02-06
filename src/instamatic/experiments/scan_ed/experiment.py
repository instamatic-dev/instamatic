from __future__ import annotations

from datetime import datetime, timedelta
from itertools import count, cycle
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from instamatic.calibrate import CalibMovieDelays
from instamatic.calibrate.calibrate_stage_translation import *
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.experiments.fast_adt.experiment import FastADTMissingCalibError
from instamatic.experiments.scan_ed.dispatch import DiffHuntDispatcher
from instamatic.experiments.scan_ed.journal import Journal
from instamatic.experiments.scan_ed.progress import ProgressTable
from instamatic.experiments.scan_ed.state import State
from instamatic.grid.artist import plot
from instamatic.grid.registry import GRID_REGISTRY, PeriodicConvexPolygonGrid
from instamatic.grid.window import GridablePolygonWindow
from instamatic.gui.click_dispatcher import ClickListener, MouseButton

if TYPE_CHECKING:
    from instamatic.gui import videostream_frame as vsf_type


class Experiment(ExperimentBase):
    name = 'SPED'

    def __init__(
        self,
        ctrl,
        path: AnyPath,
        log: logging.Logger,
        flatfield: Optional[np.ndarray] = None,
        progress: Optional[ProgressTable] = None,
        load: bool = False,
        videostream_frame: Optional[vsf_type] = None,
    ):
        super().__init__()
        self.ctrl = ctrl
        self.path: Path = Path(path)
        self.log: logging.Logger = log
        self.flatfield: Optional[np.ndarray] = flatfield
        self.progress: Optional[ProgressTable] = progress
        self.load: bool = load
        self._state: Optional[State] = None
        self.start_time = datetime.now()
        self.videostream_frame: Optional[vsf_type] = videostream_frame

        # attributes initialized once an experiment starts
        self.params: dict[str, Any] = {}
        self.dispatcher: Optional[DiffHuntDispatcher] = None

    @property
    def state(self) -> State:
        """Initialize, fill a state if first access; raise at load issues."""
        if self._state is not None:
            return self._state
        journal_path = self.path / 'journal.jsonl'
        journal = Journal(path=journal_path)
        grid = GRID_REGISTRY[self.params['grid_geometry']]()
        state = State(journal=journal, grid=grid, progress=self.progress)
        if self.load:
            if not journal_path.exists() or not journal_path.is_file():
                raise FileNotFoundError(f'No journal file found at {journal_path=}')
            state.load_from_journal()
        self._state = state
        return state

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

        self.params = params
        _ = self.state  # loads the journal
        if self.dispatcher is None:
            self.dispatcher = self.get_dispatcher()

        # windows are only added if no defined; TODO: allow adding after loading
        self.ctrl.stage.set(a=0)
        if not self.state.grid.windows:
            windows = self.determine_manual_windows()
            self.order_and_add_manual_windows(windows)
        for window_idx, window in self.state.grid.windows.items():
            self.draw_window_to_file(window_idx=window_idx, window=window)

        while not params['stop_event'].is_set():
            try:
                for window_idx in self.state.grid.windows.keys():
                    if not self.state.has_any_scans(window_idx):
                        self.add_scans(window_idx=window_idx, params=params)
                    for _, scan_idx in self.state.untouched_scans(window=window_idx):
                        self.set_tilt(window_idx)
                        self.run_scan(window_idx, scan_idx)
                        self.set_stop_event_if_target_met()
                        if params['stop_event'].is_set():
                            break
            finally:
                self.ctrl.stage.set(a=0)
            if params['stop_event'].is_set():
                break
            try:
                window_idx, window = self.locate_next_window()
            except IndexError:
                params['stop_event'].set()
                break
            self.state.add_window(idx=window_idx, window=window)
            self.draw_window_to_file(window_idx=window_idx, window=window)

        self.teardown()

    def add_scans(self, window_idx: int, params: dict[str, Any]) -> None:
        """Add scans for window, asserting it does not have scans yet."""

        window = self.state.grid.windows[window_idx]
        if params['scan_geometry'].lower().startswith('x'):
            axis = 0
            scan_factory = window.x_intersections
            step = params['scan_x_step']
            spacing = params['scan_y_step']
        else:  # params['scan_geometry'].lower().startswith('y'):
            axis = 1
            scan_factory = window.y_intersections
            step = params['scan_y_step']
            spacing = params['scan_x_step']

        _, _, total_delay = self.determine_timing(step)
        error_margin = max(step * total_delay / self.params['scan_exposure'], 0)

        scan_dirs = cycle([1] if 'raster' in params['scan_geometry'] else [1, -1])
        slow_min = np.min(window.corners[:, 1 - axis])
        slow_max = np.max(window.corners[:, 1 - axis])
        slows = np.arange(slow_min + spacing, slow_max, spacing, dtype=int)
        for scan_id, slow in enumerate(slows):
            fast_min, fast_max = scan_factory(slow)
            fast_min -= error_margin
            fast_max += error_margin
            fast_start, fast_stop = [fast_min, fast_max][:: next(scan_dirs)]
            step = step if fast_stop > fast_start else -step
            self.state.add_scan(
                window=int(window_idx),
                scan=int(scan_id),
                x0=int(slow if axis else fast_start),
                y0=int(fast_start if axis else slow),
                axis=int(axis),
                step=int(step),
                n_steps=int(np.ceil(abs((fast_stop - fast_start) / step))),
            )

    def determine_manual_windows(self) -> list[GridablePolygonWindow]:
        method = self.params.get('grid_finder', 'All automatically')
        if method == 'All automatically':
            return []

        d = self.videostream_frame.click_dispatcher
        n = self.name
        cl: ClickListener = c if (c := d.listeners.get(n)) else d.add_listener(n)

        print('Please navigate the stage to as many points on the windows edge as possible')
        print('(at least the corners and midpoints). At each point, position the edge at')
        print('the center of the screen and LMB to add the point. RMB to finish.')

        windows = {}
        for window_idx in count():
            edge_xys = []
            with cl:
                while True:
                    c = cl.get_click()
                    if c.button == MouseButton.RIGHT:
                        break
                    edge_xys.append(self.ctrl.stage.xy)
            edge_xys = np.asarray(edge_xys, dtype=float)
            window = self.state.grid.window_type.from_edge_xys(edge_xys=edge_xys)
            fig, ax = plot({**windows, window_idx: window}, debug_edges=True)
            with self.videostream_frame.processor.temporary(figure=fig):
                print('LMB to accept and finish, RMB to retry, MMB to accept and add new')
                c = cl.get_click()
                if c.button == MouseButton.LEFT:
                    windows[window_idx] = window
                    return list(windows.values())
                elif c.button == MouseButton.RIGHT:
                    continue
                else:  # middle or any other
                    windows[window_idx] = window
                    continue

    def order_and_add_manual_windows(self, windows: list[GridablePolygonWindow]) -> None:
        """Based on the first, correctly reindex+add the following windows."""
        if not windows:
            return
        self.state.add_window(idx=0, window=windows.pop(0))
        for window in windows:
            idx = self.state.grid.predict_index(window.center)
            self.state.add_window(idx=idx, window=window)

    def locate_next_window(self) -> tuple[int, GridablePolygonWindow]:
        """Find a next window on the grid, or raise if none can be found."""
        if self.params.get('grid_finder') == 'All manually':
            raise IndexError('Experiment params disallow locating new windows')
        grid: PeriodicConvexPolygonGrid[GridablePolygonWindow] = self.state.grid
        if not self.state.grid.windows:
            return 0, grid.window_type.from_sweeping()
        max_index = 10 + 2 * (max(grid.windows) if grid.windows else 0)
        for window_id in range(0, max_index):
            if window_id in grid.windows:
                continue
            predicted = grid.predict_window(window_id)
            x_lim = tx if (tx := self.params['target_x']) is not None else float('inf')
            y_lim = ty if (ty := self.params['target_y']) is not None else float('inf')
            x_fits = np.all(np.abs(predicted.corners[:, 0]) < x_lim)
            y_fits = np.all(np.abs(predicted.corners[:, 1]) < y_lim)
            if not (x_fits and y_fits):
                continue
            self.ctrl.stage.set(*[int(xy) for xy in predicted.center])
            return window_id, grid.window_type.from_sweeping()
        raise IndexError('Could not locate next window within limits')

    def draw_window_to_file(self, window_idx: int, window: GridablePolygonWindow) -> None:
        """Use grid.artist.plot to draw window into its own file for debug."""
        file_path = self.path / 'windows' / f'window_{window_idx:04d}.png'
        file_path.parent.mkdir(exist_ok=True, parents=True)
        fig, ax = plot({window_idx: window}, debug_edges=True)
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

    def set_tilt(self, window_idx: int) -> None:
        """Set alpha (0 to +/-max to 0) as a function of window progress."""
        p = self.state.window_progress(window=window_idx)
        m = self.params['max_alpha']
        a = m * 2 * p if p <= 0.5 else m * (2 * p - 2)  # 0 to m, then -m to 0
        self.ctrl.stage.set(a=a)

    def run_scan(self, window_idx: int, scan_idx: int) -> None:
        """Run a single scan previously added to state on the grid."""

        idx = pd.IndexSlice[window_idx, scan_idx, :]
        if np.any(self.state.steps.loc[idx, 'n_peaks'] != -1):
            return  # none-op for a scans that has been already done
        n_frames = int(self.state.scans.loc[(window_idx, scan_idx), 'n_steps'])

        scan = self.state.scans.loc[(window_idx, scan_idx)]
        self.ctrl.stage.set(x=scan['x0'], y=scan['y0'])

        self.dispatcher.begin_scan(n_frames)
        fb_kwargs = {'state': self.state, 'window': window_idx, 'scan': scan_idx}
        fb_thread = Thread(target=self.dispatcher.handle_feedback, kwargs=fb_kwargs)
        fb_thread.start()

        exposure, speed, _ = self.determine_timing(scan['step'])
        axis = scan['axis']  # x: 0, y: 1
        fast0 = scan['y0' if axis else 'x0']
        fast1 = fast0 + scan['step'] * scan['n_steps']
        setter_kwargs = {'xy'[axis]: fast1, 'speed': speed}
        self.ctrl.stage.set_with_speed(**setter_kwargs)

        movie = self.ctrl.get_movie(n_frames=n_frames, exposure=exposure, header_keys=None)
        for frame, header in movie:
            self.dispatcher.process(frame, header)
        self.dispatcher.scan_finished.set()  # signals no more data is coming
        self.dispatcher.scan_processed.wait(timeout=60)  # should process live
        fb_thread.join()

        self.dispatcher.write_scan(path=self.path / 'tiff')
        self.dispatcher.handle_feedback(self.state, window_idx, scan_idx)
        self.dispatcher.end_scan()
        self.state.finalize_scan(window_idx, scan_idx)

    def teardown(self) -> None:
        """Close all threads and safely shut down when requested."""
        self.dispatcher.terminate_workers()
        self.params['stop_event'].clear()

    def finalize(self) -> None:
        ...
        # TODO
