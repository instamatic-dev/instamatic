from __future__ import annotations

from instamatic._collections import NoOverwriteDict
from instamatic.grid.grid import PeriodicConvexPolygonGrid, WindowType
from instamatic.grid.pairing import ij2ulam, spiral2uv, ulam2ij, uv2spiral
from instamatic.grid.window import HexagonalWindow, RectangularWindow, SquareWindow


class HexagonalGrid(PeriodicConvexPolygonGrid[HexagonalWindow]):
    window_type = HexagonalWindow
    pairing_function = staticmethod(uv2spiral)
    pairing_inverse = staticmethod(spiral2uv)


class RectangularGrid(PeriodicConvexPolygonGrid[RectangularWindow]):
    window_type = RectangularWindow
    pairing_function = staticmethod(ij2ulam)
    pairing_inverse = staticmethod(ulam2ij)


class SquareGrid(PeriodicConvexPolygonGrid[RectangularWindow]):
    window_type = SquareWindow
    pairing_function = staticmethod(ij2ulam)
    pairing_inverse = staticmethod(ulam2ij)


GRID_REGISTRY = NoOverwriteDict[str, type[PeriodicConvexPolygonGrid]]()
GRID_REGISTRY['hexagonal'] = HexagonalGrid
GRID_REGISTRY['rectangular'] = RectangularGrid
GRID_REGISTRY['square'] = SquareGrid


# development test code; to be moved to artist/tests

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import numpy as np

    from instamatic.grid.artist import plot

    g1 = HexagonalGrid()
    w1 = HexagonalWindow(0, 0, 50_000, np.deg2rad(10))
    g1.windows[0] = w1

    g2 = RectangularGrid()
    w2 = RectangularWindow(0, 0, 40_000, 60_000, np.deg2rad(10))
    g2.windows[0] = w2

    g3 = RectangularGrid()
    w3 = RectangularWindow(0, 0, 20_000, 200_000, np.deg2rad(10))
    g3.windows[0] = w3

    g4 = SquareGrid()
    w4 = SquareWindow(0, 0, 50_000, np.deg2rad(10))
    g4.windows[0] = w4

    for grid in [g1, g2, g3, g4]:
        for i in range(120):
            w = grid.predict_window(i)
            if np.linalg.norm(w.center - grid.windows[0].center) < 200_000:
                grid.windows[i] = w

    fig, axs = plt.subplots(2, 2)
    fig.tight_layout()
    plot(g1.windows, ax=axs[0, 0])
    plot(g2.windows, ax=axs[0, 1])
    plot(g3.windows, ax=axs[1, 0])
    plot(g4.windows, ax=axs[1, 1])
    plt.show()
