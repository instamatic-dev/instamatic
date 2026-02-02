from __future__ import annotations

from instamatic._collections import NoOverwriteDict
from instamatic.grid.grid import PeriodicConvexPolygonGrid, WindowType
from instamatic.grid.pairing import ij2ulam, spiral2uv, ulam2ij, uv2spiral
from instamatic.grid.window import HexagonalWindow, RectangularWindow, SquareWindow

GRID_REGISTRY = NoOverwriteDict[str, WindowType]()


def register_grid(name: str):
    """A decorator to cleanly puts grid class in GRID_REGISTRY under name."""

    def decorator(cls):
        GRID_REGISTRY[name] = cls
        return cls

    return decorator


@register_grid(name='Hexagonal')
class HexagonalGrid(PeriodicConvexPolygonGrid[HexagonalWindow]):
    window_type = HexagonalWindow
    pairing_function = staticmethod(uv2spiral)
    pairing_inverse = staticmethod(spiral2uv)


@register_grid(name='Rectangular')
class RectangularGrid(PeriodicConvexPolygonGrid[RectangularWindow]):
    window_type = RectangularWindow
    pairing_function = staticmethod(ij2ulam)
    pairing_inverse = staticmethod(ulam2ij)


@register_grid(name='Square')
class SquareGrid(PeriodicConvexPolygonGrid[RectangularWindow]):
    window_type = SquareWindow
    pairing_function = staticmethod(ij2ulam)
    pairing_inverse = staticmethod(ulam2ij)


# development test code; to be moved to artist/tests

if __name__ == '__main__':
    import numpy as np

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
