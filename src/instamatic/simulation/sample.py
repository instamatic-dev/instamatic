from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Sample:
    x: float
    y: float
    r: float
    thickness: float  # between 0 and 1
    euler_angle_phi_1: float
    euler_angle_psi: float
    euler_angle_phi_2: float
    crystal_index: int = 0  # used for lookup in a list of crystals

    def __post_init__(self):
        cp1 = np.cos(self.euler_angle_phi_1)
        cp = np.cos(self.euler_angle_psi)
        cp2 = np.cos(self.euler_angle_phi_2)
        sp1 = np.sin(self.euler_angle_phi_1)
        sp = np.sin(self.euler_angle_psi)
        sp2 = np.sin(self.euler_angle_phi_2)
        r1 = np.array([[cp1, sp1, 0], [-sp1, cp1, 0], [0, 0, 1]])
        r2 = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])
        r3 = np.array([[cp2, sp2, 0], [-sp2, cp2, 0], [0, 0, 1]])
        self.rotation_matrix = r1 @ r2 @ r3

    def pixel_contains_crystal(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Given arrays of x- and y- coordinates in the lab frame, calculate
        whether the crystal overlaps with these positions.

        Parameters
        ----------
        x : np.ndarray
            x coordinates
        y : np.ndarray
            y coordinates

        Returns
        -------
        np.ndarray
            Same shape as inputs, dtype bool
        """
        return (x - self.x) ** 2 + (y - self.y) ** 2 < self.r**2

    def range_might_contain_crystal(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> bool:
        """Simple estimate of whether a range contains the crystal. This check
        is fast but inaccurate. False positives are possible, false negatives
        are impossible.

        Parameters
        ----------
        x_min : float
            Lower bound for x
        x_max : float
            Upper bound for x
        y_min : float
            Lower bound for y
        y_max : float
            Upper bound for y

        Returns
        -------
        bool
            True if range contains crystal
        """
        # TODO ensure the docstring is true, regarding false negatives.
        # TODO improve estimate?
        # TODO handle this correctly when stage is rotated...
        in_x = x_min <= self.x + self.r and self.x - self.r <= x_max
        in_y = y_min <= self.y + self.r and self.y - self.r <= y_max
        return in_x and in_y
