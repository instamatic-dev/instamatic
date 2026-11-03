from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

import pandas as pd

from instamatic._typing import float_nm
from instamatic.experiments.scan_ed.encoding import *
from instamatic.experiments.scan_ed.journal import Journal, edits_journal
from instamatic.experiments.scan_ed.progress import ProgressTable, edits_progress

if TYPE_CHECKING:
    from instamatic.experiments.scan_ed.dispatch import DiffHuntDispatcher


class State:
    """Stores the current state of the SPED experiment in history dataframe."""

    def __init__(
        self,
        journal: Journal,
        progress: Optional[ProgressTable] = None,
    ) -> None:
        self.journal: Journal = journal
        self.progress: Optional[ProgressTable] = progress
        self.dispatcher: Optional[DiffHuntDispatcher] = None

        self.lines: pd.DataFrame = pd.DataFrame()
        self.scans: pd.DataFrame = pd.DataFrame()
        self.steps: pd.DataFrame = pd.DataFrame()
        self._init_dataframes()

    def _init_dataframes(self) -> None:
        """Create a new empty history with required indices and columns."""
        lines_columns = {
            'region': pd.Series(dtype='UInt16'),
            'line': pd.Series(dtype='UInt16'),
            'x0': pd.Series(dtype='Int32'),
            'y0': pd.Series(dtype='Int32'),
            'axis': pd.Series(dtype='UInt8'),
            'step': pd.Series(dtype='Int32'),
            'n_steps': pd.Series(dtype='UInt16'),
        }
        self.lines = pd.DataFrame(lines_columns)
        self.lines.set_index(['region', 'line'], inplace=True)

        scans_columns = {
            'region': pd.Series(dtype='UInt16'),
            'line': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt8'),
            'tilt': pd.Series(dtype='Float32'),
            'offset': pd.Series(dtype='Float32'),
        }
        self.scans = pd.DataFrame(scans_columns)
        self.scans.set_index(['region', 'line', 'scan'], inplace=True)

        steps_columns = {
            'region': pd.Series(dtype='UInt16'),
            'line': pd.Series(dtype='UInt16'),
            'scan': pd.Series(dtype='UInt8'),
            'step': pd.Series(dtype='UInt16'),
            'hits': pd.Series(dtype='boolean'),
            'light': pd.Series(dtype='UInt32'),
            'n_peaks': pd.Series(dtype='Int16'),
        }
        self.steps = pd.DataFrame(steps_columns)
        self.steps.set_index(['region', 'line', 'scan', 'step'], inplace=True)

    def load_from_journal(self, fill: bool = True) -> None:
        """Recreate experiment state from journal file: get the list of events
        and, if fill=True, apply only the latest fill event to save time."""

        events = list(self.journal.events())

        latest_fill_event: dict[tuple[int, int, int], int] = {}
        for event in events:
            if fill and event['method'] == 'fill_encoded_scan':
                k = event['kwargs']
                latest_fill_event[(k['region'], k['line'], k['scan'])] = event['seq']

        with self.journal.writing_off():
            for event in events:
                method_name, kwargs = event['method'], event.get('kwargs', {})
                if method_name == 'configure_dispatcher':
                    continue  # reapplied live, not part of structural state
                if fill and method_name == 'fill_encoded_scan':
                    key = (kwargs['region'], kwargs['line'], kwargs['scan'])
                    if event['seq'] != latest_fill_event[key]:
                        continue  # superseded by a later reprocess pass
                getattr(self, method_name)(**kwargs)

    @edits_journal
    @edits_progress
    def add_region(self, region: int, windows: Sequence[int]) -> None:
        pass

    @edits_journal
    @edits_progress
    def add_line(
        self,
        region: int,
        line: int,
        x0: int,
        y0: int,
        axis: int,
        step: int,
        n_steps: int,
    ) -> None:
        """Append to scans and pre-allocate space in the steps dataframe."""
        lines_cols = ['x0', 'y0', 'axis', 'step', 'n_steps']
        self.lines.loc[(region, line), lines_cols] = (x0, y0, axis, step, n_steps)

    @edits_journal
    def configure_dispatcher(self, **params) -> None:
        assert self.dispatcher is not None
        self.dispatcher.emit_all('CONFIGURE', **params)

    @edits_journal
    @edits_progress
    def add_scan(
        self,
        region: int,
        line: int,
        scan: int,
        tilt: float,
    ) -> None:
        """Append to scans and pre-allocate space in the steps dataframe."""
        n_steps = self.lines.loc[(region, line)]['n_steps']

        self.scans.loc[(region, line, scan), 'tilt'] = tilt

        names = ['region', 'line', 'scan', 'step']
        product = [[region], [line], [scan], range(n_steps)]
        idx = pd.MultiIndex.from_product(product, names=names)
        new_scans = {
            'hits': np.zeros(n_steps, dtype=np.bool_),
            'light': np.zeros(n_steps, dtype=np.uint32),
            'n_peaks': np.full(n_steps, -1, dtype=np.int16),
        }
        self.steps = pd.concat([self.steps, pd.DataFrame(new_scans, index=idx)])

    def finalize_scan(self, region: int, line: int, scan: int, offset: float_nm = 0) -> None:
        """Converts scan results to an encoded scan, writes it to journal."""
        idx = pd.IndexSlice[region, line, scan, :]
        n_peaks = self.steps.loc[idx, 'n_peaks'].to_numpy(np.int16, copy=False)
        if (n_peaks < 0).any():
            raise RuntimeError(f'Scan incomplete or still in process: {n_peaks}')

        self.scans.loc[(region, line, scan), 'offset'] = offset

        hits = self.steps.loc[idx, 'hits'].to_numpy(np.bool_, copy=False)
        light = self.steps.loc[idx, 'light'].to_numpy(np.uint32, copy=False)

        payload = {
            'region': int(region),
            'line': int(line),
            'scan': int(scan),
            'offset': float(offset),
            'hits': encode_hits(hits),
            'light': encode_u32(light),
            'n_peaks': encode_i16(n_peaks),
        }
        self.journal.write('fill_encoded_scan', payload)

    @edits_progress
    def mark_processing(self, region: int, line: int, scan: int, step: int) -> None:
        """Mark a step as currently processed by setting n_peaks to -2."""
        idx = (region, line, scan, step)
        if int(self.steps.at[idx, 'n_peaks']) == -1:
            self.steps.at[idx, 'n_peaks'] = np.int16(-2)

    @edits_progress
    def fill_step(
        self,
        region: int,
        line: int,
        scan: int,
        step: int,
        hits: bool,
        light: int,
        n_peaks: int,
    ) -> None:
        """Once the step is processed, set correct hit bool and n_peaks."""
        idx = (region, line, scan, step)
        self.steps.at[idx, 'hits'] = bool(hits)
        self.steps.at[idx, 'light'] = np.uint32(light)
        self.steps.at[idx, 'n_peaks'] = np.int16(n_peaks)

    @edits_progress
    def fill_scan(
        self,
        region: int,
        line: int,
        scan: int,
        offset: float_nm,
        hits: Sequence[bool],
        light: Sequence[int],
        n_peaks: Sequence[int],
    ) -> None:
        """An alternative to repeated fill_step, fills whole scan at once."""
        self.scans.loc[(region, line, scan), 'offset'] = offset
        idx = pd.IndexSlice[region, line, scan, :]
        self.steps.loc[idx, 'hits'] = np.asarray(hits, dtype=np.bool_)
        self.steps.loc[idx, 'light'] = np.asarray(light, dtype=np.uint32)
        self.steps.loc[idx, 'n_peaks'] = np.asarray(n_peaks, dtype=np.int16)

    def fill_encoded_scan(
        self,
        region: int,
        line: int,
        scan: int,
        offset: float_nm,
        hits: str,
        light: str,
        n_peaks: str,
    ) -> None:
        """Called directly ONLY during replay when recreating from journal."""
        n_steps = int(self.lines.loc[(region, line), 'n_steps'])
        hits_arr = decode_hits(hits, n_steps)
        light_arr = decode_u32(light)
        peaks_arr = decode_i16(n_peaks)
        if peaks_arr.size != n_steps:
            raise ValueError(f'Corrupt scan payload: {peaks_arr.size=} != {n_steps=}')
        self.fill_scan(region, line, scan, offset, hits_arr, light_arr, peaks_arr)

    def has_any_scans(self, region: int) -> bool:
        """Returns True if region has any defined scans with any status."""
        i, k = self.scans.index, 'region'
        return len(self.scans) > 0 and k in i.names and (i.get_level_values(k) == region).any()

    def untouched_scans(self, region: Optional[int] = None) -> pd.MultiIndex:
        """Iterable of (region, line, scan) of planned-but-untouched scans."""
        n_peaks = self.steps['n_peaks']
        if region is not None:
            n_peaks = n_peaks.xs(region, level='region', drop_level=False)
        untouched = n_peaks.eq(-1).groupby(level=['region', 'line', 'scan']).all()
        return untouched[untouched].index
