from __future__ import annotations

from typing import Type, TypeVar

import numpy as np
from diffpy import structure as diffpy

Crystal_T = TypeVar('Crystal_T', bound='Crystal')


class Crystal:
    def __init__(
        self, a: float, b: float, c: float, alpha: float, beta: float, gamma: float
    ) -> None:
        """Simulate a primitive crystal given the unit cell. No additional
        symmetry is imposed.

        Standard orientation as defined in diffpy.

        Parameters
        ----------
        a : float
            Unit cell length a, in Å
        b : float
            Unit cell length b, in Å
        c : float
            Unit cell length c, in Å
        alpha : float
            Angle between b and c, in degrees
        beta : float
            Angle between a and c, in degrees
        gamma : float
            Angle between a and b, in degrees
        """
        self.a = a
        self.b = b
        self.c = c
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

        self.lattice = diffpy.Lattice(self.a, self.b, self.c, self.alpha, self.beta, self.gamma)
        self.structure = diffpy.Structure(
            atoms=[diffpy.Atom(xyz=[0, 0, 0])],
            lattice=self.lattice,
        )

    @property
    def a_vec(self) -> np.ndarray:
        return self.lattice.cartesian((1, 0, 0))

    @property
    def b_vec(self) -> np.ndarray:
        return self.lattice.cartesian((0, 1, 0))

    @property
    def c_vec(self) -> np.ndarray:
        return self.lattice.cartesian((0, 0, 1))

    @property
    def a_star_vec(self) -> np.ndarray:
        return self.lattice.reciprocal().cartesian((1, 0, 0))

    @property
    def b_star_vec(self) -> np.ndarray:
        return self.lattice.reciprocal().cartesian((0, 1, 0))

    @property
    def c_star_vec(self) -> np.ndarray:
        return self.lattice.reciprocal().cartesian((0, 0, 1))

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2, 3, 90, 100, 110)

    def real_space_lattice(self, d_max: float) -> np.ndarray:
        """Get the real space lattice as a (n, 3) shape array.

        Parameters
        ----------
        d_max: float
            The maximum d-spacing

        Returns
        -------
        np.ndarray
            Shape (n, 3), lattice points
        """
        max_h = int(d_max // self.a)
        max_k = int(d_max // self.b)
        max_l = int(d_max // self.c)
        hkls = np.array(
            [
                (h, k, l)
                for h in range(-max_h, max_h + 1)  # noqa: E741
                for k in range(-max_k, max_k + 1)  # noqa: E741
                for l in range(-max_l, max_l + 1)  # noqa: E741
            ]
        )
        vecs = self.lattice.cartesian(hkls)
        return vecs

    def reciprocal_space_lattice(self, d_min: float) -> np.ndarray:
        """Get the reciprocal space lattice as a (n, 3) shape array for input
        n.

        Parameters
        ----------
        d_min: float
            Minimum d-spacing included

        Returns
        -------
        np.ndarray
            Shape (n, 3), lattice points
        """
        max_h = int(d_min // self.lattice.ar)
        max_k = int(d_min // self.lattice.br)
        max_l = int(d_min // self.lattice.cr)
        hkls = np.array(
            [
                (h, k, l)
                for h in range(-max_h, max_h + 1)  # noqa: E741
                for k in range(-max_k, max_k + 1)  # noqa: E741
                for l in range(-max_l, max_l + 1)  # noqa: E741
            ]
        )
        vecs = self.lattice.reciprocal().cartesian(hkls)
        return vecs

    def diffraction_pattern_mask(
        self,
        shape: tuple[int, int],
        d_min: float,
        rotation_matrix: np.ndarray,
        wavelength: float,
        excitation_error: float,
    ) -> np.ndarray:
        """Get a diffraction pattern with a given shape, up to a given
        resolution, in a given orientation and wavelength.

        Parameters
        ----------
        shape : tuple[int, int]
            Output shape
        d_min : float
            Minimum d-spacing, in Å
        rotation_matrix : np.ndarray
            Orientation
        wavelength : float
            Wavelength of incident beam, in Å
        excitation_error : float
            Excitation error used for intensity calculation, in reciprocal Å

        Returns
        -------
        np.ndarray
            Diffraction pattern
        """
        out = np.zeros(shape, dtype=bool)
        spot_radius = 3  # pixels

        vecs = self.reciprocal_space_lattice(d_min)
        d = np.sum(vecs**2, axis=1)
        vecs = vecs[d < d_min**2]

        k = 2 * np.pi / wavelength
        k_vec = rotation_matrix @ np.array([0, 0, -k])

        # Find intersect with Ewald's sphere
        q_squared = np.sum((vecs - k_vec) ** 2, axis=1)
        vecs = vecs[
            (q_squared > (k - excitation_error) ** 2)
            & (q_squared < (k + excitation_error) ** 2)
        ]

        # Project onto screen
        vecs_xy = (rotation_matrix.T @ vecs.T).T[:, :-1]  # ignoring curvature

        # Make image
        for vec in vecs_xy:
            x = int(vec[0] * d_min * shape[1] / 2) + shape[1] // 2
            y = int(vec[1] * d_min * shape[0] / 2) + shape[0] // 2
            min_x = max(0, x - spot_radius)
            max_x = min(shape[1], x + spot_radius)
            min_y = max(0, y - spot_radius)
            max_y = min(shape[0], y + spot_radius)
            out[min_y:max_y, min_x:max_x] = 1
        return out

    def __str__(self) -> str:
        return f'{self.__class__.__name__}(a = {self.a}, b = {self.b}, c = {self.c}, alpha = {self.alpha}, beta = {self.beta}, gamma = {self.gamma})'


class CubicCrystal(Crystal):
    def __init__(self, a: float) -> None:
        super().__init__(a, a, a, 90, 90, 90)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1)


class HexagonalCrystal(Crystal):
    def __init__(self, a: float, c: float) -> None:
        super().__init__(a, a, c, 90, 90, 120)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2)


class TrigonalCrystal(Crystal):
    def __init__(self, a: float, alpha: float) -> None:
        super().__init__(a, a, a, alpha, alpha, alpha)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 100)


class TetragonalCrystal(Crystal):
    def __init__(self, a: float, c: float) -> None:
        super().__init__(a, a, c, 90, 90, 90)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2)


class OrthorhombicCrystal(Crystal):
    def __init__(self, a: float, b: float, c: float) -> None:
        super().__init__(a, b, c, 90, 90, 90)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2, 3)


class MonoclinicCrystal(Crystal):
    def __init__(self, a: float, b: float, c: float, beta: float) -> None:
        super().__init__(a, b, c, 90, beta, 90)

    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2, 3, 100)


class TriclinicCrystal(Crystal):
    @classmethod
    def default(cls: Type[Crystal_T]) -> Crystal_T:
        return cls(1, 2, 3, 90, 100, 110)
