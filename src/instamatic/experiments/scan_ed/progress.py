from __future__ import annotations

import inspect
import queue
import tkinter as tk
import tkinter.ttk as ttk
from collections import Counter
from functools import wraps
from typing import Any, Callable, Optional, Protocol, Sequence, Union

import numpy as np


class GridWindowProtocol(Protocol):
    def __repr__(self) -> str: ...


def new_counter(**kwargs):
    """A new counter to sum current hit, peak, step, and total step count."""
    starting_dict = {'hits': 0, 'peaks': 0, 'steps': 0, 'n_steps': 0} | kwargs
    return Counter(**starting_dict)


def safe_ratio(d: dict, k1: str, k2: str, alt: str = '0.0') -> str:
    """Return a formatted d1-to-d2 ratio if defined, else hyphen."""
    return f'{d[k1] / v2:.3g}' if (v2 := d[k2]) else alt


class ProgressTable(ttk.Frame):
    """Use a ttk.TreeView to display the progress of scanning experiment."""

    COLUMNS = ('geometry', 'hits', 'peaks', 'steps', 'hit rate')

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.tree: Optional[ttk.Treeview] = None
        self._build_tree()

        self._line_geom: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
        self._region_totals: dict[int, Counter] = {}
        self._line_totals: dict[tuple[int, int], Counter] = {}
        self._scan_totals: dict[tuple[int, int, int], Counter] = {}

    def _build_tree(self) -> None:
        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show='tree headings')

        for column in self.COLUMNS:
            self.tree.heading(column, text=column)

        self.tree.column('#0', width=40, stretch=True)
        self.tree.column('geometry', anchor=tk.CENTER, width=160)
        self.tree.column('hits', anchor=tk.E, width=20)
        self.tree.column('peaks', anchor=tk.E, width=20)
        self.tree.column('steps', anchor=tk.E, width=20)
        self.tree.column('hit rate', anchor=tk.E, width=20)

        vsb = ttk.Scrollbar(orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(column=0, row=0, sticky='nsew', in_=self)
        vsb.grid(column=1, row=0, sticky='ns', in_=self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    @staticmethod
    def _region_iid(region: int) -> str:
        return f'r:{region}'

    @staticmethod
    def _line_iid(region: int, line: int) -> str:
        return f'r:{region}/l:{line}'

    @staticmethod
    def _scan_iid(region: int, line: int, scan: int) -> str:
        return f'r:{region}/l:{line}/s:{scan}/'

    @staticmethod
    def _step_iid(region: int, line: int, scan: int, step: int) -> str:
        return f'r:{region}/l:{line}/s:{scan}/p:{step}'

    def add_region(self, region: int, windows: Sequence[int]) -> None:
        """Add a new parent line called Region # with window information."""
        region_iid = self._region_iid(region)
        region_name = f'Region {region:d}'
        geometry = 'Windows: ' + ' '.join(str(w) for w in windows)
        values = (geometry, '-', '-', '-', '-')
        self.tree.insert('', tk.END, iid=region_iid, text=region_name, values=values)
        self._region_totals[region] = new_counter()

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
        """Add a new line under region for "line" geometry called Line #."""
        region_iid = self._region_iid(region)
        line_iid = self._line_iid(region, line)
        line_name = f'Line {line}'

        start = (x0, y0)[axis]
        end = start + step * n_steps
        if axis == 0:
            geom = f'y={y0}, x: {start} -> {end}'
        else:
            geom = f'x={x0}, y: {start} -> {end}'

        v = (geom, '-', '-', f'0/{n_steps}', '-')
        self.tree.insert(region_iid, tk.END, iid=line_iid, text=line_name, values=v)
        self._line_geom[(region, line)] = (x0, y0, axis, step, n_steps)
        self._line_totals[(region, line)] = new_counter()

    def add_scan(
        self,
        region: int,
        line: int,
        scan: int,
        tilt: float,
    ) -> None:
        """Add a new child scan line to the tree called Scan # (planned)."""
        line_iid = self._line_iid(region, line)
        scan_iid = self._scan_iid(region, line, scan)
        scan_name = f'Scan {scan}'

        _, _, _, _, n_steps = self._line_geom[(region, line)]
        v = (f'tilt: {tilt:+6.3f} deg', '0', '0', f'0/{n_steps}', '0.0')
        self.tree.insert(line_iid, tk.END, iid=scan_iid, text=scan_name, values=v)

        self._region_totals[region]['n_steps'] += n_steps
        self._line_totals[(region, line)]['n_steps'] += n_steps
        self._scan_totals[(region, line, scan)] = new_counter(n_steps=n_steps)
        self._update_totals_display(region, line, scan)

    def mark_processing(self, region: int, line: int, scan: int, *_) -> None:
        scan_iid = self._scan_iid(region, line, scan)
        for column in ['hits', 'peaks', 'hit rate']:
            if not self.tree.set(scan_iid, column).isnumeric():  # don't overwrite numbers
                self.tree.set(scan_iid, column, '...')

    def _update_totals_display(self, region: int, line: int, scan: int) -> None:
        self._update_region_totals_display(region=region)
        self._update_line_totals_display(region=region, line=line)
        self._update_scan_totals_display(region=region, line=line, scan=scan)

    def _update_region_totals_display(self, region: int) -> None:
        region_iid = self._region_iid(region)
        region_totals = self._region_totals[region]
        self._update_row_display(row_iid=region_iid, totals=region_totals)

    def _update_line_totals_display(self, region: int, line: int) -> None:
        line_iid = self._line_iid(region, line)
        line_totals = self._line_totals[(region, line)]
        self._update_row_display(row_iid=line_iid, totals=line_totals)

    def _update_scan_totals_display(self, region: int, line: int, scan: int) -> None:
        scan_iid = self._scan_iid(region, line, scan)
        scan_totals = self._scan_totals[(region, line, scan)]
        self._update_row_display(row_iid=scan_iid, totals=scan_totals)

    def _update_row_display(self, row_iid: str, totals: Counter) -> None:
        self.tree.set(row_iid, 'hits', str(totals['hits']))
        self.tree.set(row_iid, 'peaks', str(totals['peaks']))
        self.tree.set(row_iid, 'steps', f'{totals["steps"]}/{totals["n_steps"]}')
        self.tree.set(row_iid, 'hit rate', safe_ratio(totals, 'hits', 'steps'))

    def fill_step(
        self,
        region: int,
        line: int,
        scan: int,
        step: int,
        hit: bool,
        light: int,
        n_peaks: int,
    ) -> None:
        rt = self._region_totals[region]
        lt = self._line_totals[(region, line)]
        st = self._scan_totals[(region, line, scan)]
        for totals_counter in rt, lt, st:
            totals_counter['steps'] += 1
            if hit:
                totals_counter['hits'] += 1
                totals_counter['peaks'] += int(n_peaks)
        self._update_totals_display(region, line, scan)

    def fill_scan(
        self,
        region: int,
        line: int,
        scan: int,
        step: int,
        hits: bool,
        light: int,
        n_peaks: int,
    ) -> None:
        """Add lines for successful experiments, update scan & column lines."""

        hits_arr = np.asarray(hits, dtype=bool)
        peaks_arr = np.asarray(n_peaks, dtype=int)
        sum_steps = int(hits_arr.size)
        sum_hits = int(hits_arr.sum())
        sum_peaks = int(peaks_arr[hits_arr].sum()) if sum_hits else 0

        st = self._scan_totals[(region, line, scan)]
        old_hits = int(st['hits'])
        old_peaks = int(st['peaks'])
        old_steps = int(st['steps'])
        st['hits'] = sum_hits
        st['peaks'] = sum_peaks
        st['steps'] = sum_steps

        lt = self._line_totals[(region, line)]
        lt['hits'] += sum_hits - old_hits
        lt['peaks'] += sum_peaks - old_peaks
        lt['steps'] += sum_steps - old_steps

        rt = self._region_totals[region]
        rt['hits'] += sum_hits - old_hits
        rt['peaks'] += sum_peaks - old_peaks
        rt['steps'] += sum_steps - old_steps

        self._update_totals_display(region, line, scan)

    def clear(self) -> None:
        """Remove all rows and reset cached totals (e.g. before loading)."""
        for iid in self.tree.get_children(''):
            self.tree.delete(iid)
        self._line_geom.clear()
        self._scan_totals.clear()
        self._region_totals.clear()


class ThreadSafeProgressTableProxy:
    """Thread-safe proxy: same API as ProgressTable, executed on Tk thread."""

    def __init__(self, parent: tk.Misc, target) -> None:
        self._parent = parent
        self._target = target
        self._q: queue.Queue[tuple[str, tuple[Any, ...], dict[str, Any]]] = queue.Queue()
        self._scheduled = False

    def _schedule(self) -> None:
        """Lets the main Tk thread know to drain and run commands from _q."""
        if not self._scheduled:
            self._scheduled = True
            self._parent.after(0, self._drain)

    def _drain(self) -> None:
        """Run at the main Tk thread, calls all scheduled commands from _q."""
        self._scheduled = False
        while True:
            try:
                name, args, kwargs = self._q.get_nowait()
            except queue.Empty:
                break
            getattr(self._target, name)(*args, **kwargs)

    def _post(self, name: str, *args, **kwargs) -> None:
        """Instead of running command, schedule it to be run on main thread."""
        self._q.put((name, args, kwargs))
        self._schedule()

    # Keep the API fixed and consistent, generalizing this is annoying
    def add_intercepts(self, **kwargs):
        self._post('add_window', **kwargs)

    def add_scan(self, **kwargs):
        self._post('add_scan', **kwargs)

    def mark_processing(self, **kwargs):
        self._post('mark_processing', **kwargs)

    def fill_step(self, **kwargs):
        self._post('fill_step', **kwargs)

    def fill_scan(self, **kwargs):
        self._post('fill_scan', **kwargs)

    def clear(self, **kwargs):
        self._post('clear', **kwargs)


def edits_progress(method: Callable) -> Callable:
    """Method decorator, captures calls to modify object's progress attr."""
    method_signature = inspect.signature(method)

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        out = method(self, *args, **kwargs)
        if (progress := getattr(self, 'progress', None)) is not None:
            bound = method_signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            kwargs2 = {k: v for k, v in bound.arguments.items() if k != 'self'}
            getattr(progress, method.__name__)(**kwargs2)
        return out

    return wrapper


if __name__ == '__main__':
    root = tk.Tk()
    root.title('Test progress listbox')
    listbox = ProgressTable(root)
    listbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    listbox.add_window(0, 'Some geometry')

    # axis=0 => x scan, step sign gives direction
    listbox.add_scan(0, 0, x0=100, y0=200, axis=0, step=50, n_steps=6)
    listbox.fill_scan(
        0, 0, hits=[True, False, True, False, True, False], n_peaks=[12, 3, 8, 0, 21, 0]
    )

    listbox.add_scan(0, 1, x0=400, y0=210, axis=1, step=-25, n_steps=5)
    listbox.fill_scan(0, 1, hits=[1, 0, 1, 0, 1], n_peaks=[17, 3, 28, 0, 21])

    root.mainloop()
