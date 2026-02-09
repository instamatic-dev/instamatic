from __future__ import annotations

import inspect
import queue
import tkinter as tk
import tkinter.ttk as ttk
from collections import Counter
from functools import wraps
from typing import Any, Callable, Protocol, Sequence, Union

import numpy as np


class GridWindowProtocol(Protocol):
    def __repr__(self) -> str: ...


def safe_ratio(d: dict, k1: str, k2: str, alt: str = '0.0') -> str:
    """Return a formatted d1-to-d2 ratio if defined, else hyphen."""
    return f'{d[k1] / v2:.3g}' if (v2 := d[k2]) else alt


class ProgressTable(ttk.Frame):
    """Use a ttk.TreeView to display the progress of scanning experiment."""

    COLUMNS = 'geometry hits peaks steps hits/step peaks/step'.split()

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.tree = None
        self._build_tree()
        self._scan_geom: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self._scan_totals: dict[tuple[int, int], Counter] = {}  # hits, peaks, done, n_steps
        self._window_totals: dict[int, Counter] = {}  # hits, peaks, steps

    def _build_tree(self) -> None:
        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show='tree headings')

        for column in self.COLUMNS:
            self.tree.heading(column, text=column)

        self.tree.column('#0', width=40, stretch=True)
        self.tree.column('geometry', anchor=tk.CENTER, width=160)
        self.tree.column('hits', anchor=tk.E, width=20)
        self.tree.column('peaks', anchor=tk.E, width=20)
        self.tree.column('steps', anchor=tk.E, width=20)
        self.tree.column('hits/step', anchor=tk.E, width=20)
        self.tree.column('peaks/step', anchor=tk.E, width=20)

        vsb = ttk.Scrollbar(orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(column=0, row=0, sticky='nsew', in_=self)
        vsb.grid(column=1, row=0, sticky='ns', in_=self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    @staticmethod
    def _window_iid(window: int) -> str:
        return f'w:{window}'

    @staticmethod
    def _scan_iid(window: int, scan: int) -> str:
        return f'w:{window}/s:{scan}'

    @staticmethod
    def _step_iid(window: int, scan: int, step: int) -> str:
        return f'w:{window}/s:{scan}/p:{step}'

    def add_window(self, idx: int, window: GridWindowProtocol) -> None:
        """Add a new parent line to the tree called Window #."""
        window_iid = self._window_iid(idx)
        window_name = f'Window {idx:d}'
        values = (str(window), '-', '-', '-', '-', '-')
        self.tree.insert('', tk.END, iid=window_iid, text=window_name, values=values)
        self._window_totals[idx] = Counter()

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
        """Add a new child scan line to the tree called Scan # (planned)."""
        window_iid = self._window_iid(window)
        scan_iid = self._scan_iid(window, scan)
        scan_name = f'Scan {scan:d}'

        start = (x0, y0)[axis]
        end = start + step * n_steps

        if axis == 0:  # x
            geom = f'y={y0}, x: {start} -> {end}'
        else:
            geom = f'x={x0}, y: {start} -> {end}'

        values = (geom, '-', '-', str(int(n_steps)), '-', '-')
        self.tree.insert(window_iid, tk.END, iid=scan_iid, text=scan_name, values=values)

        self._scan_geom[(window, scan)] = (x0, y0, axis, step)
        self._scan_totals[(window, scan)] = Counter(n_steps=int(n_steps))
        self.tree.set(scan_iid, 'steps', f'0/{int(n_steps)}')

    def mark_processing(self, window: int, scan: int, step: int) -> None:
        scan_iid = self._scan_iid(window, scan)
        for column in 'hits peaks hits/step peaks/step'.split():
            if not self.tree.set(scan_iid, column).isnumeric():  # don't overwrite numbers
                self.tree.set(scan_iid, column, '...')

    def fill_step(self, window: int, scan: int, step: int, hit: bool, n_peaks: int) -> None:
        scan_iid = self._scan_iid(window, scan)
        window_iid = self._window_iid(window)

        st = self._scan_totals[(window, scan)]
        st['done'] += 1
        if hit:
            st['hits'] += 1
            st['peaks'] += int(n_peaks)

        self.tree.set(scan_iid, 'hits', str(st['hits']))
        self.tree.set(scan_iid, 'peaks', str(st['peaks']))
        self.tree.set(scan_iid, 'steps', f'{st["done"]}/{st["n_steps"]}')
        self.tree.set(scan_iid, 'hits/step', safe_ratio(st, 'hits', 'done'))
        self.tree.set(scan_iid, 'peaks/step', safe_ratio(st, 'peaks', 'done'))

        wt = self._window_totals[window]
        wt['steps'] += 1
        if hit:
            wt['hits'] += 1
            wt['peaks'] += int(n_peaks)

        self.tree.set(window_iid, 'hits', str(wt['hits']))
        self.tree.set(window_iid, 'peaks', str(wt['peaks']))
        self.tree.set(window_iid, 'steps', str(wt['steps']))
        self.tree.set(window_iid, 'hits/step', safe_ratio(wt, 'hits', 'steps'))
        self.tree.set(window_iid, 'peaks/step', safe_ratio(wt, 'peaks', 'steps'))

        if hit:
            x0, y0, axis, step_size = self._scan_geom[(window, scan)]
            step_iid = self._step_iid(window, scan, step)
            geom = f'{"xy"[axis]}: {(x0, y0)[axis] + step * step_size}'
            v = (geom, '', int(n_peaks), '', '', '')
            self.tree.insert(scan_iid, tk.END, iid=step_iid, text=f'Step {step}', values=v)

    def fill_scan(
        self,
        window: int,
        scan: int,
        hits: Union[np.ndarray, Sequence[bool]],
        n_peaks: Union[np.ndarray, Sequence[int]],
    ) -> None:
        """Add lines for successful experiments, update scan & column lines."""

        scan_iid = self._scan_iid(window, scan)
        window_iid = self._window_iid(window)
        hits_arr = np.asarray(hits, dtype=bool)
        peaks_arr = np.asarray(n_peaks, dtype=int)

        s_steps = int(hits_arr.size)
        s_hits = int(hits_arr.sum())
        s_peaks = int(peaks_arr[hits_arr].sum()) if s_hits else 0

        self.tree.set(scan_iid, 'hits', str(s_hits))
        self.tree.set(scan_iid, 'peaks', str(s_peaks))
        self.tree.set(scan_iid, 'steps', str(s_steps))
        self.tree.set(scan_iid, 'hits/step', f'{s_hits / s_steps if s_steps else 0.0:.3g}')
        self.tree.set(scan_iid, 'peaks/step', f'{s_peaks / s_steps if s_steps else 0.0:.3g}')

        wt = self._window_totals[window]
        wt['hits'] += s_hits
        wt['peaks'] += s_peaks
        wt['steps'] += s_steps

        self.tree.set(window_iid, 'hits', str(wt['hits']))
        self.tree.set(window_iid, 'peaks', str(wt['peaks']))
        self.tree.set(window_iid, 'steps', str(wt['steps']))
        self.tree.set(window_iid, 'hits/step', safe_ratio(wt, 'hits', 'steps'))
        self.tree.set(window_iid, 'peaks/step', safe_ratio(wt, 'peaks', 'steps'))

    def clear(self) -> None:
        """Remove all rows and reset cached totals (e.g. before loading)."""
        for iid in self.tree.get_children(''):
            self.tree.delete(iid)
        self._scan_geom.clear()
        self._scan_totals.clear()
        self._window_totals.clear()


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
    def add_window(self, **kwargs):
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
