from __future__ import annotations

from typing import Annotated, Generic, Optional, Protocol, Self, TypeVar, Union

import numpy as np
from scipy.optimize import least_squares

from instamatic._collections import NoOverwriteDict
from instamatic._typing import float_nm
from instamatic.grid.window import (
    GridablePolygonWindow,
    HexagonalWindow,
    RectangularWindow,
    SquareWindow,
)
from instamatic.utils.pairing import hulam2uv, ij2ulam, ulam2ij, uv2hulam

DualIndex = tuple[int, int]
SpiralIndex = Annotated[int, 'positive']
WindowIndex = Union[DualIndex, SpiralIndex]
WindowType = TypeVar('WindowType', bound=GridablePolygonWindow)


def versor(
    *,
    deg: Optional[Union[float, np.ndarray]] = None,
    rad: Optional[Union[float, np.ndarray]] = None,
) -> np.ndarray:
    """A versor in the direction of angle expressed in radians or degrees."""
    radians = np.deg2rad(deg) if rad is None else rad
    return np.array([np.cos(radians), np.sin(radians)], dtype=float)


class PairingFunction(Protocol):
    def __call__(self, i: int, j: int, /) -> int: ...


class PairingInverse(Protocol):
    def __call__(self, n: int, /) -> tuple[int, int]: ...


WindowGeometryTuple = tuple[float_nm, float_nm, float, float_nm, Optional[float_nm]]
WindowShapeTuple = tuple[float, float_nm, Optional[float_nm]]


class PeriodicConvexPolygonGrid(Generic[WindowType]):
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

    neighborhood: np.ndarray[int]
    pairing_function: PairingFunction
    pairing_inverse: PairingInverse
    window_type: type[WindowType]

    DEFAULT_SPACING: float_nm = 10_000

    def __init__(
        self,
        x: float_nm,  # x coordinate of the grid origin in stage coordinates
        y: float_nm,  # y coordinate of the grid origin in stage coordinates
        t: float,  # signed angle from the X-axis towards a-vector in degrees
        w: float_nm,  # length of X-aligned axis: edge to edge center-points
        h: Optional[float_nm] = None,  # length of the other axis, if relevant
        s: Optional[float_nm] = None,  # spacing between neighbor grid windows
    ):
        self.x = x
        self.y = y
        self.t = t
        self.w = w
        self._h = h
        self._s = s

    def __repr__(self) -> str:
        params = ', '.join(f'{k}: {v}' for k, v in self.to_params().items())
        return f'{self.__class__.__name__}({params})'

    def normalized(self) -> Self:
        """Align w with X axis by casting theta to [+,- interior angle / 2]"""
        a = float(self.window_type.INTERIOR_ANGLE)
        n = int(np.floor((self.t + 0.5 * a) / a))  # rotates needed to min theta
        t = float(self.t - n * a)
        w = abs(float(self.w))
        h = None if self._h is None else abs(float(self._h))
        if self._h is not None and (n % 2):
            w, h = h, w
        return self.__class__(self.x, self.y, t, w, h, self._s)

    @property
    def origin(self) -> np.ndarray:
        """Origin of the grid i.e. its window 0 in stage coordinates (nm)."""
        return np.array([self.x, self.y], dtype=float)

    @property
    def h(self):
        """Value of "h" if it is applicable or "w" in square/hex cases."""
        return self._h if self.window_type.USES_HEIGHT else self.w

    @h.setter
    def h(self, value: float_nm) -> None:
        self._h = value if self.window_type.USES_HEIGHT else None

    @property
    def s(self):
        """Uniform spacing between two neighbor windows i.e. grid thickness."""
        return self.DEFAULT_SPACING if self._s is None else self._s

    @s.setter
    def s(self, value: float_nm) -> None:
        self._s = value

    @property
    def a_dir(self) -> np.ndarray:
        """A versor oriented along grid space axis "a" in stage coords."""
        t = float(np.radians(self.t))
        return np.array([np.cos(t), np.sin(t)], dtype=float)

    @property
    def a_edge(self) -> np.ndarray:
        """Half-window vector from center to edge midpoint along axis "a"."""
        return (self.w / 2) * self.a_dir

    @property
    def a_grid(self) -> np.ndarray:
        """Center-to-center lattice vector to neighboring window along "a"."""
        return (self.w + self.s) * self.a_dir

    @property
    def b_dir(self) -> np.ndarray:
        """A versor oriented along grid space axis "b" in stage coords."""
        t = float(np.radians(self.t + self.window_type.INTERIOR_ANGLE))
        return np.array([np.cos(t), np.sin(t)], dtype=float)

    @property
    def b_edge(self) -> np.ndarray:
        """Half-window vector from center to edge midpoint along axis "b"."""
        return (self.h / 2) * self.b_dir

    @property
    def b_grid(self) -> np.ndarray:
        """Center-to-center lattice vector to neighboring window along "b"."""
        return (self.h + self.s) * self.b_dir

    def window_geometry(self, idx: WindowIndex) -> WindowGeometryTuple:
        """Return the current geom: origin + shape params of window "idx"."""
        ij: DualIndex = idx if isinstance(idx, tuple) else self.pairing_inverse(idx)
        x, y = self.origin + ij[0] * self.a_grid + ij[1] * self.b_grid
        return x, y, self.t, self.w, self.h

    def window(self, idx: WindowIndex) -> WindowType:
        """Convenience method that makes a window located at requested idx."""
        return self.window_type(*self.window_geometry(idx))

    def windows_in_limits(self, x: float_nm, y: float_nm) -> list[int]:
        """List indices of windows intersecting the box [-x, x] x [-y, y]."""
        candidates_idx: set[int] = {0, self.nearest_index(0.0, 0.0)}
        idx_in_limits: list[int] = []

        while candidates_idx:
            idx = min(candidates_idx)
            candidates_idx.remove(idx)

            if self.window(idx=idx).intersects_limits(x, y):
                idx_in_limits.append(idx)
                for nb in np.array(self.pairing_inverse(idx)) + self.neighborhood:
                    nb_idx = self.pairing_function(int(nb[0]), int(nb[1]))
                    if nb_idx > idx:
                        candidates_idx.add(nb_idx)

        return idx_in_limits

    def nearest_index(self, x: float_nm, y: float_nm) -> int:
        """Return spiral index of predicted window nearest to the center."""
        delta = np.asarray([x, y], dtype=float) - self.origin
        metric = np.column_stack([self.a_grid, self.b_grid])
        ij, *_ = np.linalg.lstsq(metric, delta, rcond=None)
        i, j = (int(np.rint(v)) for v in ij)
        return int(self.pairing_function(i, j))

    @classmethod
    def guess(cls, intercepts: dict[int, np.ndarray]) -> Self:
        """Guess the geometry of window 0 given points on its edges."""
        if 0 not in intercepts:
            raise ValueError('No intercepts for window 0 provided')

        xys0 = np.asarray(intercepts[0], dtype=float)
        c0 = np.mean(xys0, axis=0)
        deltas = xys0 - c0
        half_span = 0.5 * cls.window_type.INTERIOR_ANGLE
        thetas = np.linspace(-half_span, +half_span, 91)

        best_guess = None
        best_score = np.inf

        for t in thetas:
            a_dir = versor(deg=t)
            b_dir = versor(deg=t + cls.window_type.INTERIOR_ANGLE)
            qa = deltas @ a_dir
            qb = deltas @ b_dir

            if cls.window_type.USES_HEIGHT:
                w = 2.0 * np.quantile(np.abs(qa), 0.9)
                h = 2.0 * np.quantile(np.abs(qb), 0.9)
            else:
                w = 2.0 * np.quantile(np.hstack([np.abs(qa), np.abs(qb)]), 0.9)
                h = None

            g = cls(x=c0[0], y=c0[1], t=t, w=w, h=h, s=None)
            score = float(np.sum(g.window(0).edge_residuals(xys0) ** 2))
            if score < best_score:
                best_guess = g
                best_score = score

        assert best_guess is not None
        return best_guess

    def refine(self, intercepts: dict[int, np.ndarray]) -> None:
        """Refine self to match the window_id: intercepts dictionary."""

        windows = sorted(intercepts.keys())
        refine_spacing = len(windows) > 1
        fit_h = self.window_type.USES_HEIGHT
        fixed_s = self._s  # preserve "unknown spacing" when not refined

        def serialize(g: PeriodicConvexPolygonGrid) -> np.ndarray:
            """Express the geometry instance as a series of refined vars."""
            vals = [float(g.x), float(g.y), float(g.t), float(g.w)]
            if fit_h:
                vals.append(float(g.h))
            if refine_spacing:
                vals.append(float(g.s))
            return np.asarray(vals, dtype=float)

        def deserialize(p: np.ndarray) -> PeriodicConvexPolygonGrid:
            """Convert a series of refined vars into a periodic geometry."""
            vals = iter(p)
            x = float(next(vals))
            y = float(next(vals))
            t = float(next(vals))
            w = float(next(vals))
            h = float(next(vals)) if fit_h else None
            s = float(next(vals)) if refine_spacing else fixed_s
            return self.__class__(x=x, y=y, t=t, w=w, h=h, s=s).normalized()

        def residuals(p: np.ndarray) -> np.ndarray:
            """Calculate residual for each window in refined geometry."""
            geom = deserialize(p)
            res: list[np.ndarray] = []
            for idx, xys in intercepts.items():
                tmp_window = geom.window(idx)
                res.append(tmp_window.edge_residuals(xys))
            return np.concatenate(res) if res else np.empty(0, dtype=float)

        lower = [-np.inf, -np.inf, -np.inf, 1e-9]
        upper = [np.inf, np.inf, np.inf, np.inf]
        if fit_h:
            lower.append(1e-9)
            upper.append(np.inf)
        if refine_spacing:
            lower.append(0.0)
            upper.append(np.inf)
        res = least_squares(
            residuals,
            x0=serialize(self),
            bounds=(np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)),
            method='trf',
            loss='soft_l1',
            f_scale=10_000,
        )

        geometry = deserialize(res.x)
        if not refine_spacing:
            geometry._s = fixed_s  # keep spacing unknown/fixed in the 1-window case

        self.x = geometry.x
        self.y = geometry.y
        self.t = geometry.t
        self.w = geometry.w
        self.h = geometry.h
        self.s = geometry._s

    def to_params(self):
        return {'x': self.x, 'y': self.y, 't': self.t, 'w': self.w, 'h': self._h, 's': self._s}


class HexagonalGrid(PeriodicConvexPolygonGrid):
    neighborhood = np.array([(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)], dtype=int)
    pairing_function: PairingFunction = staticmethod(uv2hulam)
    pairing_inverse: PairingInverse = staticmethod(hulam2uv)
    window_type: type[WindowType] = HexagonalWindow


class RectangularGrid(PeriodicConvexPolygonGrid[RectangularWindow]):
    neighborhood = np.array([(1, 0), (0, 1), (-1, 0), (0, -1)], dtype=int)
    pairing_function: PairingFunction = staticmethod(ij2ulam)
    pairing_inverse: PairingInverse = staticmethod(ulam2ij)
    window_type: type[WindowType] = RectangularWindow


class SquareGrid(PeriodicConvexPolygonGrid[SquareWindow]):
    neighborhood = np.array([(1, 0), (0, 1), (-1, 0), (0, -1)], dtype=int)
    pairing_function: PairingFunction = staticmethod(ij2ulam)
    pairing_inverse: PairingInverse = staticmethod(ulam2ij)
    window_type: type[WindowType] = SquareWindow


GRID_REGISTRY = NoOverwriteDict[str, type[PeriodicConvexPolygonGrid]]()
GRID_REGISTRY['hexagonal'] = HexagonalGrid
GRID_REGISTRY['rectangular'] = RectangularGrid
GRID_REGISTRY['square'] = SquareGrid


if __name__ == '__main__':
    import numpy as np

    residuals = {
        0: np.array(
            [
                [572543.92272, 458611.73068],
                [564971.6688, 458611.73068],
                [564971.6688, 458611.73068],
                [564971.6688, 458611.73068],
                [552876.06528, 458609.70234],
                [552876.06528, 458609.70234],
                [538110.39744, 458608.68817],
                [538110.39744, 458608.68817],
                [538110.39744, 458608.68817],
                [518853.20256, 458610.71651],
                [518853.20256, 458610.71651],
                [496719.8544, 458613.75902],
                [496719.8544, 458613.75902],
                [487814.08368, 434983.59802],
                [484349.97072, 421938.32931],
                [484349.97072, 421938.32931],
                [483886.27056, 411164.8014],
                [483886.27056, 411164.8014],
                [486744.23952, 397380.20276],
                [486744.23952, 397380.20276],
                [486744.23952, 397380.20276],
                [486183.55632, 380419.22368],
                [486183.55632, 380419.22368],
                [496566.80304, 365588.0016],
                [496566.80304, 365588.0016],
                [503120.73504, 365593.07245],
                [503120.73504, 365593.07245],
                [511500.67584, 365799.96313],
                [511500.67584, 365799.96313],
                [520806.5016, 366044.3781],
                [520806.5016, 366044.3781],
                [532121.69472, 366439.9044],
                [543770.26704, 366439.9044],
                [543770.26704, 366439.9044],
                [555862.83984, 366764.4388],
                [555862.83984, 366764.4388],
                [568560.04128, 367445.96104],
                [568560.04128, 367445.96104],
                [572369.65632, 406690.28336],
                [576968.77392, 419188.91444],
                [575013.95952, 431882.26616],
                [572419.6632, 441778.53702],
                [572422.69392, 454949.56281],
            ]
        )
    }
    a = SquareGrid(10000, 20000, 0, 50000)
    print(a.guess(residuals).to_params())
    print(a.to_params())
    a.refine(residuals)
    print(a.to_params())
    a = a.guess(residuals)
    a.refine(residuals)
    print(a.to_params())
