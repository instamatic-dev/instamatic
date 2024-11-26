from __future__ import annotations

import warnings

import numpy as np
from scipy.spatial.transform import Rotation

from instamatic.camera.simulate.crystal import Crystal
from instamatic.camera.simulate.grid import Grid
from instamatic.camera.simulate.sample import Sample
from instamatic.camera.simulate.warnings import NotImplementedWarning


class Stage:
    def __init__(
        self,
        num_crystals: int = 100_000,
        min_crystal_size: float = 100,
        max_crystal_size: float = 1000,
        random_seed: int = 100,
    ) -> None:
        self.x = 0
        self.y = 0
        self.z = 0
        self.alpha_tilt = 0
        self.beta_tilt = 0
        self.in_plane_rotation = 0  # TODO change this with focus/magnification
        self.rotation_matrix = np.eye(3)
        self.origin = np.array([0, 0, 0])

        # TODO parameters
        self.grid = Grid()

        self.rng = np.random.Generator(np.random.PCG64(random_seed))

        # TODO parameters
        self.crystal = Crystal(*self.rng.uniform(5, 25, 3), *self.rng.uniform(80, 110, 3))

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

    def image_extent_to_sample_coordinates(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        warnings.warn(
            'Tilting is not fully implemented yet', NotImplementedWarning, stacklevel=2
        )
        # https://en.wikipedia.org/wiki/Line%E2%80%93plane_intersection
        n = self.rotation_matrix @ np.array([0, 0, 1])
        p0 = self.origin
        l = np.array([0, 0, 1])  # noqa: E741
        l0 = np.array(
            [
                p.flatten()
                for p in np.meshgrid(
                    np.linspace(x_min, x_max, shape[1]),
                    np.linspace(y_min, y_max, shape[0]),
                    [0],
                )
            ]
        )

        p = l0 + np.array([0, 0, 1])[:, np.newaxis] * np.dot(-l0.T + p0, n) / np.dot(l, n)

        x, y, z = self.rotation_matrix.T @ p
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
        x, y = self.image_extent_to_sample_coordinates(
            shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )

        grid_mask = self.grid.array_from_coords(x, y)

        sample_data = np.ones(shape, dtype=int) * 1000
        for ind, sample in enumerate(self.samples):
            if not sample.range_might_contain_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue
            # TODO better logic here
            sample_data[sample.pixel_contains_crystal(x, y)] = 1000 * (1 - sample.thickness)

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
        x, y = self.image_extent_to_sample_coordinates(
            shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )
        d_min = 1.0

        grid_mask = self.grid.array_from_coords(x, y)

        reflections = np.zeros(shape, dtype=bool)

        if np.all(grid_mask):
            # no transmission
            return reflections.astype(int)

        # TODO diffraction shift, also for pattern
        # Direct beam
        reflections[
            shape[0] // 2 - 4 : shape[0] // 2 + 4, shape[1] // 2 - 4 : shape[1] // 2 + 4
        ] = 1

        for sample in self.samples:
            if not sample.range_might_contain_crystal(
                x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            ):
                continue
            pos = sample.pixel_contains_crystal(x, y)
            if np.all(grid_mask[pos]):
                # Crystal is completely on the grid
                continue

            reflections |= self.crystal.diffraction_pattern_mask(
                shape,
                d_min=d_min,
                rotation_matrix=self.rotation_matrix @ sample.rotation_matrix,
                wavelength=0.02,
                excitation_error=0.01,
            )

        # Simple scaling
        # TODO improve, proper form factors maybe
        # TODO camera length
        kx, ky = np.meshgrid(
            np.linspace(-1 / d_min, 1 / d_min, shape[1]),
            np.linspace(-1 / d_min, 1 / d_min, shape[0]),
        )
        k_squared = kx**2 + ky**2
        scale = 1 / (3 * k_squared + 1)

        scale[~reflections] = 0

        # Convert to int array
        scale = (scale * 1000).astype(int)

        return scale
