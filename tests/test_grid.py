from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from instamatic.grid import cross2d, versor
from instamatic.grid.artist import plot_grid
from instamatic.grid.finder import GridFinder
from instamatic.grid.grid import (
    HexagonalGrid,
    PeriodicConvexPolygonGrid,
    RectangularGrid,
    SquareGrid,
)
from instamatic.grid.sweeping import Sweeper
from instamatic.grid.window import (
    GridablePolygonWindow,
    HexagonalWindow,
    RectangularWindow,
    SquareWindow,
)
from tests.utils import InstanceAutoTracker

# instamatic.grid.__init__


def test_grid_cross2d():
    """Assert that cross2d product is calculated correctly."""
    a = np.array([1.0, 0.0])
    a2 = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    z = np.array([0.0, 0.0])
    assert cross2d(a, b) == pytest.approx(1.0)
    assert cross2d(a, a2) == pytest.approx(0.0)
    assert cross2d(a, z) == pytest.approx(0.0)


def test_grid_versors():
    """Assert that versors are created properly and reasonably."""
    np.testing.assert_allclose(versor(rad=0), [1, 0], atol=1e-12)
    np.testing.assert_allclose(versor(deg=90), [0, 1], atol=1e-12)
    for angle in np.linspace(0, 360, 37):
        assert np.linalg.norm(versor(deg=angle)) == pytest.approx(1.0)
    v1 = versor(deg=30.0)
    v2 = versor(rad=0.5235987756)
    v3 = np.array([np.sqrt(3) / 2, 1 / 2], dtype=np.float32)
    np.testing.assert_allclose(v1, v3, atol=1e-6)
    np.testing.assert_allclose(v2, v3, atol=1e-6)


# instamatic.grid.window


@dataclass
class WindowTestCase(InstanceAutoTracker):
    """Auto-registers three windows test case instances in INSTANCES."""

    cls: type[GridablePolygonWindow]
    params: tuple[float, ...]
    h_cut: float = 10  # length of horizontal / vertical line cutting through middle
    v_cut: float = 10


r2 = np.sqrt(2)
r3 = np.sqrt(3)

WindowTestCase(cls=HexagonalWindow, params=(30, 30, 0, 10), h_cut=20 / r3)
WindowTestCase(cls=RectangularWindow, params=(30, 30, 0, 10, 10))
WindowTestCase(cls=SquareWindow, params=(30, 30, 45, 10), h_cut=10 * r2, v_cut=10 * r2)


@pytest.mark.parametrize('window_case', WindowTestCase.INSTANCES)
def test_windows(window_case) -> None:
    """Test if created window meets simple tests for internal lengths."""
    w = window_case.cls(*window_case.params)
    assert w.corners.shape[0] > 3
    np.testing.assert_allclose(w.center, [30, 30])
    side_lens = np.linalg.norm(np.roll(w.corners, -1, axis=0) - w.corners, axis=1)
    dists = np.linalg.norm(w.corners - w.center, axis=1)
    if window_case.cls == HexagonalWindow:
        np.testing.assert_allclose(side_lens, 10 / r3, rtol=1e-10)
        np.testing.assert_allclose(dists, 10 / r3, rtol=1e-10)
    else:
        np.testing.assert_allclose(side_lens, 10, rtol=1e-10)
        np.testing.assert_allclose(dists, 5 * r2, rtol=1e-10)


@pytest.mark.parametrize('window_case', WindowTestCase.INSTANCES)
def test_window_residuals(window_case) -> None:
    """Test if edge residual calculations work and give 0 for corners."""
    w = window_case.cls(*window_case.params)
    np.testing.assert_allclose(w.edge_residuals(w.corners), 0.0, atol=1e-6)
    assert w.edge_residuals(np.empty((0, 2))).shape == (0,)


@pytest.mark.parametrize('window_case', WindowTestCase.INSTANCES)
def test_window_intersects(window_case) -> None:
    """Test if windows are correctly cut or missed by intersecting lines."""
    w = window_case.cls(*window_case.params)
    wx = w.y_intersections(30)
    assert wx[1] - wx[0] == pytest.approx(window_case.h_cut)
    wy = w.x_intersections(30)
    assert wy[1] - wy[0] == pytest.approx(window_case.v_cut)
    assert w.x_intersections(-30) is None
    assert w.y_intersections(-30) is None


@pytest.mark.parametrize('window_case', WindowTestCase.INSTANCES)
def test_window_hexagonal_intersects_limits(window_case) -> None:
    """Test if windows intersect correct x/y limits' squares."""
    w = window_case.cls(*window_case.params)
    assert not w.intersects_limits(5, 5)
    assert w.intersects_limits(30, 30)


# instamatic.grid.grid


@dataclass
class GridTestCase(InstanceAutoTracker):
    """Auto-registers grid test case instances in INSTANCES."""

    cls: type[PeriodicConvexPolygonGrid]
    window_type: type
    h: Optional[float] = None
    s: Optional[float] = None


GridTestCase(cls=HexagonalGrid, window_type=HexagonalWindow, h=None, s=5.0)
GridTestCase(cls=RectangularGrid, window_type=RectangularWindow, h=50)
GridTestCase(cls=SquareGrid, window_type=SquareWindow, h=None, s=None)


@pytest.mark.parametrize('grid_case', GridTestCase.INSTANCES)
def test_grid_initialization_and_normalization(grid_case) -> None:
    """Test that grids initialize correctly and normalization bounds the
    angle."""
    g = grid_case.cls(10, 20, 30, 40, grid_case.h, grid_case.s)
    if grid_case.s is None:
        assert g.s == g.DEFAULT_SPACING
    g_norm = g.normalized()
    max_angle = g.window_type.INTERIOR_ANGLE / 2
    assert -max_angle <= g_norm.t <= max_angle


@pytest.mark.parametrize('grid_case', GridTestCase.INSTANCES)
def test_grid_window_and_nearest_index(grid_case) -> None:
    """Test whether initialized window type and nearest index are correct."""
    g = grid_case.cls(10, 20, 30, 40, grid_case.h, grid_case.s)
    w = g.window(77)
    assert isinstance(w, grid_case.window_type)
    assert g.nearest_index(*w.center) == 77


@pytest.mark.parametrize('grid_case', GridTestCase.INSTANCES)
def test_grid_limits(grid_case) -> None:
    """Test that limit bounding boxes properly encapsulate targeted windows."""
    g = grid_case.cls(10, 20, 30, 40, grid_case.h, grid_case.s)
    idc_in_limits = g.windows_in_limits(20, 20)
    assert 0 in idc_in_limits
    assert 77 not in idc_in_limits


@pytest.mark.parametrize('grid_case', GridTestCase.INSTANCES)
def test_grid_guess_and_refine(grid_case) -> None:
    """Test that guessing and refining a grid from perfect intercepts recovers
    it."""
    g = grid_case.cls(0, 10, 20, 30, grid_case.h, grid_case.s)

    corners = g.window(0).corners  # window corners
    midpoints = (corners + np.roll(corners, -1, axis=0)) / 2
    intercepts = {0: np.vstack((corners, midpoints))}
    g_guess = grid_case.cls.guess(intercepts)
    np.testing.assert_allclose(g_guess.origin, g.origin, atol=1e-7)
    g_guess.refine(intercepts)
    for a in ('origin', 'x', 'y', 't', 'w', 'h'):
        np.testing.assert_allclose(getattr(g_guess, a), getattr(g, a), atol=1e-10)


# instamatic.grid.finder


def test_grid_finder_add_intercept():
    """Assert that new intercepts are properly saved in GridFinder."""
    gf = GridFinder(grid=SquareGrid(0, 0, 0, 10_000), intercepts={})
    gf.add_intercept(0, 200.0, 0)
    assert 0 in gf.intercepts
    assert gf.intercepts[0].shape == (1, 2)
    gf.add_intercept(0, 400.0, 0)
    gf.add_intercept(0, 600.0, 0)
    assert gf.intercepts[0].shape == (3, 2)


def test_grid_finder_yaml_read_write():
    """Assert that grid finder can read and (auto-)write yaml files."""
    gf = GridFinder(grid=SquareGrid(0, 0, 0, 10_000), intercepts={})
    gf.add_intercept(0, 1000.0, 2000.0)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'grid.yaml'
        gf.to_yaml(p)
        gf2 = GridFinder.from_yaml(p)
        assert type(gf2.grid) is SquareGrid
        np.testing.assert_allclose(gf2.grid.x, gf.grid.x)
        np.testing.assert_allclose(gf2.intercepts[0], gf.intercepts[0])
        gf.path = p
        gf.add_intercept(1, 5000.0, 5000.0)
        gf3 = GridFinder.from_yaml(p)
        assert type(gf3.grid) is SquareGrid
        np.testing.assert_allclose(gf2.grid.w, gf.grid.w)
        np.testing.assert_allclose(gf3.intercepts[1], gf.intercepts[1])


# instamatic.grid.sweeping


def test_grid_sweeping_sweeper_dist2segment():
    """Assert dist2segment properly estimates dist only to hit segments."""
    s = Sweeper(origin=[0, 0], heading=[1, 0])
    assert s.dist2segment(4, -1, 6, 1) == pytest.approx(5.0)
    assert s.dist2segment(0, 1, 10, 1) == np.inf
    assert s.dist2segment(-5, -1, -5, 1) == np.inf


# instamatic.grid.artist


def test_grid_plot_grid():
    """Assert that plot_grid executes with default arguments and returns
    Figure/Axes."""
    fig, ax = plot_grid(
        SquareGrid(0, 0, 0, 10_000),
        intercepts={0: np.atleast_2d([0.0, 0.0])},
        limit_x=25_000,
        limit_y=25_000,
    )
    assert isinstance(fig, Figure)
    assert isinstance(ax, Axes)
    assert len(ax.patches) > 0  # Should have drawn the default windows 0-24
    assert len(ax.lines) >= 6
    plt.close(fig)


# instamatic.grid.monitor is GUI only and thus has no tests
