"""This module deals with pairing functions and their inverses used to map
between two coordinate systems: a 1D series of natural numbers including zero
and a 2D space of integers (infinite in both directions).

The space indexing schemes used in this module are as follows:
- ij - orthogonal 2D grid: i goes right (alongside x), j goes up (with y);
  This is the typical Cartesian setting used in mathematics.
- ulam - 1D idx of ortho 2D grid: 0=center, 1=right, then spiral anti-clockwise.
  Cartesian distance between two subsequent cells is always 1.
  Maximum distance from zero grows steadily step-wise: 1x0, 8x1, 16x2, 24x3...
- uv - hexagonal 2D grid (side-flat): u goes right, v +60deg anti-clockwise
  A popular hexagonal setting: distance between i,j and i+1,j or i,j+1 is 1.
- hulam - 1D idx of hex 2D grid: 0=center, 1=right, then spiral anti-clockwise
  Cartesian distance between two subsequent cells is always 1.
  Hex-Chebyshev distance from zero grows steadily step-wise:
  One cell in distance 0, six in distance 1, twelve in distance 12...

For further details on the qrs space, see:
https://www.redblobgames.com/grids/hexagons/ and https://doi.org/10.1117/1.JEI.22.1.010502

The algorithm behind both pairing and inverse functions works as follows:
- find k: (hex-)chebyshev distance of index n / pair ij or uv from (0, 0)
- find n0: the lowest (h)ulam index for any index / pair at a given distance k
- determine on which segment the point is and manually calculate its pair/index

In any 2D space, n0 for given k is always right above the bottom right corner.

In 2D orthogonal space:
- k-th ring starts at minimum ulam index (2k-1)^2 at orthogonal coords (k, 1-k).
- k-th ring ends at maximum ulam index (2k+1)^2-1 at orthogonal coords (k, -k).

Ulam index increases when counting along the following segments in this order:
- Segment 1: Up from bottom-right to top-right corner:  (k, 1-k)   to (k, k).
- Segment 2: Left from top-right to top-left corner:    (k-1, k)   to (-k, k).
- Segment 3: Down from top-left to bottom-left corner:  (-k, k-1)  to (-k, -k).
- Segment 4: Right from bottom-left to b-right corner:  (1-k, -k)  to (k, -k).

In 2D hexagonal space:
- k-th ring starts at minimum hulam index 3k^2-3k+1 at hex coords (k, 1-k).
- k-th ring ends at maximum hulam index 3k^2+3k at hexagonal coords (k, -k).

Hulam index (hexagonal) increases along the following segments in this order:
- Segment 1: Up-right from bottom-right to right corner:  (k, 1-k)  to (k, 0).
- Segment 2: Up-left from right to top-right corner:      (k-1, 1)  to (0, k).
- Segment 3: Left top-right to top-left corner:           (-1, k)   to (-k, k).
- Segment 4: Down-left from top-left to left corner:      (-k, k-1) to (-k, 0).
- Segment 5: Down-right from left to bottom-left corner:  (1-k, -1) to (0, -k).
- Segment 6: Right from bottom-left to b-right corner:    (1, -k)   to (k, -k).
"""

from __future__ import annotations

import math
from typing import Protocol


class PairingFunction(Protocol):
    def __call__(self, i: int, j: int, /) -> int: ...


class PairingInverse(Protocol):
    def __call__(self, n: int, /) -> tuple[int, int]: ...


def ulam2ij(n: int) -> tuple[int, int]:
    """Convert from index in 1D Ulam to orthogonal (i, j) coordinates.

    k-th ring starts at minimum value of n0 = (2k-1)^2 at coords (k,
    1-k). k-th ring ends at maximum value of n1 = (2k+1)^2-1 at coords
    (k, -k).
    """
    if n == 0:
        return 0, 0
    elif n < 0:
        raise ValueError(f'Conversion of negative Ulam index {n} is not supported')

    k = math.ceil((math.sqrt(n + 1) - 1) / 2)
    n0 = (2 * k - 1) ** 2
    offset = n - n0

    if offset <= 2 * k - 1:  # segment 1
        return k, -k + 1 + offset
    elif offset <= 4 * k - 1:  # segment 2
        return 3 * k - 1 - offset, k
    elif offset <= 6 * k - 1:  # segment 3
        return -k, 5 * k - 1 - offset
    return offset - 7 * k + 1, -k  # segment 4


def ij2ulam(i: int, j: int) -> int:
    """Convert from index in orthogonal (i, j) to 1D Ulam coordinates."""
    if i == 0 and j == 0:
        return 0

    k = max(abs(i), abs(j))
    n0 = (2 * k - 1) ** 2

    if i == k and -k + 1 <= j <= k:  # segment 1
        return n0 + j + k - 1
    elif j == k and -k <= i <= (k - 1):  # segment 2
        return n0 + (2 * k - 1) + (k - i)
    elif i == -k and -k <= j <= (k - 1):  # segment 3
        return n0 + (4 * k - 1) + (k - j)
    return n0 + (6 * k - 1) + (i + k)  # segment 4


def hulam2uv(n: int) -> tuple[int, int]:
    """Convert from 1D hex Ulam index to hexagonal (u, v) coordinates."""
    if n == 0:
        return 0, 0
    elif n < 0:
        raise ValueError(f'Conversion of negative hulam index {n} is not supported')

    k = math.ceil((math.sqrt(12 * n + 9) - 3) / 6)
    n0 = 1 + 3 * (k - 1) * k
    offset = n - n0

    if offset < k:  # Segment 1
        return k, 1 - k + offset
    elif offset < 2 * k:  # Segment 2
        return 2 * k - offset - 1, offset - k + 1
    elif offset < 3 * k:  # Segment 3
        return 2 * k - 1 - offset, k
    elif offset < 4 * k:  # Segment 4
        return -k, 4 * k - offset - 1
    elif offset < 5 * k:  # Segment 5
        return -5 * k + offset + 1, 4 * k - offset - 1
    return 1 + offset - 5 * k, -k  # Segment 6


def uv2hulam(u: int, v: int) -> int:
    """Convert from index in hexagonal (u, v) coordinates to 1D hex Ulam."""

    if u == 0 and v == 0:
        return 0

    k = max(abs(u), abs(v), abs(u + v))
    n0 = 1 + 3 * (k - 1) * k

    if u == k and -k < v <= 0:
        return n0 + v + k - 1
    elif u + v == k and u < k:
        return n0 + k + v - 1
    elif v == k:
        return n0 + 2 * k - u - 1
    elif u == -k:
        return n0 + 3 * k + k - 1 - v
    elif u + v == -k:
        return n0 + 4 * k + u + k - 1
    return n0 + 5 * k + u - 1


if __name__ == '__main__':  # tests
    # Draw ulam and hulam indices onto a 2x2 matrix of (i,j) for demo/testing.

    import numpy as np

    # 9x9x2 array of (i,j)
    ij_grid = np.empty((9, 9, 2), dtype=int)
    for r, j in enumerate(np.arange(4, -5, -1)):
        for c, i in enumerate(np.arange(-4, 5)):
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
    hulam_grid = np.empty((9, 9), dtype=int)
    for r in range(9):
        for c in range(9):
            u, v = ij_grid[r, c]
            hulam_grid[r, c] = uv2hulam(u, v)

    # pretty-print spiral hulam indices
    print('Hulam index grid:')
    for i, row in enumerate(hulam_grid):
        print('  ' * (8 - i) + ' '.join(f'{n:3d}' for n in row))
