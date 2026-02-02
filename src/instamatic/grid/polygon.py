from __future__ import annotations

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter


def plot(self, show: bool = True) -> tuple[Figure, Axes]:
    """Plot grid windows as white polygons on black bg with Ulam labels."""

    fig, ax = plt.subplots(figsize=(5, 5), dpi=100)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')

    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('x / um', color='white')
    ax.set_ylabel('y / um', color='white')

    ax.tick_params(colors='white', direction='out')
    for spine in ax.spines.values():
        spine.set_color('white')

    if not self.windows:
        plt.show()
        return

    patch_kw = {'facecolor': 'white', 'edgecolor': 'white', 'closed': True}
    text_kw = {'color': 'black', 'ha': 'center', 'va': 'center', 'fontsize': 10}
    for ulam_idx, w in self.windows.items():
        corners = np.asarray(w.corners, dtype=float)
        ax.add_patch(Polygon(corners, **patch_kw))
        cx, cy = w.center
        ax.text(cx, cy, str(ulam_idx), **text_kw)

    ax.autoscale()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x * 1e-3:g}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y * 1e-3:g}'))

    # draw explicit x/y axes through origin for orientation
    ax.axhline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)
    ax.axvline(0, color='white', linewidth=1.0, alpha=0.6, zorder=0)

    if show:
        plt.show()
    return fig, ax
