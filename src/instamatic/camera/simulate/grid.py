from __future__ import annotations

import numpy as np


class Grid:
    def __init__(
        self,
        diameter: float = 3.05,
        mesh: int = 200,
        pitch: float = 125,
        hole_width: float = 90,
        bar_width: float = 35,
        rim_width: float = 0.225,
    ):
        """TEM grid.

        Parameters
        ----------
        diameter : float, optional
            [mm] Total diameter, by default 3.05
        mesh : int, optional
            [lines/inch] Hole density, by default 200
        pitch : float, optional
            [µm], by default 125
        hole_width : float, optional
            [µm], by default 90
        bar_width : float, optional
            [µm], by default 35
        rim_width : float, optional
            [mm], by default 0.225
        """
        # TODO make mesh set the pitch, bar width and pitch set the hole width ect.
        self.diameter_mm = diameter
        self.radius_nm = 1e6 * diameter / 2
        self.mesh = mesh
        self.pitch_um = pitch
        self.hole_width_um = hole_width
        self.bar_width_um = bar_width
        self.rim_width_mm = rim_width
        self.grid_width_um = self.bar_width_um + self.hole_width_um
        self.grid_width_nm = 1e3 * self.grid_width_um

    def get_rim_filter(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        r_nm = 1e6 * (self.diameter_mm / 2 - self.rim_width_mm)
        return x**2 + y**2 >= r_nm**2

    def get_hole_filter(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x = np.remainder(np.abs(x), self.grid_width_nm)
        y = np.remainder(np.abs(y), self.grid_width_nm)

        # Assume no grid in center, i.e. middle of the bar width
        half_bar_width_nm = 1e3 * self.bar_width_um / 2
        return (
            (x < half_bar_width_nm)
            | (x > (self.grid_width_nm - half_bar_width_nm))
            | (y < half_bar_width_nm)
            | (y > (self.grid_width_nm - half_bar_width_nm))
        )

    def get_center_mark(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        # TODO
        return np.zeros(x.shape, dtype=bool)

    def array_from_coords(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Get mask array for given coordinate arrays (output from
        np.meshgrid). (x, y) = (0, 0) is in the center of the grid.

        Parameters
        ----------
        x : np.ndarray
            x-coordinates
        y : np.ndarray
            y-coordinates

        Returns
        -------
        np.ndarray
            Mask array, False where the grid is blocking
        """
        rim_filter = self.get_rim_filter(x, y)
        grid_filter = self.get_hole_filter(x, y)

        # TODO proper logic for this,
        # as the mark includes a hole in the center which will be overridden by the grid filter
        center_mark = self.get_center_mark(x, y)

        return rim_filter | grid_filter | center_mark

    def array(
        self,
        shape: tuple[int, int],
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> np.ndarray:
        """Get mask array for given ranges. (x, y) = (0, 0) is in the center of
        the grid.

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
            Mask array, False where the grid is blocking
        """
        x, y = np.meshgrid(
            np.linspace(x_min, x_max, shape[1]),
            np.linspace(y_min, y_max, shape[0]),
        )
        return self.array_from_coords(x, y)
