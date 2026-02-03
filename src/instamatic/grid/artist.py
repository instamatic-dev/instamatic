from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter

if TYPE_CHECKING:
    from instamatic.grid.window import ConvexPolygonWindow


def plot(
    windows: Dict[int, ConvexPolygonWindow],
    ax: Optional[Axes] = None,
    show_indices: bool = True,
    show_axes: bool = True,
    debug_edges: bool = False,
    figsize: tuple[float, float] = (5, 5),
    dpi: int = 100,
) -> tuple[Figure, Axes]:
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

    for idx, window in windows.items():
        corners = np.asarray(window.corners, dtype=float)
        ax.add_patch(Polygon(corners, **patch_kw))

        if show_indices:
            cx, cy = map(float, window.center)
            ax.text(cx, cy, str(idx), **text_kw)

        if debug_edges and hasattr(window, '_edge_xys'):
            xys = np.asarray(window._edge_xys, dtype=float)
            ax.plot(xys[:, 0], xys[:, 1], 'bx', markersize=6, zorder=5)

    ax.autoscale()

    if show_axes:
        ax.axhline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)
        ax.axvline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)

    return fig, ax
