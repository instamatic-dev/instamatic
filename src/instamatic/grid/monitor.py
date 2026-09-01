from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Optional

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from instamatic._typing import AnyPath
from instamatic.grid.artist import plot_grid
from instamatic.grid.finder import GridFinder


class GridMonitor(ttk.Frame):
    """A Tkinter-based GUI to monitor and refine TEM grids."""

    def __init__(self, parent: tk.Widget, grid_path: Optional[AnyPath] = None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.path = tk.StringVar(value=str(grid_path) if grid_path else '')
        self.last_mtime: float = 0.0

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.fig, self.ax = plt.subplots(figsize=(5, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        address_frame = ttk.Frame(self)
        address_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        ttk.Label(address_frame, text='Grid File:').pack(side=tk.LEFT)

        path_entry = ttk.Entry(address_frame, textvariable=self.path)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        browse_btn = ttk.Button(address_frame, text='Browse', command=self._browse_file)
        browse_btn.pack(side=tk.LEFT)

        self.pack(fill=tk.BOTH, expand=True)
        self.after(1000, self._poll_file_updates)

    def _browse_file(self):
        filepath = filedialog.askopenfilename(
            title='Select YAML with grid information',
            filetypes=(('YAML files', '*.yaml *.yml'), ('All files', '*.*')),
        )
        if filepath:
            self.path.set(filepath)
            self.last_mtime = 0.0  # Force a redraw

    def _poll_file_updates(self):
        """Continuously check if the grid YAML file has been modified."""
        grid_path = Path(self.path.get())
        if grid_path and grid_path.exists():
            try:
                current_mtime = grid_path.stat().st_mtime
                if current_mtime > self.last_mtime:
                    self.last_mtime = current_mtime
                    self._redraw_grid()
            except OSError:
                pass

        self.after(1000, self._poll_file_updates)

    def _redraw_grid(self):
        """Load the latest YAML and redraw the matplotlib canvas."""
        grid_path = Path(self.path.get())
        if not grid_path or not grid_path.exists():
            return

        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        gf = GridFinder.from_yaml(grid_path)
        plot_grid(
            grid=gf.grid,
            intercepts=gf.intercepts,
            ax=self.ax,
            show_indices=True,
            show_intercepts=True,
        )
        self.canvas.draw_idle()


def main():
    """GUI program to monitor a grid.yaml file and plot any updates live."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        '-f', '--file', type=str, help='Path to the grid.yaml file', default=None
    )

    args = parser.parse_args()

    root = tk.Tk()
    root.title('Instamatic Grid Monitor')
    _ = GridMonitor(root, grid_path=args.file)
    root.mainloop()


if __name__ == '__main__':
    main()
