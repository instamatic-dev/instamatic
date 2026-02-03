from __future__ import annotations

from typing import Annotated, Generic, Protocol, Sequence, TypeVar, Union, cast

import numpy as np

from instamatic._collections import VersionedDict
from instamatic._typing import float_nm, int_nm
from instamatic.grid.window import GridablePolygonWindow

DualIndex = tuple[int, int]
SpiralIndex = Annotated[int, 'positive']
WindowIndex = Union[DualIndex, SpiralIndex]
WindowType = TypeVar('WindowType', bound=GridablePolygonWindow)


class PairingFunction(Protocol):
    def __call__(self, i: int, j: int, /) -> int: ...


class PairingInverse(Protocol):
    def __call__(self, n: int, /) -> tuple[int, int]: ...


class Grid(Generic[WindowType]):
    """Abstract base class for any TEM grid.

    Container for grid windows. Lists and documents class methods and
    attributes that must be implemented or work when inherited by every
    grid.
    """

    window_type: type[WindowType]

    def __init__(self, windows: dict[int, WindowType] = None) -> None:
        self.windows: VersionedDict[int, WindowType] = VersionedDict(windows or {})


class ConvexPolygonGrid(Grid[WindowType]):
    """A grid where all windows are convex polygons."""


class PeriodicConvexPolygonGrid(ConvexPolygonGrid[WindowType]):
    """A ConvexPolygonGrid with identical windows and on a 2D ab-lattice.

    The conventional, most-expected lattice kind for ED experiments.
    Every window is an identical convex polygon placed in the same
    distance from other windows, as determined by the grid support
    thickness. Utilizes internal coordinate system of its "central"
    window 0, with two axes, "a" & "b", selected in such a way that the
    angle between axes "a" and coordinate X is minimal, and the angle
    from "a" to "b" is positive (clockwise) and minimal. The length of
    "a" and "b" should match expected distance to next windows.
    """

    pairing_function: PairingFunction
    pairing_inverse: PairingInverse

    def __init__(self, windows: dict[int, WindowType] = None, spacing: int = 10_000) -> None:
        super().__init__(windows)
        self.default_spacing: int_nm = spacing
        self._spacing_cache_version = 0
        self._spacing = spacing

    @property
    def a(self) -> np.ndarray:
        """Grid coordinate vector aligned with X pointing to next window."""
        w0 = self.windows[0]
        return w0.a * (2.0 + float(self.spacing) / np.linalg.norm(w0.a))

    @property
    def b(self) -> np.ndarray:
        """Second grid coordinate vector (not ~X) pointing to next window."""
        w0 = self.windows[0]
        return w0.b * (2.0 + float(self.spacing) / np.linalg.norm(w0.b))

    @property
    def spacing(self) -> float_nm:
        """Cached property of self.windows: stores spacing between windows."""
        if self._spacing_cache_version < self.windows.version:
            self._spacing = self._estimate_spacing()
            self._spacing_cache_version = self.windows.version
        return self._spacing

    def _estimate_spacing(self) -> float_nm:
        """Estimate actual spacing found between all defined grid windows."""
        if 0 not in self.windows or len(self.windows) < 2:
            return float(self.default_spacing)

        w0 = self.windows[0]
        a_axis = np.asarray(w0.a, dtype=float)
        b_axis = np.asarray(w0.b, dtype=float)
        a_hat = a_axis / np.linalg.norm(a_axis)
        b_hat = b_axis / np.linalg.norm(b_axis)

        ijs = self.windows_ij.astype(float)  # (N,2)
        centers = self.windows_xy.astype(float)  # (N,2)
        deltas = centers - np.asarray(w0.center, dtype=float)

        mask = ~((ijs[:, 0] == 0) & (ijs[:, 1] == 0))
        ijs = ijs[mask]
        deltas = deltas[mask]

        # Solve deltas ≈ [i j] @ [a_step; b_step]
        # i.e. two independent least squares, one per coordinate component.
        m, *_ = np.linalg.lstsq(ijs, deltas, rcond=None)
        step_a, step_b = m[0], m[1]

        # Only use estimates along a/b axis if i/j coordinate changes
        spacing_candidates: list[float] = []
        if np.any(ijs[:, 0] != 0):
            if np.isfinite(s_w := float(np.dot(step_a - 2.0 * a_axis, a_hat))):
                spacing_candidates.append(s_w)
        if np.any(ijs[:, 1] != 0):
            if np.isfinite(s_h := float(np.dot(step_b - 2.0 * b_axis, b_hat))):
                spacing_candidates.append(s_h)

        if not spacing_candidates:
            return float(self.default_spacing)
        return float(max(0.0, float(np.mean(spacing_candidates))))

    @property
    def windows_ij(self) -> np.ndarray:
        """A Nx2 array of all existing window dual indices in windows order."""
        ulam_indices = list(self.windows.keys())
        return np.array([self.pairing_inverse(u) for u in ulam_indices], dtype=int)

    @property
    def windows_xy(self) -> np.ndarray:
        """A Nx2 array of all existing window centers in windows order."""
        return np.array([w.center for w in self.windows.values()], dtype=float)

    def nearest_window(self, idx: WindowIndex) -> SpiralIndex:
        """Return spiral index of existing window nearest to the one w/ idx."""
        predicted_center = self.predict_center(idx)
        offsets2 = np.sum((self.windows_xy - predicted_center) ** 2, axis=1)
        nearest = int(np.argmin(offsets2))
        return list(self.windows.keys())[nearest]

    def predict_center(self, idx: WindowIndex) -> np.ndarray:
        """Predict center position of window idx given the rest of the grid."""
        ij: DualIndex = self.pairing_inverse(idx) if isinstance(idx, int) else idx
        return self.windows[0].center + self.a * ij[0] + self.b * ij[1]

    def predict_index(self, center: Sequence[float]) -> int:
        """Return spiral index of predicted window nearest to the center."""
        delta = np.asarray(center, dtype=float) - self.windows[0].center
        metric = np.column_stack([self.a, self.b])
        ij, *_ = np.linalg.lstsq(metric, delta, rcond=None)
        i, j = (int(np.rint(v)) for v in ij)
        return int(self.pairing_function(i, j))

    def predict_window(self, idx: WindowIndex) -> WindowType:
        """Predict the window of index idx given the rest of the grid."""
        w0_delta = self.predict_center(idx) - self.windows[0].center
        return cast(WindowType, self.windows[0].translated(w0_delta))
