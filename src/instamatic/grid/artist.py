from __future__ import annotations

import traceback
from typing import Optional

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter

from instamatic._typing import float_nm
from instamatic.grid.geometry import PeriodicConvexPolygonGridGeometry


def plot(
    geometry: PeriodicConvexPolygonGridGeometry,
    *,
    intercepts: Optional[dict[int, np.ndarray]] = None,
    limit_x: Optional[float_nm] = None,
    limit_y: Optional[float_nm] = None,
    ax: Optional[Axes] = None,
    lines: Optional[pd.DataFrame] = None,
    scans: Optional[pd.DataFrame] = None,
    steps: Optional[pd.DataFrame] = None,
    show_indices: bool = True,
    show_intercepts: bool = False,
    figsize: tuple[float, float] = (5, 5),
    dpi: int = 100,
) -> tuple[Figure, Axes]:
    """Draw geometry with windows based on intercepts dict or limit_x/y."""

    fig, ax = (ax.figure, ax) if ax else plt.subplots(figsize=figsize, dpi=dpi)

    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.set_aspect('equal', adjustable='box')
    ax.tick_params(colors='white', direction='out')
    for spine in ax.spines.values():
        spine.set_color('white')
    ax.set_xlabel('x / um', color='white')
    ax.set_ylabel('y / um', color='white')
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x * 1e-3:g}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y * 1e-3:g}'))
    ax.grid(True, which='major', color='white', linewidth=0.8, alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    patch_kw = {'facecolor': 'white', 'edgecolor': 'white', 'closed': True, 'zorder': 1}
    text_kw = {'color': 'black', 'ha': 'center', 'va': 'center', 'fontsize': 10, 'zorder': 2}

    indices = sorted(intercepts) if intercepts else list(range(25))
    if limit_x is not None and limit_y is not None:
        indices = geometry.windows_in_limits(x=limit_x, y=limit_y)

    for idx in indices:
        window = geometry.window(idx)
        corners = np.asarray(window.corners, dtype=float)
        ax.add_patch(Polygon(corners, **patch_kw))

        if show_indices:
            cx, cy = map(float, window.center)
            ax.text(cx, cy, str(idx), **text_kw)

        if show_intercepts and intercepts and idx in intercepts:
            xys = np.asarray(intercepts[idx], dtype=float)
            ax.plot(xys[:, 0], xys[:, 1], 'bx', markersize=6, zorder=5)

    ax.relim()
    ax.autoscale_view()

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    r = 0.5 * max(x1 - x0, y1 - y0)
    ax.set_xlim(cx - r, cx + r)
    ax.set_ylim(cy - r, cy + r)

    ax.set_autoscale_on(False)  # Freeze limits so lines don't affect view
    ax.axhline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)
    ax.axvline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)

    # draw imshow with light and hits, if lines, scans, and steps are given
    # TODO: lines, scans, steps belong strictly to ScanED - move it there
    try:
        if all(x is not None and not x.empty for x in [lines, scans, steps]):
            slow_idx = 'y0' if (lines['axis'] == 0).all() else 'x0'
            fast_idx = 'x0' if (lines['axis'] == 0).all() else 'y0'

            max_offset = scans['offset'].abs().max()

            if (fast_step := lines['step'].abs().mean()) == 0:
                raise ValueError(f'{fast_step=}: scan data missing or corrupt')
            fast_start = lines[fast_idx]
            fast_end = lines[fast_idx] + lines['step'] * lines['n_steps']
            fast_min = np.minimum(fast_start, fast_end).min() - max_offset
            fast_max = np.maximum(fast_start, fast_end).max() + max_offset
            fast_count = np.ceil((fast_max - fast_min) / fast_step).astype(int)

            slows = lines[slow_idx]
            try:
                slow_step = (np.max(slows) - np.min(slows)) / (len(slows) - 1)
            except ZeroDivisionError:
                slow_step = fast_step  # fallback in case of a single scan
            slow_min = np.min(slows) - 0.5 * slow_step
            slow_max = np.max(slows) + 0.5 * slow_step
            slow_count = len(slows)

            level = ['region', 'line', 'scan']
            hits = {k: g['hits'].to_numpy(dtype=float) for k, g in steps.groupby(level=level)}

            hits_matrix = np.zeros(shape=(slow_count, fast_count), dtype=float)
            for (region, line), line_row in lines.iterrows():
                slow = line_row[slow_idx]
                step = int(line_row['step'])
                n_steps = int(line_row['n_steps'])
                fast0 = float(line_row[fast_idx])
                i = int((slow - slow_min) // slow_step)

                sc = scans.loc[(region, line)]
                offsets = sc['offset'].to_numpy()
                hits_array = np.stack([hits[(region, line, s)] for s in sc.index], axis=0)
                if step < 0:  # reverse dir: flip hit matrix and recalculate fast0
                    hits_array = hits_array[:, ::-1]
                    fast0 = fast0 + step * (n_steps - 1)
                j0s = np.floor((fast0 - fast_min + offsets) / fast_step).astype(int)

                for k in range(len(j0s)):
                    j0 = j0s[k]
                    j0c = max(0, j0)
                    j1c = min(fast_count, j0 + n_steps)
                    if j0c < j1c:
                        hits_matrix[i, j0c:j1c] += hits_array[k][j0c - j0 : j1c - j0]

            if fast_idx == 'x0':
                x0, x1, y0, y1 = fast_min, fast_max, slow_min, slow_max
            else:
                x0, x1, y0, y1 = slow_min, slow_max, fast_min, fast_max
                hits_matrix = hits_matrix.T

            rgba = np.zeros((*hits_matrix.shape, 4), dtype=np.float32)
            if (hits_max := hits_matrix.max()) > 0:
                rgba[..., 0] = 1.0  # red square with opacity ~ hit density
                rgba[..., 3] = hits_matrix / hits_max
            ax.imshow(rgba, origin='lower', extent=(x0, x1, y0, y1), aspect='auto', zorder=3)
            ax.set_aspect('equal', adjustable='box')
    except (KeyError, ValueError):
        traceback.print_exc()  # if fails, not my largest concern

    if limit_x is not None:
        ax.axvline(-limit_x, color='red', linewidth=1.0, zorder=4)
        ax.axvline(limit_x, color='red', linewidth=1.0, zorder=4)
    if limit_y is not None:
        ax.axhline(-limit_y, color='red', linewidth=1.0, zorder=4)
        ax.axhline(limit_y, color='red', linewidth=1.0, zorder=4)

    return fig, ax


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import numpy as np

    from instamatic.grid.geometry import *

    common = {'x': 0, 'y': 0, 't': 0}
    g1 = HexagonalGridGeometry(w=50_000, **common)
    g2 = RectangularGridGeometry(w=40_000, h=60_000, **common)
    g3 = RectangularGridGeometry(w=40_000, h=200_000, **common)
    g4 = SquareGridGeometry(w=50_000, **common)

    fig, axs = plt.subplots(2, 2)
    fig.tight_layout()
    plot(g1, ax=axs[0, 0], limit_x=200_000, limit_y=200_000)
    plot(g2, ax=axs[0, 1], limit_x=200_000, limit_y=200_000)
    plot(g3, ax=axs[1, 0], limit_x=200_000, limit_y=200_000)
    plot(g4, ax=axs[1, 1], limit_x=200_000, limit_y=200_000)

    plt.show()
