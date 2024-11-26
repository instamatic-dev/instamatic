from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from instamatic.camera.simulate.crystal import CubicCrystal
from instamatic.camera.simulate.grid import Grid


@dataclass
class CrystalSample:
    x: float
    y: float
    r: float
    euler_angle_phi_1: float
    euler_angle_psi: float
    euler_angle_phi_2: float

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
        return (x - self.x) ** 2 + (y - self.y) ** 2 < self.r**2

    def range_contains_crystal(self, x_min: float, x_max: float, y_min: float, y_max: float):
        return (
            x_min < self.x + self.r
            and self.x - self.r < x_max
            and y_min < self.y + self.r
            and self.y - self.r < y_max
        )


class Sample:
    def __init__(
        self,
        num_crystals: int = 10_000,
        min_crystal_size: float = 100,
        max_crystal_size: float = 1000,
        random_seed: int = 100,
    ) -> None:
        # TODO parameters
        self.grid = Grid()

        self.rng = np.random.Generator(np.random.PCG64(random_seed))

        # TODO parameters
        self.crystal = CubicCrystal(4)

        self.crystal_samples = [
            CrystalSample(
                x=self.rng.uniform(-self.grid.radius_nm, self.grid.radius_nm),
                y=self.rng.uniform(-self.grid.radius_nm, self.grid.radius_nm),
                r=self.rng.uniform(min_crystal_size, max_crystal_size),
                euler_angle_phi_1=self.rng.uniform(0, 2 * np.pi),
                euler_angle_psi=self.rng.uniform(0, np.pi),
                euler_angle_phi_2=self.rng.uniform(0, 2 * np.pi),
            )
            for _ in range(num_crystals)
        ]

    def get_image(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> np.ndarray:
        """Get image array for given ranges. (x, y) = (0, 0) is in the center
        of the grid.

        Parameters
        ----------
        shape : tuple[int, int]
            Output shape
        x_min : float
            [nm] Lower bound for x (left)
        x_max : float
            [nm] Upper bound for x (right)
        y_min : float
            [nm] Lower bound for y (bottom)
        y_max : float
            [nm] Upper bound for y (top)

        Returns
        -------
        np.ndarray
            Image
        """
        x, y = np.meshgrid(
            np.linspace(x_min, x_max, shape[1]),
            np.linspace(y_min, y_max, shape[0]),
        )

        grid_mask = self.grid.array_from_coords(x, y)

        sample_data = np.zeros(shape)
        for ind, crystal in enumerate(self.crystal_samples):
            if not crystal.range_contains_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue
            # TODO get actual crystal here, not just index
            sample_data[crystal.pixel_contains_crystal(x, y)] = ind

        # TODO
        sample_data[grid_mask] += 1000

        return sample_data

    def get_diffraction_pattern(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> np.ndarray:
        """Get diffraction pattern array for given ranges. (x, y) = (0, 0) is
        in the center of the grid.

        Parameters
        ----------
        shape : tuple[int, int]
            Output shape
        x_min : float
            [nm] Lower bound for x (left)
        x_max : float
            [nm] Upper bound for x (right)
        y_min : float
            [nm] Lower bound for y (bottom)
        y_max : float
            [nm] Upper bound for y (top)

        Returns
        -------
        np.ndarray
            diffraction pattern
        """
        x, y = np.meshgrid(
            np.linspace(x_min, x_max, shape[1]),
            np.linspace(y_min, y_max, shape[0]),
        )
        d_min = 1.0  # Determines scale of diffraction pattern, length from center to edge

        grid_mask = self.grid.array_from_coords(x, y)

        reflections = np.zeros(shape, dtype=bool)
        for crystal in self.crystal_samples:
            if not crystal.range_contains_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue

            pos = crystal.pixel_contains_crystal(x, y)
            if np.all(grid_mask[pos]):
                # Crystal is completely on the grid
                continue

            reflections |= self.crystal.diffraction_pattern_mask(
                shape,
                d_min=d_min,
                rotation_matrix=crystal.rotation_matrix,
                wavelength=0.02,
                excitation_error=0.01,
            )

        # Simple scaling
        # TODO improve, proper form factors maybe
        kx, ky = np.meshgrid(
            np.linspace(-1 / d_min, 1 / d_min, shape[1]),
            np.linspace(-1 / d_min, 1 / d_min, shape[0]),
        )
        k_squared = kx**2 + ky**2
        scale = 1 / (3 * k_squared + 1)

        scale[~reflections] = 0

        return scale
