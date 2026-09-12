from __future__ import annotations

from typing import Optional

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter

from instamatic._typing import float_nm
from instamatic.grid import Intercepts
from instamatic.grid.grid import PeriodicConvexPolygonGrid


def plot_grid(
    grid: PeriodicConvexPolygonGrid,
    *,
    intercepts: Optional[Intercepts] = None,
    limit_x: Optional[float_nm] = None,
    limit_y: Optional[float_nm] = None,
    ax: Optional[Axes] = None,
    show_indices: bool = True,
    show_intercepts: bool = True,
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
        indices = grid.windows_in_limits(x=limit_x, y=limit_y)

    cmap = plt.colormaps.get_cmap('tab10')
    for idx in indices:
        try:
            window = grid.window(idx)
        except ValueError:  # negative/invalid Ulam index
            color = '#808080'
        else:
            color = cmap(idx % 10)
            corners = np.asarray(window.corners, dtype=float)
            ax.add_patch(Polygon(corners, **patch_kw))
            if show_indices:
                cx, cy = map(float, window.center)
                ax.text(cx, cy, str(idx), **text_kw)

        if show_intercepts and intercepts and idx in intercepts:
            xys = np.asarray(intercepts[idx], dtype=float)
            ax.plot(
                xys[:, 0],
                xys[:, 1],
                marker='x',
                linestyle='',
                color=color,
                markersize=6,
                zorder=5,
            )

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

    if limit_x is not None:
        ax.axvline(-limit_x, color='red', linewidth=1.0, zorder=4)
        ax.axvline(limit_x, color='red', linewidth=1.0, zorder=4)
    if limit_y is not None:
        ax.axhline(-limit_y, color='red', linewidth=1.0, zorder=4)
        ax.axhline(limit_y, color='red', linewidth=1.0, zorder=4)

    return fig, ax
