"""Keeps the logic about dividing grid windows into separate regions."""

from __future__ import annotations

import re
from itertools import product
from typing import Iterator, Self, Union

import numpy as np

from instamatic.grid.grid import PeriodicConvexPolygonGrid as GridGeometry


class Regionalization:
    """Dictates the relation between grid windows & regions (their groups)."""

    def __init__(
        self,
        grid: Union[type[GridGeometry], GridGeometry],
        shape: tuple[int, int],
    ):
        self.grid = grid
        self.shape = shape

    @classmethod
    def from_str(cls, grid: Union[type[GridGeometry], GridGeometry], shape: str) -> Self:
        """Shorthand to convert shape string "MxN" into a tuple."""
        m = re.match(pattern=r'^\s*(\d+)\s*[Xx*,]\s*(\d+)\s*$', string=shape)
        return cls(grid, (int(m[1]), int(m[2])))

    def windows(self, region_idx: int) -> Iterator[int]:
        """Yield idx of windows that lie in requested region."""
        region_ij = self.grid.pairing_inverse(region_idx)
        i_span = np.arange(self.shape[0]) - (self.shape[0] - 1) // 2
        j_span = np.arange(self.shape[1]) - (self.shape[1] - 1) // 2
        window_ij = region_ij * np.array(self.shape)
        for i, j in product(i_span, j_span):
            yield self.grid.pairing_function(window_ij[0] + i, window_ij[1] + j)
