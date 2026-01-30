from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from instamatic.experiments.scan_ed.encoding import *
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
            'hits': pd.Series(dtype=np.bool_),
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
        self.steps.loc[idx, 'hits'] = np.full(n_steps, False, dtype=np.bool_)
        self.steps.loc[idx, 'n_peaks'] = np.full(n_steps, -1, dtype=np.int16)

    def finalize_scan(self, window: int, scan: int) -> None:
        idx = pd.IndexSlice[window, scan, :]
        n_peaks = self.steps.loc[idx, 'n_peaks'].to_numpy(np.int16, copy=False)
        if (n_peaks < 0).any():
            raise RuntimeError('Scan not complete.')

        hits = self.steps.loc[idx, 'hits'].to_numpy(np.bool_, copy=False)

        payload = {
            'window': int(window),
            'scan': int(scan),
            'hits': encode_hits(hits),
            'n_peaks': encode_i16(n_peaks),
        }
        self.journal.write('fill_encoded_scan', payload)

    @edits_progress
    def mark_processing(self, window: int, scan: int, step: int) -> None:
        """Mark a step as currently processed by setting n_peaks to -2."""
        idx = (window, scan, step)
        if int(self.steps.at[idx, 'n_peaks']) == -1:
            self.steps.at[idx, 'n_peaks'] = np.int16(-2)

    @edits_progress
    def fill_step(self, window: int, scan: int, step: int, hit: bool, n_peaks: int) -> None:
        """Once the step is processed, set correct hit bool and n_peaks."""
        idx = (window, scan, step)
        self.steps.at[idx, 'hits'] = bool(hit)
        self.steps.at[idx, 'n_peaks'] = np.int16(n_peaks)

    @edits_progress
    def fill_scan(self, window: int, scan: int, hits, n_peaks) -> None:
        """An alternative to repeated fill_step, fills whole scan at once."""
        idx = pd.IndexSlice[window, scan, :]
        self.steps.loc[idx, 'hits'] = np.asarray(hits, dtype=np.bool_)
        self.steps.loc[idx, 'n_peaks'] = np.asarray(n_peaks, dtype=np.int16)

    def fill_encoded_scan(self, window: int, scan: int, hits: str, n_peaks: str) -> None:
        """To be called ONLY during replay when recreating from journal."""
        n_steps = int(self.scans.loc[(window, scan), 'n_steps'])
        hits_arr = decode_hits(hits, n_steps)
        peaks_arr = decode_i16(n_peaks)
        if peaks_arr.size != n_steps:
            raise ValueError(f'Corrupt scan payload: {peaks_arr.size=} != {n_steps=}')
        self.fill_scan(window, scan, hits_arr, peaks_arr)
