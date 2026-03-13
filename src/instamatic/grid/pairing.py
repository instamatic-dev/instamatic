"""This module deals with pairing functions used to map between two coordinate
systems: a 1D-periodic series of natural numbers infinite in one direction
and a 2D-periodic lattice of whole numbers infinite in both directions.
Either space is to be used when indexing individual windows on a sample grid:
1D for ordering on a list and 2D for locating in 2D ij-indexed space.

The space indexing schemes used in this module are as follows:
- ij - orthogonal 2D grid: i goes right (alongside x), j goes up (with y);
  This is the typical Cartesian setting used in mathematics.
- ulam - 1D idx of ortho 2D grid: 0=center, 1 right, then spiral anti-clockwise.
  Cartesian distance between two subsequent cells is always 1.
  Maximum distance from zero grows steadily step-wise: 1x0, 8x1, 16x2, 24x3...
- uv - hexagonal 2D grid (side-flat): u goes right, v +120deg anti-clockwise
  Most popular hexagonal setting, i+1,j or i,j+1 distance is always 2r
- spiral - 1D idx of hex 2D grid: 0=center, 1 right, then spiral anti-clockwise
  Cartesian distance between two subsequent cells is always 2r.
  Hex-Manhattan distance from zero grows steadily step-wise: 1x0, 6x1, 12x2...

For further details on the qrs space, see:
https://www.redblobgames.com/grids/hexagons/ and https://doi.org/10.1117/1.JEI.22.1.010502
"""

from __future__ import annotations

import math
from typing import Protocol


class PairingFunction(Protocol):
    def __call__(self, i: int, j: int, /) -> int: ...


class PairingInverse(Protocol):
    def __call__(self, n: int, /) -> tuple[int, int]: ...


def ulam2ij(u: int) -> tuple[int, int]:
    """Convert from index in 1D Ulam to orthogonal (i, j) coordinates."""
    if u < 0:
        i, j = ulam2ij(-u)
        return -i, -j
    if u == 0:
        return 0, 0

    # Calculate Chebyshev distance k in the ij-space:
    # k-th ring starts at minimum value of u0 = (2k-1)^2 at coords (k, 1-k)
    # k-th ring ends at maximum value of u1 = (2k+1)^2-1 at coords (k, -k)
    k = math.ceil((math.sqrt(u + 1) - 1) / 2)
    u0 = (2 * k - 1) ** 2
    offset = u - u0

    if offset <= 2 * k - 1:  # segment 1: go upwards from bottom-right corner
        return k, -k + 1 + offset
    elif offset <= 4 * k - 1:  # segment 2: go left from top-right corner
        return 3 * k - 1 - offset, k
    elif offset <= 6 * k - 1:  # segment 3: go down from top-left corner
        return -k, 5 * k - 1 - offset
    return offset - 7 * k + 1, -k  # segment 4: go right from bottom-left corner


def ij2ulam(i: int, j: int) -> int:
    """Convert from index in orthogonal (i, j) to 1D Ulam coordinates."""
    if i == 0 and j == 0:
        return 0

    k = max(abs(i), abs(j))  # Chebyshev distance k in the ij-space
    u0 = (2 * k - 1) ** 2  # Lowest Ulam index on ring k at coords (k, 1-k)

    if i == k and -k + 1 <= j <= k:  # segment 1
        return u0 + j + k - 1
    elif j == k and -k <= i <= (k - 1):  # segment 2
        return u0 + (2 * k - 1) + (k - i)
    elif i == -k and -k <= j <= (k - 1):  # segment 3
        return u0 + (4 * k - 1) + (k - j)
    return u0 + (6 * k - 1) + (i + k)  # segment 4


# Spiral directions (axial-like coords):
# start of ring k is (k, 0), then walk CCW with these step directions
_DIRS: list[tuple[int, int]] = [(0, 1), (-1, 0), (-1, -1), (0, -1), (1, 0), (1, 1)]


def spiral2uv(n: int) -> tuple[int, int]:
    """Convert from 1D hex spiral index to hexagonal (u, v) coordinates.

    Inverse of the user's uv2spiral() that:
      - ring k starts at (u,v) = (1, 1-k) (right above bottom-right corner)
      - walks counter-clockwise with 6 segments, each of length k
      - ring k has 6k points, indices s0..s0+6k-1
    """
    if n < 0:
        raise ValueError('n must be >= 0')
    if n == 0:
        return (0, 0)

    # Find ring k such that max index on ring k is 3*k*(k+1)
    k = math.ceil((math.sqrt(12 * n + 9) - 3) / 6)

    # First index on ring k
    s0 = 1 + 3 * (k - 1) * k
    t = n - s0  # offset along ring: 0 .. 6k-1

    if not (0 <= t <= 6 * k - 1):
        raise AssertionError(f'Internal error: n={n}, k={k}, s0={s0}, t={t}')

    # Segment 1: up the right-bottom edge (u-v=k), u = 1..k
    if t < k:
        u = t + 1
        v = u - k
    # Segment 2: up the right-up edge (u=k), v = 1..k
    elif t < 2 * k:
        u = k
        v = (t - k) + 1
    # Segment 3: along the top edge (v=k), u = k-1 .. 0
    elif t < 3 * k:
        v = k
        u = (3 * k - 1) - t
    # Segment 4: down the upper-left edge (v-u=k), u = -1 .. -k
    elif t < 4 * k:
        u = (3 * k) - t - 1
        v = u + k
    # Segment 5: down the left edge (u=-k), v = -1 .. -k
    elif t < 5 * k:
        u = -k
        v = (4 * k) - t - 1
    # Segment 6: along the bottom edge (v=-k), u = -k+1 .. 0
    else:
        v = -k
        u = t - 6 * k + 1
    return u - v, v  # conversion from previously used 120-deg system to 60-deg


def uv2spiral(u: int, v: int) -> int:
    """Convert from index in hexagonal (u, v) coordinates to 1D hex spiral."""

    if u == 0 and v == 0:
        return 0

    u = u + v  # conversion from previously used 120-deg system to 60-deg
    k = max(abs(u), abs(v), abs(u - v))  # Hex "radius" in (u,v) system
    s0 = 1 + 3 * (k - 1) * k  # first index on ring k
    # point with lowest s0 lies right above bottom right corner of the hexagon

    if u - v == k and u > 0:  # segment 1: up the right-bottom edge
        return s0 + u - 1
    elif u == k:  # segment 2: up the right-up edge
        return s0 + k + v - 1
    elif v == k:  # segment 3: right the top edge
        return s0 + 2 * k - u + v - 1
    elif v - u == k:
        return s0 + 3 * k - u - 1
    elif u == -k:
        return s0 + 4 * k - v - 1
    return s0 + 5 * k + u - v - 1


if __name__ == '__main__':  # tests
    """Map ulam and spiral indices onto a 2x2 matrix of (i,j) coordinates."""

    import numpy as np

    # grid definition
    xs = np.arange(-4, 5)
    ys = np.arange(4, -5, -1)  # top row first: (·,4) down to (·,-4)

    # 9x9x2 array of (i,j)
    ij_grid = np.empty((9, 9, 2), dtype=int)
    for r, j in enumerate(ys):
        for c, i in enumerate(xs):
            ij_grid[r, c] = (i, j)

    # pretty-print ij grid
    print('ij grid:')
    for row in ij_grid:
        print(' '.join(f'({i:2d},{j:2d})' for i, j in row))

    print()

    # 9x9 array of Ulam indices
    ulam_grid = np.empty((9, 9), dtype=int)
    for r in range(9):
        for c in range(9):
            i, j = ij_grid[r, c]
            ulam_grid[r, c] = ij2ulam(i, j)

    # pretty-print ulam grid
    print('Ulam index grid:')
    for row in ulam_grid:
        print(' '.join(f'{n:4d}' for n in row))

    print()

    # 9x9 array of Spiral indices
    spiral_grid = np.empty((9, 9), dtype=int)
    for r in range(9):
        for c in range(9):
            u, v = ij_grid[r, c]
            spiral_grid[r, c] = uv2spiral(u, v)

    # pretty-print spiral indices
    print('Spiral index grid:')
    for i, row in enumerate(spiral_grid):
        print('  ' * (8 - i) + ' '.join(f'{n:3d}' for n in row))

    for i in range(100):
        assert ij2ulam(*ulam2ij(i)) == i
        assert uv2spiral(*spiral2uv(i)) == i, f'Mismatch for {i}'
