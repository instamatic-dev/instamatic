from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import count, cycle
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import pandas as pd

from instamatic._typing import AnyPath, int_nm
from instamatic.calibrate import CalibMovieDelays
from instamatic.calibrate.calibrate_stage_translation import CalibStageTranslationX
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
        self.state = self.get_state(load=load, progress=progress)
        self.start_time = datetime.now()
        self.videostream_frame: Optional[vsf_type] = videostream_frame

        # attributes initialized once an experiment starts
        self.params: dict[str, Any] = {}
        self.dispatcher: Optional[DiffHuntDispatcher] = None

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

    def get_stage_translation(self) -> CalibStageTranslationX:
        """Get rotation calibration if present; otherwise warn & terminate."""
        try:
            return CalibStageTranslationX.from_file()
        except OSError:
            print(m1 := 'This script requires stage rotation to be calibrated.')
            print(m2 := 'Please run `instamatic.calibrate_stage_rotation` first.')
            raise FastADTMissingCalibError(m1 + ' ' + m2)

    def get_state(self, load: bool, progress: Optional[ProgressTable] = None) -> State:
        """Initialize a state, fill it from journal; raise at load issues."""
        journal_path = self.path / 'journal.jsonl'
        journal = Journal(path=journal_path)
        grid = GRID_REGISTRY[self.params['grid_geometry']]()
        state = State(journal=journal, grid=grid, progress=progress)
        if load:
            if not journal_path.exists() or not journal_path.is_file():
                raise FileNotFoundError(f'No journal file found at {journal_path=}')
            state.load_from_journal()
        return state

    def determine_exposure_and_speed(self, step_size: int_nm) -> tuple[float, float]:
        """Determine exposure/speed reachable by TEM close to requested."""
        detector_dead_time = self.get_dead_time(self.params['exposure'])
        time_for_one_frame = self.params['exposure'] + detector_dead_time
        trans_calib = self.get_stage_translation()
        motion_plan = trans_calib.plan_motion(time_for_one_frame / step_size)
        exposure = abs(motion_plan.pace * step_size) - detector_dead_time
        return exposure, motion_plan.speed

    def start_collection(self, **params) -> None:
        """Method that governs the entirety of scan ED experiment work flow."""

        self.params = params
        if self.dispatcher is None:
            self.dispatcher = self.get_dispatcher()

        windows = self.determine_manual_windows()
        self.order_and_add_manual_windows(windows)

        while not params['stop_event'].is_set():
            for window_idx in self.state.grid.windows.keys():
                for _, scan_idx in self.state.untouched_scans(window=window_idx):
                    self.set_tilt(window_idx)
                    self.run_scan(window_idx, scan_idx)
                    self.set_stop_event_if_target_met()
                    if params['stop_event'].is_set():
                        break
            try:
                window_idx, window = self.locate_next_window()
            except IndexError:
                params['stop_event'].set()
                break
            self.state.add_window(idx=window_idx, window=window)
            self.add_scans(window_idx=window_idx, params=params)

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

        if params['scan_geometry'].lower().endswith('raster'):
            scan_signs = cycle([1, -1])
        else:  # params['scan_geometry'].lower().endswith('raster'):
            scan_signs = cycle([1])

        slow_min = np.min(window.corners[:, 1 - axis])
        slow_max = np.max(window.corners[:, 1 - axis])
        slows = np.arange(slow_min + spacing, slow_max, spacing, dtype=int)
        for scan_id, slow in enumerate(slows):
            fast_min, fast_max = scan_factory(slow)[:: next(scan_signs)]
            self.state.add_scan(
                window=window_idx,
                scan_id=scan_id,
                x0=slow_min if axis else fast_min,
                y0=fast_min if axis else slow_min,
                axis=axis,
                step=step,
                n_steps=-(-abs(fast_max - fast_min) % step),
            )

    def determine_manual_windows(self) -> list[GridablePolygonWindow]:
        method = self.params.get('grid_finder', 'All automatically')
        if method == 'All automatically':
            return []

        d = self.videostream_frame.click_dispatcher
        n = self.name
        cl: ClickListener = c if (c := d.listeners.get(n)) else d.add_listener(n)

        print('Please navigate the stage as many points on the edge as possible')
        print('(at least the corners and approximate midpoints). At each point,')
        print('position the edge at the center of the screen.')
        print('Left-click the screen to add the point, right-click to finish.')
        print('')

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
            window = self.state.grid.window_type.from_edge_xys(edge_xy=edge_xys)
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
        for window_id in range(1, 2 * max(grid.windows) + 10):
            if window_id in grid.windows:
                continue
            predicted = grid.predict_window(window_id)
            x_lim = tx if (tx := self.params['target_x']) is not None else float('inf')
            y_lim = ty if (ty := self.params['target_x']) is not None else float('inf')
            x_fits = np.all(np.abs(predicted.corners[:, 0]) < x_lim)
            y_fits = np.all(np.abs(predicted.corners[:, 0]) < y_lim)
            if not (x_fits and y_fits):
                continue
            self.ctrl.stage.set(*[int(xy) for xy in predicted.center])
            return window_id, grid.window_type.from_sweeping()
        raise IndexError('Could not locate next window within limits')

    def set_stop_event_if_target_met(self) -> None:
        time_passed = datetime.now() - self.start_time
        time_target = timedelta(hours=self.params['target_time'])
        hits_found = self.state.steps['hits'].sum()
        hits_target = self.params['target_hits']
        if time_passed > time_target or hits_found > hits_target:
            self.params['stop_event'].set()

    def set_tilt(self, window_idx: int) -> None:
        """Set alpha (0 to +/-max to 0) as a function of window progress."""
        p = self.state.window_progress(window=window_idx)
        m = self.params['max_alpha']
        a = m * 2 * p if p <= 0.5 else m * (2 * p - 1)  # 0 to m, then -m to 0
        self.ctrl.stage.set(a=a)

    def run_scan(self, window_idx: int, scan_idx: int) -> None:
        """Run a single scan previously added to state on the grid."""

        idx = pd.IndexSlice[window_idx, scan_idx, :]
        if np.any(self.state.steps.loc[idx, 'n_peaks'] != -1):
            return  # none-op for a scans that has been already done

        scan = self.state.scans.loc[(window_idx, scan_idx)]
        self.ctrl.stage.set(x0=scan['x0'], y0=scan['y0'])

        self.dispatcher.begin_scan(len(idx))
        fb_kwargs = {'state': self.state, 'window': window_idx, 'scan': scan_idx}
        fb_thread = Thread(target=self.dispatcher.handle_feedback, kwargs=fb_kwargs)
        fb_thread.start()

        exposure, speed = self.determine_exposure_and_speed(scan['step'])
        axis = scan['axis']  # x: 0, y: 1
        fast0 = scan['y0' if axis else 'x0']
        fast1 = fast0 + scan['step'] * scan['n_steps']
        setter_kwargs = {'xy'[axis]: fast1, 'speed': speed}
        self.ctrl.stage.set_with_speed(**setter_kwargs)

        movie = self.ctrl.get_movie(n_frames=len(idx), exposure=exposure, header_keys=None)
        for frame, header in movie:
            self.dispatcher.process(frame, header)
        self.dispatcher.scan_processed.wait(timeout=60)  # should process live

        self.dispatcher.write_scan(path=self.path / 'tiff')
        self.dispatcher.end_scan()
        fb_thread.join()
        self.state.finalize_scan(window_idx, scan_idx)

    def teardown(self) -> None:
        """Close all threads and safely shut down when requested."""
        self.dispatcher.terminate_workers()

    def finalize(self) -> None:
        ...
        # TODO
