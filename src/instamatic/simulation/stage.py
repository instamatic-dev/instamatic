from __future__ import annotations

import warnings

import numpy as np
from scipy.spatial.transform import Rotation

from instamatic.simulation.crystal import Crystal
from instamatic.simulation.grid import Grid
from instamatic.simulation.sample import Sample
from instamatic.simulation.warnings import NotImplementedWarning


class Stage:
    def __init__(
        self,
        num_crystals: int = 100_000,
        min_crystal_size: float = 100,
        max_crystal_size: float = 3_000,
        random_seed: int = 100,
    ) -> None:
        """Handle many samples on a grid.

        Parameters
        ----------
        num_crystals : int, optional
            Number of crystals to disperse on the grid, by default 100_000
        min_crystal_size : float, optional
            Minimum radius of the crystals, in nm, by default 100
        max_crystal_size : float, optional
            Maximum radius of the crystals, in nm, by default 1000
        random_seed : int, optional
            Seed for random number generation, by default 100
        """

        self.in_plane_rotation = 10  # TODO change this with focus/magnification
        self.set_position(0, 0, 0, 0, 0)

        # TODO parameters
        self.grid = Grid()

        self.rng = np.random.Generator(np.random.PCG64(random_seed))

        # TODO parameters
        # TODO amorphous phase
        self.crystals = [
            Crystal(20, 20, 20, 90, 90, 90, 221),
            Crystal(*self.rng.uniform(5, 25, 3), *self.rng.uniform(80, 110, 3)),
        ]

        self.samples = [
            Sample(
                x=self.rng.uniform(-self.grid.radius_nm, self.grid.radius_nm),
                y=self.rng.uniform(-self.grid.radius_nm, self.grid.radius_nm),
                r=self.rng.uniform(min_crystal_size, max_crystal_size),
                thickness=self.rng.uniform(0, 1),
                euler_angle_phi_1=self.rng.uniform(0, 2 * np.pi),
                euler_angle_psi=self.rng.uniform(0, np.pi),
                euler_angle_phi_2=self.rng.uniform(0, 2 * np.pi),
            )
            for _ in range(num_crystals)
        ]

    @property
    def origin(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    def set_position(
        self,
        x: float = None,
        y: float = None,
        z: float = None,
        alpha_tilt: float = None,
        beta_tilt: float = None,
    ):
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y
        if z is not None:
            self.z = z
        if alpha_tilt is not None:
            warnings.warn(
                'Tilting is not fully implemented yet',
                NotImplementedWarning,
                stacklevel=2,
            )
            self.alpha_tilt = alpha_tilt
        if beta_tilt is not None:
            warnings.warn(
                'Tilting is not fully implemented yet',
                NotImplementedWarning,
                stacklevel=2,
            )
            self.beta_tilt = beta_tilt

        # TODO define orientation. Is this matrix multiplied with lab coordinates to get sample coordinates?
        self.rotation_matrix = Rotation.from_euler(
            'ZXY',
            [self.in_plane_rotation, self.alpha_tilt, self.beta_tilt],
            degrees=True,
        ).as_matrix()

    def image_extent_to_stage_coordinates(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Get arrays of grid positions with a given shape and extent in lab
        coordinates.

        Parameters
        ----------
        shape : tuple[int, int]
            Output shape
        x_min : float
            Lower bound of x
        x_max : float
            Upper bound of x
        y_min : float
            Lower bound of y
        y_max : float
            Upper bound of y

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            x, y. 2D arrays of floats
        """
        if self.alpha_tilt != 0 or self.beta_tilt != 0:
            warnings.warn(
                'Tilting is not fully implemented yet', NotImplementedWarning, stacklevel=2
            )
        # https://en.wikipedia.org/wiki/Line%E2%80%93plane_intersection
        l = np.array([0, 0, 1])  # noqa: E741
        n = self.rotation_matrix @ l
        p0 = self.origin
        l0 = np.array(
            [
                p.flatten()
                for p in np.meshgrid(
                    np.linspace(x_min, x_max, shape[1]),
                    np.linspace(y_min, y_max, shape[0]),
                    [self.z],
                )
            ]
        )
        p = l0 + l[:, np.newaxis] * np.dot(-l0.T + p0, n) / np.dot(l, n)

        # Rotate around sample-holder-constant axes, not stage
        p0[2] = 0
        x, y, z = p0[:, np.newaxis] + self.rotation_matrix.T @ (p - p0[:, np.newaxis])
        x = x.reshape(shape)
        y = y.reshape(shape)
        return x, y

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
        x, y = self.image_extent_to_stage_coordinates(
            shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )
        x_min = x.min()
        x_max = x.max()
        y_min = y.min()
        y_max = y.max()

        grid_mask = self.grid.array_from_coords(x, y)

        sample_data = np.full(shape, fill_value=0xF000, dtype=np.uint32)
        for ind, sample in enumerate(self.samples):
            if not sample.range_might_contain_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue
            # TODO better logic here
            sample_data[sample.pixel_contains_crystal(x, y)] = np.round(
                0xF000 * (1 - sample.thickness)
            )

        sample_data[grid_mask] = 0

        return sample_data

    def get_diffraction_pattern(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        camera_length: float = 150,
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
        camera_length : float
            [cm] Camera length, for calibration

        Returns
        -------
        np.ndarray
            diffraction pattern
        """
        x, y = self.image_extent_to_stage_coordinates(
            shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )
        x_min = x.min()
        x_max = x.max()
        y_min = y.min()
        y_max = y.max()
        d_min = 1.0

        grid_mask = self.grid.array_from_coords(x, y)

        if np.all(grid_mask):
            # no transmission
            return np.zeros(shape, dtype=int)

        reflections = np.zeros(shape, dtype=float)

        for sample in self.samples:
            if not sample.range_might_contain_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue
            pos = sample.pixel_contains_crystal(x, y)
            if np.all(grid_mask[pos]):
                # Crystal is completely on the grid
                continue

            reflections += self.crystals[sample.crystal_index].diffraction_pattern_mask(
                shape,
                d_min=d_min,
                rotation_matrix=self.rotation_matrix @ sample.rotation_matrix,
                acceleration_voltage=200,
                excitation_error=0.01,
                intensity_scale=0xFFFF,
            )
        # TODO diffraction shift

        # TODO noise

        # Convert to int array
        reflections = (reflections).astype(np.uint32)

        return reflections
