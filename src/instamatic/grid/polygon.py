from __future__ import annotations

from typing import Annotated, Generic, TypeVar, Union, cast

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter

from instamatic._collections import VersionedDict
from instamatic._typing import float_nm, int_nm
from instamatic.grid.pairing import *
from instamatic.grid.window import ConvexPolygonWindow, HexagonalWindow, RectangularWindow

DualIndex = tuple[int, int]
UlamIndex = Annotated[int, 'positive']
WindowIndex = Union[DualIndex, UlamIndex]
WindowType = TypeVar('WindowType', bound=ConvexPolygonWindow)


class ConvexPolygonGrid(Generic[WindowType]):
    window_type: type[WindowType]
    pairing_function: PairingFunction
    pairing_inverse: PairingInverse

    def __init__(self) -> None:
        self.windows: VersionedDict[int, WindowType] = VersionedDict()
        self.default_spacing: int_nm = 10_000
        self._spacing_cache_version = 0
        self._spacing = 10_000

    def _estimate_spacing(self) -> float_nm:
        """Estimate actual spacing between all defined windows."""
        if 0 not in self.windows or len(self.windows) < 2:
            return float(self.default_spacing)

        w0 = self.windows[0]
        w_axis = np.asarray(w0.w_axis, dtype=float)
        h_axis = np.asarray(w0.h_axis, dtype=float)
        w_hat = w_axis / np.linalg.norm(w_axis)
        h_hat = h_axis / np.linalg.norm(h_axis)

        ijs = self.windows_ij.astype(float)  # (N,2)
        centers = self.windows_xy.astype(float)  # (N,2)
        deltas = centers - np.asarray(w0.center, dtype=float)

        mask = ~((ijs[:, 0] == 0) & (ijs[:, 1] == 0))
        ijs = ijs[mask]
        deltas = deltas[mask]

        # Solve deltas ≈ [i j] @ [w_step; h_step]
        # i.e. two independent least squares, one per coordinate component.
        m, *_ = np.linalg.lstsq(ijs, deltas, rcond=None)
        step_w, step_h = m[0], m[1]

        # Only use estimates along w/h axis if i/j coordinate changes
        s_candidates: list[float] = []
        if np.any(ijs[:, 0] != 0):
            if np.isfinite(s_w := float(np.dot(step_w - 2.0 * w_axis, w_hat))):
                s_candidates.append(s_w)
        if np.any(ijs[:, 1] != 0):
            if np.isfinite(s_h := float(np.dot(step_h - 2.0 * h_axis, h_hat))):
                s_candidates.append(s_h)

        if not s_candidates:
            return float(self.default_spacing)
        return float(max(0.0, float(np.mean(s_candidates))))

    @property
    def coords(self) -> tuple[np.ndarray, np.ndarray]:
        """Coordinate vectors along "w" and "h" dirs derived from window 0."""
        s = float(self.spacing)
        w0 = self.windows[0]
        step_w = 2.0 * w0.w_axis + s * w0.w_axis / np.linalg.norm(w0.w_axis)
        step_h = 2.0 * w0.h_axis + s * w0.h_axis / np.linalg.norm(w0.h_axis)
        return step_w, step_h

    @property
    def spacing(self) -> float_nm:
        """Cached property of self.windows: stores spacing between windows."""
        if self._spacing_cache_version < self.windows.version:
            self._spacing = self._estimate_spacing()
            self._spacing_cache_version = self.windows.version
        return self._spacing

    @property
    def windows_ij(self) -> np.ndarray:
        """A Nx2 array of all existing window dual indices in windows order."""
        ulam_indices = list(self.windows.keys())
        return np.array([self.pairing_inverse(u) for u in ulam_indices], dtype=int)

    @property
    def windows_xy(self) -> np.ndarray:
        """A Nx2 array of all existing window centers in windows order."""
        return np.array([w.center for w in self.windows.values()], dtype=float)

    def nearest_window(self, idx: WindowIndex) -> UlamIndex:
        """Return Ulam index of existing window nearest to the one with idx."""
        predicted_center = self.predict_center(idx)
        offsets2 = np.sum((self.windows_xy - predicted_center) ** 2, axis=1)
        nearest = int(np.argmin(offsets2))
        return list(self.windows.keys())[nearest]

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

    def predict_center(self, idx: WindowIndex) -> np.ndarray:
        """Predict center position of window idx given the rest of the grid."""
        ij: DualIndex = self.pairing_inverse(idx) if isinstance(idx, int) else idx
        w, h = self.coords
        return self.windows[0].center + w * ij[0] + h * ij[1]

    def predict_window(self, idx: WindowIndex) -> WindowType:
        """Predict the window of index idx given the rest of the grid."""
        w0_delta = self.predict_center(idx) - self.windows[0].center
        return cast(WindowType, self.windows[0].translated(w0_delta))


class HexagonalGrid(ConvexPolygonGrid[HexagonalWindow]):
    window_type = HexagonalWindow
    pairing_function = staticmethod(uv2spiral)
    pairing_inverse = staticmethod(spiral2uv)


class RectangularGrid(ConvexPolygonGrid[RectangularWindow]):
    window_type = RectangularWindow
    pairing_function = staticmethod(ij2ulam)
    pairing_inverse = staticmethod(ulam2ij)


if __name__ == '__main__':
    g = RectangularGrid()
    w0 = RectangularWindow(0, 0, 50_000, 50_000, np.deg2rad(10))
    g.windows[0] = w0
    for i in range(200):
        p = g.predict_window(i)
        if np.linalg.norm(p.center - w0.center) < 400_000:
            g.windows[i] = p

    g.plot()

    h = HexagonalGrid()
    v0 = HexagonalWindow(0, 0, 50_000, np.deg2rad(10))
    h.windows[0] = v0

    for i in range(200):
        q = h.predict_window(i)
        if np.linalg.norm(q.center - v0.center) < 400_000:
            h.windows[i] = q

    h.plot()
