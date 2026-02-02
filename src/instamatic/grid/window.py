from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import chain
from typing import Literal, Optional, Sequence

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Polygon
from scipy.optimize import minimize
from typing_extensions import Self

from instamatic._typing import float_nm, int_nm
from instamatic.controller import TEMController, _ctrl, initialize
from instamatic.grid.sweepers import BinaryEdgeSweeper, EdgeSweeperTeam, MarchingEdgeSweeper
from instamatic.utils.iterating import pairwise

if not _ctrl:
    _ctrl: TEMController = initialize()


X = np.array([1, 0], dtype=float)
Y = np.array([0, 1], dtype=float)


class Window(ABC):
    """Describes an arbitrary single window on a TEM grid."""

    center: np.ndarray = ...  # 2-element array describing the center of window


class ConvexPolygonWindow(Window):
    """Describes any convex polygon TEM grid window with known corners."""

    corners: np.ndarray = ...  # a Nx2 ordered array of xy corner coordinates

    def plot(self, ax=None, pad: float = 0.1) -> None:
        """Plot a simple visual representation of the window geometry."""
        if ax is None:
            _, ax = plt.subplots()

        corners = self.corners
        cx, cy = self.center
        xmin, ymin = corners.min(axis=0)
        xmax, ymax = corners.max(axis=0)
        dx, dy = xmax - xmin, ymax - ymin

        ax.set_facecolor('0.85')
        ax.add_patch(
            Polygon(
                corners,
                closed=True,
                facecolor='white',
                edgecolor='black',
                linewidth=1.5,
                zorder=1,
            )
        )

        ax.plot(corners[:, 0], corners[:, 1], 'ro', zorder=2)
        ax.plot(cx, cy, 'r+', markersize=10, markeredgewidth=2, zorder=3)

        if hasattr(self, '_edge_xys'):
            xys = self._edge_xys
            ax.plot(xys[:, 0], xys[:, 1], 'bx', markersize=6, zorder=5)

        ax.set_aspect('equal', adjustable='box')
        ax.set_xlim(xmin - pad * dx, xmax + pad * dx)
        ax.set_ylim(ymin - pad * dy, ymax + pad * dy)
        ax.set_xlabel('x / nm')
        ax.set_ylabel('y / nm')

        plt.show()

    def x_intersections(self, y: float_nm) -> Optional[tuple[float, float]]:
        """Return (x_min, x_max) for a horizontal line intersecting at y."""
        intersection_xs: list[float] = []
        for x1, y1, x2, y2 in pairwise(self.corners, closed=True):
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
        for x1, y1, x2, y2 in pairwise(self.corners, closed=True):
            if x1 == x2:  # edge case (degeneracy / double counting)
                continue
            intersection_fraction = (x - x1) / (x2 - x1)
            if not 0 < intersection_fraction < 1:
                continue  # does not intersect
            intersection_ys.append(y1 + (y2 - y1) * intersection_fraction)
        if len(intersection_ys) < 2:
            return None
        return min(intersection_ys), max(intersection_ys)


class RegularPolygonWindow(Window):
    """Describes regular polygon window with a 2D ab coordinate system.

    This kind of window is expected to exist in a periodic grid,
    therefore it should include an internal coordinate system with two
    axes "a" and "b". They should be selected in such a way that the
    angle between axes "a" and X is minimal and the angle from "a" to
    "b" is positive and minimal. The length of "a" and "b" should match
    the distance between window center and its edge.
    """

    a: np.ndarray = ...  # from center towards the side, aligned in ~X direction
    b: np.ndarray = ...  # from center towards the side, not aligned with ~X

    @abstractmethod
    def __repr__(self) -> str: ...

    @classmethod
    def from_sweeping(cls, order: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10] = 3) -> Self:
        """Return new using `EdgeSweeper`s scanning around current position."""
        origin = np.array(_ctrl.stage.xy, dtype=int)
        team = str(origin)
        _ = EdgeSweeperTeam(name=team)

        # define and sweep with initial marching sweepers to approx. grid center
        dirs = [+X, -X, +Y, -Y]
        mess = [MarchingEdgeSweeper(origin=origin, heading=d, team=team) for d in dirs]
        for mes in mess:
            mes.sweep()
        center_x = (mess[0].position[0] + mess[1].position[0]) / 2
        center_y = (mess[2].position[1] + mess[3].position[1]) / 2
        center = np.array([center_x, center_y], dtype=float)

        # define binary sweepers, step to edge of marchers-probed region & sweep
        mess_position_pairs = list(pairwise([mes.position for mes in mess], closed=True))
        bess = [BinaryEdgeSweeper(origin=center, heading=d) for d in (X, Y, -X, -Y)]
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

    @classmethod
    @abstractmethod
    def from_edge_xys(cls, edge_xy: np.ndarray) -> Self: ...


class HexagonalWindow(RegularPolygonWindow):
    """Describes a regular hexagonal window with a 2D ab coordinate system.

    Geometry is described using four immutable float scalars (nm / radian):

    - center_x: coordinate of the window center on the X axis;
    - center_y: coordinate of the window center on the Y axis;
    - width: distance between two opposite sides ("flat-to-flat");
    - theta: signed angle from world X axis towards the +a axis direction.
    """

    ROT60MAT = np.array([[1, -np.sqrt(3)], [np.sqrt(3), 1]], dtype=float) / 2

    def __init__(self, x: float, y: float, w: float, t: float):
        t = (t + (np.pi / 6)) % (np.pi / 3) - (np.pi / 6)  # cast to [-pi/6, pi/6]
        self.center_x: float_nm = x
        self.center_y: float_nm = y
        self.width = w = abs(w)
        self.theta: float = t

        self.center = c = np.array([x, y], dtype=float)
        self.a = 0.5 * w * np.array([np.cos(t), np.sin(t)], dtype=float)
        self.b = self.ROT60MAT @ (self.ROT60MAT @ self.a)

        r_circum = w / np.sqrt(3.0)
        corners = []
        for angle in np.linspace(t + np.pi / 6, t + 13 * np.pi / 6, num=6, endpoint=False):
            corners.append(r_circum * np.array([np.cos(angle), np.sin(angle)], dtype=float))
        self.corners = c + np.vstack(corners)

    def __repr__(self) -> str:
        args = [self.center_x, self.center_y, self.width, self.theta]
        return self.__class__.__name__ + '(x={}, y={}, w={}, t={})'.format(*args)

    @classmethod
    def from_edge_xys(cls, edge_xys: np.ndarray) -> Self:
        """Return new by fitting a regular hexagon to a Nx2 list of edge
        positions.

        Uses a simple initial guess from PCA and refines with Powell.
        """
        edge_xys = np.asarray(edge_xys, dtype=float)
        xys_com = np.mean(edge_xys, axis=0)

        # PCA for an initial orientation guess
        xys_deltas = edge_xys - xys_com
        xys_cov = np.cov(xys_deltas.T)
        _, eigenvectors = np.linalg.eigh(xys_cov)

        # Use principal axis as a crude guess for a vertex direction; convert to theta for a axis
        theta0 = float(np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1]) - np.pi / 6.0)

        # Guess width from projected spread onto a axis direction (apothem approx)
        w_hat0 = np.array([np.cos(theta0), np.sin(theta0)], dtype=float)
        proj = xys_deltas @ w_hat0
        # apothem ~ median absolute projection to a side midpoint direction
        a0 = float(np.median(np.abs(proj)))
        width0 = max(1.0, 2.0 * a0)

        guess = np.array([xys_com[0], xys_com[1], width0, theta0], dtype=float)
        res = minimize(cls.edge_d2_sum, guess, args=(edge_xys,), method='Powell')
        new = cls(*res.x)
        new._edge_xys = edge_xys
        return new

    @staticmethod
    def edge_d2_sum(geom: tuple[float, float, float, float], xys: np.ndarray) -> float:
        """Objective: squared distance of points to nearest hexagon side (regular)."""
        center_x, center_y, width, theta = geom
        if width <= 0:
            return np.inf

        center = np.array([center_x, center_y], dtype=float)
        deltas = np.asarray(xys, dtype=float) - center

        # Unit normals to the 6 sides (pointing outward).
        # If an axis points to a side midpoint at angle theta, then that side's outward normal is along theta.
        # Other side normals are spaced by 60 degrees.
        angles = theta + np.arange(6) * (np.pi / 3.0)
        normals = np.stack([np.cos(angles), np.sin(angles)], axis=1)  # (6,2)

        # Signed distances to each supporting line: (n·p - a)
        # Point is inside if all <= 0. We want distance to boundary: max(n·p - a) clipped at 0.
        distances = deltas @ normals.T - 0.5 * width  # (N,6)
        outside = np.maximum(distances.max(axis=1), 0.0)  # (N,)
        return float(np.sum(outside**2))

    def translated(self, delta: np.ndarray) -> Self:
        """Return a new window translated by (dx, dy) in nm."""
        d = np.asarray(delta, dtype=float).reshape(
            2,
        )
        return type(self)(
            float(self.center_x + d[0]),
            float(self.center_y + d[1]),
            float(self.width),
            float(self.theta),
        )


class RectangularWindow(RegularPolygonWindow):
    """Describes one rectangular window with a 2D ab coordinate system.

    Geometry is described using five immutable float scalars (nm / radian):

    - center_x: coordinate of the window center on the X axis;
    - center_y: coordinate of the window center on the Y axis;
    - width: length of window side aligned with the direction of X axis;
    - height: length of window side aligned with the direction or Y axis;
    - theta: signed angle from X axis towards A axis and the X-aligned edge.
    """

    def __init__(self, x: float, y: float, w: float, h: float, t: float):
        t = (t + (np.pi / 2)) % np.pi - (np.pi / 2)  # cast to [-pi/2, pi/2]
        if not -np.pi / 4 < t < np.pi / 4:  # cast to [-pi/4, pi/4]
            w, h, t = h, w, (np.pi - t) % np.pi - np.pi / 2

        self.center_x: float_nm = x
        self.center_y: float_nm = y
        self.width = w = abs(w)
        self.height = h = abs(h)
        self.theta: float = t  # expressed in radian

        self.center = c = np.array([x, y], dtype=float)
        self.a = a = 0.5 * w * np.array([np.cos(t), np.sin(t)], dtype=float)
        self.b = b = 0.5 * h * np.array([-np.sin(t), np.cos(t)], dtype=float)
        self.corners = np.vstack([c + a + b, c + a - b, c - a - b, c - a + b])

    def __repr__(self) -> str:
        args = [self.center_x, self.center_y, self.width, self.height, self.theta]
        return self.__class__.__name__ + '(x={}, y={}, w={}, h={}, t={})'.format(*args)

    @classmethod
    def from_edge_xys(cls, edge_xys: np.ndarray) -> Self:
        """Return new by fitting the edge to a Nx2 list of edge positions."""
        xys_com = np.mean(edge_xys, axis=0)
        xys_deltas = edge_xys - xys_com
        xys_cov = np.cov(xys_deltas.T)
        _, eigenvectors = np.linalg.eigh(xys_cov)
        eigenvector_proj = xys_deltas @ eigenvectors
        width0 = eigenvector_proj[:, 1].max() - eigenvector_proj[:, 1].min()
        height0 = eigenvector_proj[:, 0].max() - eigenvector_proj[:, 0].min()
        theta0 = np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1])
        guess = np.array([xys_com[0], xys_com[1], width0, height0, theta0])
        res = minimize(cls.edge_d2_sum, guess, args=(edge_xys,), method='Powell')
        new = cls(*res.x)
        new._edge_xys = edge_xys
        return new

    @staticmethod
    def edge_d2_sum(geom: tuple[float, float, float, float, float], xys: np.ndarray) -> float:
        """scipy.optimize.minimize fitting func; for geometry see cls docs."""
        center_x, center_y, width, height, theta = geom
        center = np.array([center_x, center_y], dtype=float)
        a = 0.5 * width * np.array([np.cos(theta), np.sin(theta)])
        b = 0.5 * height * np.array([-np.sin(theta), np.cos(theta)])
        a_hat = a / np.linalg.norm(a)
        b_hat = b / np.linalg.norm(b)
        d1 = np.abs(np.dot(xys - (center + a), a_hat))
        d2 = np.abs(np.dot(xys - (center - a), a_hat))
        d3 = np.abs(np.dot(xys - (center + b), b_hat))
        d4 = np.abs(np.dot(xys - (center - b), b_hat))
        return np.sum(np.min([d1, d2, d3, d4], axis=0) ** 2)

    def translated(self, delta: np.ndarray) -> Self:
        """Return a new window translated by (dx, dy) in nm."""
        d = np.asarray(delta, dtype=float).reshape(2)
        return type(self)(
            float(self.center_x + d[0]),
            float(self.center_y + d[1]),
            float(self.width),
            float(self.height),
            float(self.theta),
        )


class SquareWindow(RegularPolygonWindow):
    """Describes one square window with a 2D ab coordinate system.

    Geometry is described using four immutable float scalars (nm / radian):

    - center_x: coordinate of the window center on the X axis;
    - center_y: coordinate of the window center on the Y axis;
    - width: length of the square side (>= 0)
    - theta: signed angle from X axis towards A axis and the X-aligned edge.
    """

    def __init__(self, x: float, y: float, s: float, t: float):
        t = (t + (np.pi / 4)) % (np.pi / 2) - (np.pi / 4)  # cast to [-pi/4, pi/4]

        self.center_x: float_nm = x
        self.center_y: float_nm = y
        self.width = s = abs(s)
        self.theta: float = float(t)

        self.center = c = np.array([x, y], dtype=float)
        self.a = a = 0.5 * s * np.array([np.cos(t), np.sin(t)], dtype=float)
        self.b = b = 0.5 * s * np.array([-np.sin(t), np.cos(t)], dtype=float)
        self.corners = np.vstack([c + a + b, c + a - b, c - a - b, c - a + b])

    def __repr__(self) -> str:
        args = [self.center_x, self.center_y, self.width, self.theta]
        return self.__class__.__name__ + '(x={}, y={}, w={}, t={})'.format(*args)

    @classmethod
    def from_edge_xys(cls, edge_xys: np.ndarray) -> Self:
        """Return new by fitting the edge to a Nx2 list of edge positions."""
        xys_com = np.mean(edge_xys, axis=0)
        xys_deltas = edge_xys - xys_com
        xys_cov = np.cov(xys_deltas.T)
        _, eigenvectors = np.linalg.eigh(xys_cov)
        eigenvector_proj = xys_deltas @ eigenvectors
        width0 = float(eigenvector_proj[:, 1].max() - eigenvector_proj[:, 1].min())
        height0 = float(eigenvector_proj[:, 0].max() - eigenvector_proj[:, 0].min())
        theta0 = float(np.arctan2(eigenvectors[1, 1], eigenvectors[0, 1]))
        side0 = max(1.0, 0.5 * (height0 + width0))
        guess = np.array([xys_com[0], xys_com[1], side0, theta0], dtype=float)
        res = minimize(cls.edge_d2_sum, guess, args=(edge_xys,), method='Powell')
        new = cls(*res.x)
        new._edge_xys = edge_xys
        return new

    @staticmethod
    def edge_d2_sum(geom: tuple[float, float, float, float], xys: np.ndarray) -> float:
        """Objective: squared distance of points to nearest of 4 square sides."""
        center_x, center_y, width, theta = geom
        if width <= 0:
            return np.inf
        center = np.array([center_x, center_y], dtype=float)
        deltas = np.asarray(xys, dtype=float) - center
        angles = theta + np.arange(4) * (np.pi / 2.0)
        normals = np.stack([np.cos(angles), np.sin(angles)], axis=1)  # (4,2)
        # Signed distances to supporting lines: n·p - a, where a = side/2
        distances = deltas @ normals.T - 0.5 * width  # (N,4)
        outside = np.maximum(distances.max(axis=1), 0.0)  # (N,)
        return float(np.sum(outside**2))

    def translated(self, delta: np.ndarray) -> Self:
        d = np.asarray(delta, dtype=float).reshape(2)
        return type(self)(
            float(self.center_x + d[0]),
            float(self.center_y + d[1]),
            float(self.width),
            float(self.theta),
        )
