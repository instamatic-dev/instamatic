from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import chain
from typing import Literal, Optional, Union

import numpy as np
from scipy.optimize import minimize
from typing_extensions import Self

from instamatic._typing import float_nm
from instamatic.controller import TEMController, _ctrl, initialize
from instamatic.grid.sweepers import BinaryEdgeSweeper, EdgeSweeperTeam, MarchingEdgeSweeper
from instamatic.utils.iterating import pairwise

if not _ctrl:
    _ctrl: TEMController = initialize()


X = np.array([1, 0], dtype=float)
Y = np.array([0, 1], dtype=float)


WindowGeometryTuple = tuple[float_nm, float_nm, float, float_nm, Optional[float_nm]]


def versor(
    *,
    deg: Optional[Union[float, np.ndarray]] = None,
    rad: Optional[Union[float, np.ndarray]] = None,
) -> np.ndarray:
    """A versor in the direction of angle expressed in radians or degrees."""
    radians = np.deg2rad(deg) if rad is None else rad
    return np.array([np.cos(radians), np.sin(radians)], dtype=float)


class Window(ABC):
    """Describes an arbitrary single window on a TEM grid."""

    center: np.ndarray = ...  # 2-element array describing the center of window


class ConvexPolygonWindow(Window):
    """Describes any convex polygon TEM grid window with known corners."""

    corners: np.ndarray = ...  # a Nx2 ordered array of xy corner coordinates

    def x_intersections(self, y: float_nm) -> Optional[tuple[float, float]]:
        """Return (x_min, x_max) for a horizontal line intersecting at y."""
        intersection_xs: list[float] = []
        for (x1, y1), (x2, y2) in pairwise(self.corners, closed=True):
            if y1 == y2:  # edge case (degeneracy / double counting)
                continue
            intersection_fraction = (y - y1) / (y2 - y1)
            if not 0 < intersection_fraction < 1:
                continue  # does not intersect
            intersection_xs.append(x1 + (x2 - x1) * intersection_fraction)
        if len(intersection_xs) < 2:
            return None
        return min(intersection_xs), max(intersection_xs)

    def y_intersections(self, x: float_nm) -> Optional[tuple[float, float]]:
        """Return (y_min, y_max) for a vertical line intersecting at x."""
        intersection_ys: list[float] = []
        for (x1, y1), (x2, y2) in pairwise(self.corners, closed=True):
            if x1 == x2:  # edge case (degeneracy / double counting)
                continue
            intersection_fraction = (x - x1) / (x2 - x1)
            if not 0 < intersection_fraction < 1:
                continue  # does not intersect
            intersection_ys.append(y1 + (y2 - y1) * intersection_fraction)
        if len(intersection_ys) < 2:
            return None
        return min(intersection_ys), max(intersection_ys)


class GridablePolygonWindow(ConvexPolygonWindow):
    """Describes a polygon window with a 2D (a, b) grid coordinate system.

    This kind of window is expected to exist in a periodic grid,
    therefore it should include an internal coordinate system with two
    axes "a" and "b". They should be selected in such a way that the
    angle between axes "a" and X is minimal and the angle from "a" to
    "b" is positive and minimal. The length of "a" and "b" should match
    the distance between window center and its edge.

    Any subclass of GridablePolygonWindow should initialize using at least
    four following parameters in this order, and other as needed:

    - x: x coordinate of the window center in the stage XY coordinate system;
    - y: y coordinate of the window center in the stage XY coordinate system;
    - t: smallest signed angle from stage +X axis towards "a" axis in degrees;
    - w: double the distance between window center and its' edge midpoint;
    """

    INTERIOR_ANGLE: float = ...  # class attribute: angle between a and b axes
    USES_HEIGHT: bool = ...  # True if a secondary metric i.e. height is needed
    a: np.ndarray = ...
    b: np.ndarray = ...  # from center towards the side, not aligned with ~X

    def __init__(
        self,
        x: float_nm,
        y: float_nm,
        t: float,
        w: float_nm,
        h: Optional[float_nm] = None,
    ) -> None:
        """A uniform abstract constructor for all subclasses (nm/degrees)."""
        self.x: float_nm = float(x)
        self.y: float_nm = float(y)
        self.t: float = float(t)
        self.w: float_nm = float(w)
        self.h: float_nm = self.w if h is None else float(h)

        self.a: np.ndarray = ...  # vector aligned with ~X direction
        self.b: np.ndarray = ...  # "a" rotated by INTERIOR_ANGLE anti-clockwise
        self.corners: np.ndarray = ...  # ordered anti-clockwise, start from "a"

    def __repr__(self) -> str:
        """Accurate representation, show params as floats (from to_params)."""
        p = self.to_params()
        parts = [f'{k}={float(v)}' for k, v in p.items()]
        return f'{type(self).__name__}(' + ', '.join(parts) + ')'

    def __str__(self) -> str:
        """Nicely display self, show params as integers (from to_params)."""
        p = self.to_params()
        parts = [f'{k}={int(np.rint(float(v)))}' for k, v in p.items()]
        return f'{type(self).__name__}(' + ', '.join(parts) + ')'

    @property
    def center(self) -> np.ndarray:
        return np.array([self.x, self.y], dtype=float)

    def edge_residuals(self, xys: np.ndarray) -> np.ndarray:
        """Return residual distance to the nearest edge per point."""
        xys = np.asarray(xys, dtype=float)
        if len(xys) == 0:
            return np.empty(0, dtype=float)

        p1 = np.asarray(self.corners, dtype=float)  # (M, 2)
        edge_vecs = np.roll(p1, -1, axis=0) - p1  # (M, 2)
        edge_l2 = np.sum(edge_vecs * edge_vecs, axis=1)  # (M,)

        if np.any(edge_l2 == 0):
            raise ValueError('Degenerate polygon edge: consecutive corners coincide')

        # Vector from each segment start to each point
        rel = xys[:, None, :] - p1[None, :, :]  # (N, M, 2)

        # Projection parameter onto each edge, then clamp to the finite segment
        t = np.sum(rel * edge_vecs[None, :, :], axis=2) / edge_l2[None, :]  # (N, M)
        t = np.clip(t, 0.0, 1.0)

        # Closest point on each segment
        closest = p1[None, :, :] + t[:, :, None] * edge_vecs[None, :, :]  # (N, M, 2)

        # Distance from each point to each segment
        dists = np.linalg.norm(xys[:, None, :] - closest, axis=2)  # (N, M)

        return np.min(dists, axis=1)

    @classmethod
    def from_sweeping(cls, order: Literal[1, 2, 3, 4, 5] = 3) -> Self:
        """Return new using `EdgeSweeper`s scanning around current position."""
        origin = np.array(_ctrl.stage.xy, dtype=int)
        team = str(origin)
        _ = EdgeSweeperTeam(name=team)

        # define and sweep with initial marching sweepers to approx. grid center
        dirs = [+X, +Y, -X, -Y]
        mess = [MarchingEdgeSweeper(origin=origin, heading=d, team=team) for d in dirs]
        for mes in mess:
            mes.sweep()
        center_x = (mess[0].position[0] + mess[2].position[0]) / 2
        center_y = (mess[1].position[1] + mess[3].position[1]) / 2
        center = np.array([center_x, center_y], dtype=float)

        # define binary sweepers, step to edge of marchers-probed region & sweep
        mess_position_pairs = list(pairwise([mes.position for mes in mess], closed=True))
        bess = [BinaryEdgeSweeper(origin=center, heading=d, team=team) for d in (X, Y, -X, -Y)]
        for bes in bess:
            dists = [bes.dist2segment(*p1, *p2) for p1, p2 in mess_position_pairs]
            safe_dist = min(dists) - bes.team.step_size
            if np.isfinite(safe_dist) and safe_dist > 0:
                bes.step(safe_dist)
            bes.sweep()

        # for each order, create a new generation of beam sweepers and sweep
        def bisectors(sweepers: list[BinaryEdgeSweeper]) -> list[BinaryEdgeSweeper]:
            new = [a.breed(b) for a, b in pairwise(sweepers, closed=True)]
            for ns in new:
                ns.sweep()
            return new

        for _ in range(1, order):
            bess = list(chain.from_iterable(zip(bess, bisectors(bess))))

        edge_xy = np.vstack([bes.position for bes in bess])  # Nx2
        return cls.from_edge_xys(edge_xy)

    # @classmethod
    # @abstractmethod
    # def from_edge_xys(cls, edge_xys: np.ndarray) -> Self: ...
    # TODO: implement non-abstract based on the geometry implementation w/ no spacing

    def intersects_limits(self, x: float_nm, y: float_nm) -> bool:
        """Test whether the window intersects the box [-x, x] x [-y, y]. To
        this aim, in seven consecutive blocks:

        1) Alias the corners and their coordinates for further
        convenience; 2) Test whether the window bounding box (min/max)
        is beyond limits; 3) Test whether any window corner is inside
        the limits; 4) to 7) Test if any limit line intersects the
        window within limits.
        """
        c = np.asarray(self.corners, dtype=float)  # window corners
        cx = c[:, 0]  # view of window corners' x coordinates
        cy = c[:, 1]  # view of window corners' x coordinates

        if cx.max() < -x or cx.min() > x or cy.max() < -y or cy.min() > y:
            return False

        if np.any((cx > -x) & (cx < x) & (cy > -y) & (cy < y)):
            return True

        xs = self.x_intersections(y=y)
        if xs is not None and xs[0] < x and xs[1] > -x:
            return True

        xs = self.x_intersections(y=-y)
        if xs is not None and xs[0] < x and xs[1] > -x:
            return True

        ys = self.y_intersections(x=x)
        if ys is not None and ys[0] < y and ys[1] > -y:
            return True

        ys = self.y_intersections(x=-x)
        if ys is not None and ys[0] < y and ys[1] > -y:
            return True

        return False

    @abstractmethod
    def to_params(self) -> dict[str, float]: ...


class HexagonalWindow(GridablePolygonWindow):
    """A regular hexagonal window with a 2D "ab" coordinate system."""

    INTERIOR_ANGLE: float = 60.0
    ROT60MAT = np.array([[1, -np.sqrt(3)], [np.sqrt(3), 1]], dtype=float) / 2
    USES_HEIGHT = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.a = 0.5 * self.w * versor(deg=self.t).T
        self.b = self.ROT60MAT @ self.a

        angles = self.t + np.array([30, 90, 150, 210, 270, 330], dtype=float)
        self.corners = self.center + self.w / np.sqrt(3.0) * versor(deg=angles).T

    def to_params(self) -> dict[str, float]:
        return {'x': self.x, 'y': self.y, 't': self.t, 'w': self.w}

    def translated(self, delta: np.ndarray) -> Self:
        """Return a new window translated by (dx, dy) in nm."""
        d = np.asarray(delta, dtype=float)
        return type(self)(self.x + d[0], self.y + d[1], self.t, self.w)


class RectangularWindow(GridablePolygonWindow):
    """Describes one rectangular window with a 2D ab coordinate system.

    Geometry is described using five immutable float scalars (nm / degree):

    - center_x: coordinate of the window center on the X axis;
    - center_y: coordinate of the window center on the Y axis;
    - width: length of window side aligned with the direction of X axis;
    - height: length of window side aligned with the direction or Y axis;
    - theta: signed angle from X axis towards A axis and the X-aligned edge.
    """

    INTERIOR_ANGLE: float = 90.0
    USES_HEIGHT = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        c = self.center
        self.a = a = 0.5 * self.w * versor(deg=self.t)
        self.b = b = 0.5 * self.h * versor(deg=self.t + 90)
        self.corners = np.vstack([c + a + b, c + a - b, c - a - b, c - a + b])

    def to_params(self) -> dict[str, float]:
        return {'x': self.x, 'y': self.y, 't': self.t, 'w': self.w, 'h': self.h}

    def translated(self, delta: np.ndarray) -> Self:
        """Return a new window translated by (dx, dy) in nm."""
        d = np.asarray(delta, dtype=float)
        return type(self)(self.x + d[0], self.y + d[1], self.t, self.w, self.h)


class SquareWindow(RectangularWindow):
    """A regular square window with a 2D "ab" coordinate system."""

    USES_HEIGHT = False

    def to_params(self) -> dict[str, float]:
        return {'x': self.x, 'y': self.y, 't': self.t, 'w': self.w}

    def translated(self, delta: np.ndarray) -> Self:
        """Return a new window translated by (dx, dy) in nm."""
        d = np.asarray(delta, dtype=float)
        return type(self)(self.x + d[0], self.y + d[1], self.t, self.w)
