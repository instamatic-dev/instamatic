from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from instamatic.experiments.scan_ed.encoding import *
from instamatic.experiments.scan_ed.journal import Journal, edits_journal
from instamatic.experiments.scan_ed.progress import ProgressTable, edits_progress
from instamatic.grid.grid import PeriodicConvexPolygonGrid
from instamatic.grid.window import GridablePolygonWindow

WindowFactory: Callable[[float, float, float, ...], type[GridablePolygonWindow]]


class State:
    """Stores the current state of the SPED experiment in history dataframe."""

    def __init__(
        self,
        journal: Journal,
        grid: PeriodicConvexPolygonGrid,
        progress: Optional[ProgressTable] = None,
    ) -> None:
        self.journal: Journal = journal
        self.grid: PeriodicConvexPolygonGrid = grid
        self.progress: Optional[ProgressTable] = progress

        self.scans: pd.DataFrame = pd.DataFrame()
        self.steps: pd.DataFrame = pd.DataFrame()
        self._init_dataframes()

    def _init_dataframes(self) -> None:
        """Create a new empty history with required index and columns."""
        scan_columns = {
            'window': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt16'),
            'x0': pd.Series(dtype='Int32'),
            'y0': pd.Series(dtype='Int32'),
            'axis': pd.Series(dtype='UInt8'),
            'step': pd.Series(dtype='Int32'),
            'n_steps': pd.Series(dtype='UInt16'),
        }
        steps_columns = {
            'window': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt16'),
            'step': pd.Series(dtype='UInt16'),
            'hits': pd.Series(dtype='boolean'),
            'n_peaks': pd.Series(dtype='Int16'),
        }
        self.scans = pd.DataFrame(scan_columns)
        self.scans.set_index(['window', 'scan'], inplace=True)
        self.steps = pd.DataFrame(steps_columns)
        self.steps.set_index(['window', 'scan', 'step'], inplace=True)

    def load_from_journal(self) -> None:
        with self.journal.writing_off():
            for event in self.journal.events():
                method_name = event['method']
                kwargs = event.get('kwargs', {})
                if method_name == 'add_window':
                    wkw = {k: float(v) for k, v in kwargs.pop('window').items()}
                    kwargs['window'] = self.grid.window_type(**wkw)
                getattr(self, method_name)(**kwargs)

    @edits_journal
    @edits_progress
    def add_window(self, idx: int, window: GridablePolygonWindow) -> None:
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
        new_scans = {
            'hits': np.zeros(n_steps, dtype=np.bool_),
            'n_peaks': np.full(n_steps, -1, dtype=np.int16),
        }
        self.steps = pd.concat([self.steps, pd.DataFrame(new_scans, index=idx)])

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

    def has_any_scans(self, window: int) -> bool:
        """Returns True if window has any defined scans with any status."""
        i, k = self.scans.index, 'window'
        return len(self.scans) > 0 and k in i.names and (i.get_level_values(k) == window).any()

    def untouched_scans(self, window: Optional[int] = None) -> pd.MultiIndex:
        """An iterable of (window, scan)-idx of planned-but-untouched scans."""
        n_peaks = self.steps['n_peaks']
        if window is not None:
            n_peaks = n_peaks.xs(window, level='window', drop_level=False)
        untouched = n_peaks.eq(-1).groupby(level=['window', 'scan']).all()
        return untouched[untouched].index

    def window_progress(self, window: int) -> float:
        """Return measured fraction of the window scans (length-weighted)."""
        if self.scans.empty or window not in self.scans.index.get_level_values('window'):
            return 0.0
        scans = self.scans.xs(window, level='window', drop_level=False)
        total_steps = int(scans['n_steps'].sum())
        if total_steps == 0:
            return 0.0
        n_peaks = self.steps['n_peaks'].xs(window, level='window', drop_level=False)
        touched = n_peaks.ge(0).groupby(level=['window', 'scan']).any()
        touched = touched.reindex(scans.index, fill_value=False)
        return scans.loc[touched, 'n_steps'].sum() / total_steps
