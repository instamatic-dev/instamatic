from __future__ import annotations

import inspect
import tkinter as tk
import tkinter.ttk as ttk
from functools import wraps
from typing import Callable, Protocol, Sequence, Union

import numpy as np


class GridWindowProtocol(Protocol):
    def __repr__(self) -> str: ...


class ProgressTable(ttk.Frame):
    """Use a ttk.TreeView to display the progress of scanning experiment."""

    COLUMNS = 'geometry hits peaks steps hits/step peaks/step'.split()

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.tree = None
        self._build_tree()
        self._scan_geom: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
        self._window_totals: tuple[int, int, int] = (0, 0, 0)  # hits, peaks, steps

    def _build_tree(self) -> None:
        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show='tree headings')

        for column in self.COLUMNS:
            self.tree.heading(column, text=column)

        self.tree.column('#0', width=30, stretch=True)
        self.tree.column('geometry', anchor=tk.CENTER, width=120)
        self.tree.column('hits', anchor=tk.E, width=20)
        self.tree.column('peaks', anchor=tk.E, width=20)
        self.tree.column('steps', anchor=tk.E, width=20)
        self.tree.column('hits/step', anchor=tk.E, width=20)
        self.tree.column('peaks/step', anchor=tk.E, width=20)

        vsb = ttk.Scrollbar(orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(column=0, row=0, sticky='nsew', in_=self)
        vsb.grid(column=1, row=0, sticky='ns', in_=self)
        hsb.grid(column=0, row=1, sticky='ew', in_=self)
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
        geom = repr(window)
        values = (geom, '-', '-', '-', '-', '-')
        self.tree.insert('', tk.END, iid=window_iid, text=window_name, values=values)
        self._window_totals = (0, 0, 0)

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

        self._scan_geom[(window, scan)] = (x0, y0, axis, step, n_steps)

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
        x0, y0, axis, step, n_steps = self._scan_geom[(int(window), int(scan))]

        s_hits = sum(hits)
        s_peaks = sum(int(n) for ok, n in zip(hits, n_peaks) if ok)
        s_steps = len(hits)
        s_hits_per_step = s_hits / s_steps if s_steps else 0.0
        s_peaks_per_step = s_peaks / s_steps if s_steps else 0.0

        self.tree.set(scan_iid, 'hits', str(s_hits))
        self.tree.set(scan_iid, 'peaks', str(s_peaks))
        self.tree.set(scan_iid, 'steps', str(s_steps))
        self.tree.set(scan_iid, 'hits/step', f'{s_hits_per_step:.3g}')
        self.tree.set(scan_iid, 'peaks/step', f'{s_peaks_per_step:.3g}')

        w_hits = self._window_totals[0] + s_hits
        w_peaks = self._window_totals[1] + s_peaks
        w_steps = self._window_totals[2] + s_steps
        w_hits_per_step = w_hits / w_steps if w_steps else 0.0
        w_peaks_per_step = w_peaks / w_steps if w_steps else 0.0
        self._window_totals = (w_hits, w_peaks, w_steps)

        self.tree.set(window_iid, 'hits', str(w_hits))
        self.tree.set(window_iid, 'peaks', str(w_peaks))
        self.tree.set(window_iid, 'steps', str(w_steps))
        self.tree.set(window_iid, 'hits/step', f'{w_hits_per_step:.3g}')
        self.tree.set(window_iid, 'peaks/step', f'{w_peaks_per_step:.3g}')

        for i, (ok, n) in enumerate(zip(hits, n_peaks)):
            if not ok:
                continue
            step_name = f'Step {i:d}'
            step_iid = self._step_iid(window, scan, i)
            geom = f'{"xy"[axis]}: {(x0, y0)[axis] + i * step}'
            values = (geom, '', int(n), '', '', '')
            self.tree.insert(scan_iid, tk.END, iid=step_iid, text=step_name, values=values)


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
