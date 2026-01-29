from __future__ import annotations

from typing import Callable, Optional, Sequence, Union

import numpy as np
import pandas as pd

from instamatic.experiments.scan_ed.journal import Journal, edits_journal
from instamatic.experiments.scan_ed.progress import ProgressTable, edits_progress
from instamatic.grid.grid import ConvexPolygonGrid
from instamatic.grid.window import ConvexPolygonWindow

WindowFactory: Callable[[float, float, float, ...], type[ConvexPolygonWindow]]


class State:
    """Stores the current state of the SPED experiment in history dataframe."""

    def __init__(
        self,
        journal: Journal,
        grid: ConvexPolygonGrid,
        progress: Optional[ProgressTable] = None,
    ) -> None:
        self.journal: Journal = journal
        self.grid: ConvexPolygonGrid = grid
        self.progress: Optional[ProgressTable] = progress

        self.scans: pd.DataFrame = pd.DataFrame()
        self.steps: pd.DataFrame = pd.DataFrame()
        self._init_dataframes()

    def _init_dataframes(self) -> None:
        """Create a new empty history with required index and columns."""
        scan_columns = {
            'window': pd.Series(dtype=np.uint16),
            'scan': pd.Series(dtype=np.uint16),
            'x0': pd.Series(dtype=np.int32),
            'y0': pd.Series(dtype=np.int32),
            'axis': pd.Series(dtype=np.uint8),
            'step': pd.Series(dtype=np.int32),
            'n_steps': pd.Series(dtype=np.uint16),
        }
        steps_columns = {
            'window': pd.Series(dtype=np.uint16),
            'scan': pd.Series(dtype=np.uint16),
            'step': pd.Series(dtype=np.uint16),
            'hits': pd.Series(dtype=np.bool),
            'n_peaks': pd.Series(dtype=np.int16),
        }
        self.scans = pd.DataFrame(scan_columns)
        self.scans.set_index(['window', 'scan'], inplace=True)
        self.steps = pd.DataFrame(steps_columns)
        self.steps.set_index(['window', 'scan', 'step'], inplace=True)

    def load_from_journal(self) -> None:
        with self.journal.writing_off():
            for event in self.journal.events():
                method = getattr(self, event['method'])
                kwargs = event.get('kwargs', {})
                method(**kwargs)

    @edits_journal
    @edits_progress
    def add_window(self, idx: int, window: ConvexPolygonWindow) -> None:
        """For journaling purposes, can be added via instance or __repr__."""
        self.grid.windows[idx] = window

    @edits_journal
    @edits_progress
    def add_scan(
        self,
        window: int,
        scan: int,
        x0: int,
        y0: int,
        axis: int,
        step: int,
        n_steps: int,
    ) -> None:
        """Append to scans and pre-allocate space in the steps dataframe."""
        scan_cols = ['x0', 'y0', 'axis', 'step', 'n_steps']
        self.scans.loc[(window, scan), scan_cols] = (x0, y0, axis, step, n_steps)
        idx_names = ['window', 'scan', 'step']
        idx = pd.MultiIndex.from_product([[window], [scan], range(n_steps)], names=idx_names)
        self.steps.loc[idx, 'hits'] = np.full(n_steps, False, dtype=np.bool)
        self.steps.loc[idx, 'n_peaks'] = np.full(n_steps, -1, dtype=np.int16)

    @edits_journal
    @edits_progress
    def fill_scan(
        self,
        window: int,
        scan: int,
        hits: Union[np.ndarray, Sequence[bool]],
        n_peaks: Union[np.ndarray, Sequence[int]],
    ) -> None:
        """Fill a previously-added scan with success/n_peaks in one update."""
        idx = pd.IndexSlice[window, scan, :]
        n_rows = self.scans.loc[(window, scan), 'n_steps']
        if len(hits) != n_rows or len(n_peaks) != n_rows:
            raise ValueError(f'Expected {n_rows} steps, got {len(hits)=}, {len(n_peaks)=}')
        self.steps.loc[idx, 'hits'] = np.array(hits, dtype=np.bool)
        self.steps.loc[idx, 'n_peaks'] = np.asarray(n_peaks, dtype=np.uint16)
