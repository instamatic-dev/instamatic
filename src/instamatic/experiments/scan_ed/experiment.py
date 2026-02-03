from __future__ import annotations

import logging
from itertools import cycle
from pathlib import Path
from threading import Thread
from typing import Any, Optional

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
from instamatic.grid.registry import GRID_REGISTRY, PeriodicConvexPolygonGrid
from instamatic.grid.window import GridablePolygonWindow


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
    ):
        super().__init__()
        self.ctrl = ctrl
        self.path: Path = Path(path)
        self.log: logging.Logger = log
        self.flatfield: Optional[np.ndarray] = flatfield
        self.state = self.get_state(load=load, progress=progress)

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

        while not params['stop_event'].is_set():
            try:
                window_idx, window = self.locate_next_window()
            except IndexError:
                break
            self.state.add_window(idx=window_idx, window=window)
            self.add_scans(window_idx=window_idx, params=params)
            for scan_idx in self.state.scans.loc[window_idx].index:
                if self.dispatcher is None:
                    self.dispatcher = self.get_dispatcher()
                self.run_scan(window_idx, scan_idx)

    def locate_next_window(self) -> tuple[int, GridablePolygonWindow]:
        """Find a next window on the grid, or raise if none can be found."""
        grid: PeriodicConvexPolygonGrid[GridablePolygonWindow] = self.state.grid
        last_window_id = max(grid.windows)
        for window_id in range(last_window_id + 1, 2 * last_window_id + 10):
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
