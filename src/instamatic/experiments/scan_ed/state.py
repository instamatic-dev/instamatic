from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from instamatic._collections import NoOverwriteDict
from instamatic.experiments.scan_ed.encoding import *
from instamatic.experiments.scan_ed.journal import Journal, edits_journal
from instamatic.experiments.scan_ed.progress import ProgressTable, edits_progress
from instamatic.grid.geometry import PeriodicConvexPolygonGridGeometry
from instamatic.grid.window import GridablePolygonWindow


class State:
    """Stores the current state of the SPED experiment in history dataframe."""

    def __init__(
        self,
        journal: Journal,
        grid: PeriodicConvexPolygonGridGeometry,
        progress: Optional[ProgressTable] = None,
        intercepts: Optional[dict[int, np.ndarray]] = None,
    ) -> None:
        self.journal: Journal = journal
        self.grid: PeriodicConvexPolygonGridGeometry = grid
        self.progress: Optional[ProgressTable] = progress
        self.intercepts: NoOverwriteDict[int, np.ndarray] = NoOverwriteDict(intercepts or {})

        self.scans: pd.DataFrame = pd.DataFrame()
        self.steps: pd.DataFrame = pd.DataFrame()
        self._init_dataframes()

    def _init_dataframes(self) -> None:
        """Create a new empty history with required index and columns."""
        scan_columns = {
            'region': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt16'),
            'x0': pd.Series(dtype='Int32'),
            'y0': pd.Series(dtype='Int32'),
            'axis': pd.Series(dtype='UInt8'),
            'step': pd.Series(dtype='Int32'),
            'n_steps': pd.Series(dtype='UInt16'),
        }
        steps_columns = {
            'region': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt16'),
            'step': pd.Series(dtype='UInt16'),
            'hits': pd.Series(dtype='boolean'),
            'n_peaks': pd.Series(dtype='Int16'),
        }
        self.scans = pd.DataFrame(scan_columns)
        self.scans.set_index(['region', 'scan'], inplace=True)
        self.steps = pd.DataFrame(steps_columns)
        self.steps.set_index(['region', 'scan', 'step'], inplace=True)

    def load_from_journal(self) -> None:
        """Recreate an instance of experiment state from journal file."""
        with self.journal.writing_off():
            for event in self.journal.events():
                method_name = event['method']
                kwargs = event.get('kwargs', {})
                getattr(self, method_name)(**kwargs)

    @edits_journal
    def add_intercepts(self, idx: int, intercepts: np.ndarray) -> None:
        """Add a Nx2 matrix of intercepts of window idx."""
        self.intercepts[idx] = np.asarray(intercepts, dtype=float)

    @edits_journal
    @edits_progress
    def add_scan(
        self,
        region: int,
        scan: int,
        x0: int,
        y0: int,
        axis: int,
        step: int,
        n_steps: int,
    ) -> None:
        """Append to scans and pre-allocate space in the steps dataframe."""
        scan_cols = ['x0', 'y0', 'axis', 'step', 'n_steps']
        self.scans.loc[(region, scan), scan_cols] = (x0, y0, axis, step, n_steps)
        idx_names = ['region', 'scan', 'step']
        idx = pd.MultiIndex.from_product([[region], [scan], range(n_steps)], names=idx_names)
        new_scans = {
            'hits': np.zeros(n_steps, dtype=np.bool_),
            'n_peaks': np.full(n_steps, -1, dtype=np.int16),
        }
        self.steps = pd.concat([self.steps, pd.DataFrame(new_scans, index=idx)])

    def finalize_scan(self, region: int, scan: int) -> None:
        """Converts scan results to an encoded scan, writes it to journal."""
        idx = pd.IndexSlice[region, scan, :]
        n_peaks = self.steps.loc[idx, 'n_peaks'].to_numpy(np.int16, copy=False)
        if (n_peaks < 0).any():
            raise RuntimeError('Scan not complete.')

        hits = self.steps.loc[idx, 'hits'].to_numpy(np.bool_, copy=False)

        payload = {
            'region': int(region),
            'scan': int(scan),
            'hits': encode_hits(hits),
            'n_peaks': encode_i16(n_peaks),
        }
        self.journal.write('fill_encoded_scan', payload)

    @edits_progress
    def mark_processing(self, region: int, scan: int, step: int) -> None:
        """Mark a step as currently processed by setting n_peaks to -2."""
        idx = (region, scan, step)
        if int(self.steps.at[idx, 'n_peaks']) == -1:
            self.steps.at[idx, 'n_peaks'] = np.int16(-2)

    @edits_progress
    def fill_step(self, region: int, scan: int, step: int, hit: bool, n_peaks: int) -> None:
        """Once the step is processed, set correct hit bool and n_peaks."""
        idx = (region, scan, step)
        self.steps.at[idx, 'hits'] = bool(hit)
        self.steps.at[idx, 'n_peaks'] = np.int16(n_peaks)

    @edits_progress
    def fill_scan(self, region: int, scan: int, hits, n_peaks) -> None:
        """An alternative to repeated fill_step, fills whole scan at once."""
        idx = pd.IndexSlice[region, scan, :]
        self.steps.loc[idx, 'hits'] = np.asarray(hits, dtype=np.bool_)
        self.steps.loc[idx, 'n_peaks'] = np.asarray(n_peaks, dtype=np.int16)

    def fill_encoded_scan(self, region: int, scan: int, hits: str, n_peaks: str) -> None:
        """Called directly ONLY during replay when recreating from journal."""
        n_steps = int(self.scans.loc[(region, scan), 'n_steps'])
        hits_arr = decode_hits(hits, n_steps)
        peaks_arr = decode_i16(n_peaks)
        if peaks_arr.size != n_steps:
            raise ValueError(f'Corrupt scan payload: {peaks_arr.size=} != {n_steps=}')
        self.fill_scan(region, scan, hits_arr, peaks_arr)

    def has_any_scans(self, region: int) -> bool:
        """Returns True if region has any defined scans with any status."""
        i, k = self.scans.index, 'region'
        return len(self.scans) > 0 and k in i.names and (i.get_level_values(k) == region).any()

    def untouched_scans(self, region: Optional[int] = None) -> pd.MultiIndex:
        """An iterable of (region, scan)-idx of planned-but-untouched scans."""
        n_peaks = self.steps['n_peaks']
        if region is not None:
            n_peaks = n_peaks.xs(region, level='region', drop_level=False)
        untouched = n_peaks.eq(-1).groupby(level=['region', 'scan']).all()
        return untouched[untouched].index

    @edits_journal
    def update_grid(self, params: dict[str, float]) -> None:
        self.grid = self.grid.__class__(**params)
