from __future__ import annotations

import atexit
import logging
import time
from typing import Tuple

import numpy as np

from instamatic._typing import float_deg
from instamatic.camera.camera_base import CameraBase
from instamatic.config import microscope as microscope_config

logger = logging.getLogger(__name__)


def _get_reciprocal_unit_cell(
    a: float, b: float, c: float, alpha: float, beta: float, gamma: float
) -> np.ndarray:
    # Copied from diffpy.structure
    ca = np.cos(np.deg2rad(alpha))
    cb = np.cos(np.deg2rad(beta))
    cg = np.cos(np.deg2rad(gamma))
    sa = np.sin(np.deg2rad(alpha))
    sb = np.sin(np.deg2rad(beta))
    cgr = (ca * cb - cg) / (sa * sb)
    sgr = np.sqrt(1.0 - cgr * cgr)
    Vunit = np.sqrt(1.0 + 2.0 * ca * cb * cg - ca * ca - cb * cb - cg * cg)
    ar = sa / (a * Vunit)
    base = np.array(
        [[1.0 / ar, -cgr / sgr / ar, cb * a], [0.0, b * sa, b * ca], [0.0, 0.0, c]],
    )
    recbase = np.linalg.inv(base)
    return recbase


def _euler_angle_z_to_matrix(theta: float_deg) -> np.ndarray:
    c = np.cos(np.deg2rad(theta))
    s = np.sin(np.deg2rad(theta))
    return np.asarray(
        [
            [c, -s, 0, 0],
            [s, c, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
    )


def _euler_angle_x_to_matrix(theta: float_deg) -> np.ndarray:
    c = np.cos(np.deg2rad(theta))
    s = np.sin(np.deg2rad(theta))
    return np.asarray(
        [
            [1, 0, 0, 0],
            [0, c, -s, 0],
            [0, s, c, 0],
            [0, 0, 0, 1],
        ]
    )


def _euler_angle_y_to_matrix(theta: float_deg) -> np.ndarray:
    c = np.cos(np.deg2rad(theta))
    s = np.sin(np.deg2rad(theta))
    return np.asarray(
        [
            [c, 0, s, 0],
            [0, 1, 0, 0],
            [-s, 0, c, 0],
            [0, 0, 0, 1],
        ]
    )


class CameraSimu(CameraBase):
    streamable = True

    def __init__(self, name: str = 'simulate'):
        """Simple simulation of the TEM. MUST START IN IMAGE MODE!

        Consisting of randomly dispersed crystals.
        One crystal is guaranteeed to be at (0, 0) on the stage
        Each crystal is perfectly flat, and perfectly round.
        All crystals have the same unit cell.

        The simulation assumes a 200kV convergent beam, always.
        Magnification and/or camera length is read from the TEM, which the simulation connects to after a few seconds.
        This is used in combination with the detector pixel size to scale the image/diffraction pattern.

        Image mode:
        Crystals have different "thickness", yielding different gray-values proportional to thickness.
        This gray-value never changes, regardless of tilt, orientation ect.
        A cross centered at (0, 0) is added for convenience

        Diffraction mode:
        All crystals visible in image mode contribute to the diffraction pattern.
        Only reflection positions are accurately simulated.
        Intensities are computed by a single Gaussian, rather than proper structure factor computing.
        Also scaled with excitation error
        """
        # Defaults
        self.n_crystals = 1000000
        self.grid_diameter = 3.05  # mm
        self.min_crystal_radius = 100  # nm
        self.max_crystal_radius = 1000  # nm
        self.unit_cell_a = 10  # Å
        self.unit_cell_b = 15  # Å
        self.unit_cell_c = 25  # Å
        self.unit_cell_alpha = 90  # Degrees
        self.unit_cell_beta = 90  # Degrees
        self.unit_cell_gamma = 120  # Degrees
        self.max_excitation_error = 0.005
        self.spot_radius = 3  # pixels
        super().__init__(name)

        self.ready = False

        # Real-space setup
        grid_radius_nm = self.grid_diameter * 1e6 / 2
        self.crystal_x = np.random.uniform(-grid_radius_nm, grid_radius_nm, self.n_crystals)
        self.crystal_y = np.random.uniform(-grid_radius_nm, grid_radius_nm, self.n_crystals)
        self.crystal_r = np.random.uniform(
            self.min_crystal_radius, self.max_crystal_radius, self.n_crystals
        )
        self.crystal_t = np.random.uniform(0.4, 1.0, self.n_crystals)
        self.crystal_euler_angle_phi_1 = np.random.uniform(0, 360, self.n_crystals)
        self.crystal_euler_angle_psi = np.random.uniform(0, 180, self.n_crystals)
        self.crystal_euler_angle_phi_2 = np.random.uniform(0, 360, self.n_crystals)

        # Ensure one crystal is always at (0, 0) and 1µm radius
        self.crystal_x[0] = 0
        self.crystal_y[0] = 0
        self.crystal_r[0] = 1000

        # Reciprocal-space setup
        reciprocal_unit_cell = _get_reciprocal_unit_cell(
            self.unit_cell_a,
            self.unit_cell_b,
            self.unit_cell_c,
            self.unit_cell_alpha,
            self.unit_cell_beta,
            self.unit_cell_gamma,
        )
        d_min = 0.8  # Å
        max_h = round(self.unit_cell_a / d_min)
        max_k = round(self.unit_cell_b / d_min)
        max_l = round(self.unit_cell_c / d_min)
        hkl = np.asarray(
            [
                [h, k, l]
                for h in range(-max_h, max_h + 1)  # noqa: E741
                for k in range(-max_k, max_k + 1)  # noqa: E741
                for l in range(-max_l, max_l + 1)  # noqa: E741
            ]
        ).T
        # Filter out the edges that are too high res
        k_vec = reciprocal_unit_cell @ hkl
        k = np.linalg.norm(k_vec, axis=0)
        self.reflections = k_vec[:, k < 1 / d_min]
        # Calculate intensity of reflections
        k = k[k < 1 / d_min]
        F = 5 * np.exp(-1.5 * k**2)  # "Structure factor" scaling with a Gaussian
        self.reflection_intensity = F**2

        # Keep track of these, not accessible when outside corresponding mode
        self.mag = None
        self.camera_length = None

        msg = f'Camera {self.get_name()} initialized'
        logger.info(msg)

        atexit.register(self.release_connection)

        # EMMENU variables
        self._image_index = 0
        self._exposure = self.default_exposure
        self._autoincrement = True
        self._start_record_time = -1

    def establish_connection(self):
        pass

    def actually_establish_connection(self):
        # Hack to establish connection with running TEM
        if self.ready:
            return
        import time

        time.sleep(2)
        from instamatic.controller import get_instance

        ctrl = get_instance()
        self.tem = ctrl.tem

        if self.tem.getFunctionMode() == 'diff':
            # raise RuntimeError('Simulation cannot start in diffraction mode')
            # Assume something reasonable instead
            self.mag = 25000
        else:
            self.mag = self.tem.getMagnification()

        # If the TEM is a simulated one (i.e. random beam shift), reset beam shift
        # Otherwise, reseting the stage will not get you to (0, 0)
        if self.tem.name == 'simulate':
            self.tem.setBeamShift(0, 0)

        self.ready = True

    def release_connection(self):
        self.tem = None
        self.ready = False

    def _stage_pose(self) -> np.ndarray:
        """Compute the 4x4 affine transform of the stage.

        Multiply with a position on the stage (x, y) (including z=0 and
        the final 1) to get a position relative to the optical axis.
        """
        x, y, z, a, b = self.tem.getStagePosition()

        # Using 'ZXY' intrinsic euler angles
        Z = _euler_angle_z_to_matrix(self.camera_rotation_vs_stage_xy)
        X = _euler_angle_x_to_matrix(a)
        Y = _euler_angle_y_to_matrix(b)

        T = np.asarray(
            [
                [1, 0, 0, -x],
                [0, 1, 0, -y],
                [0, 0, 1, -z],
                [0, 0, 0, 1],
            ]
        )

        return Z @ X @ Y @ T

    def get_realspace_image(
        self, xx: np.ndarray, yy: np.ndarray, crystal_indices: np.ndarray
    ) -> np.ndarray:
        # Only crystals and void, no mesh or anything
        out = np.zeros_like(xx)
        for x, y, r, t in zip(
            self.crystal_x[crystal_indices],
            self.crystal_y[crystal_indices],
            self.crystal_r[crystal_indices],
            self.crystal_t[crystal_indices],
        ):
            # thickness multiplied by mask of where the crystal is
            mask = ((xx - x) ** 2 + (yy - y) ** 2) < r**2
            out += t * mask.astype(float)
        # Invert and scale
        out = 0xF000 * (1 - out)
        # Add some noise
        out *= np.random.uniform(0.9, 1.1, out.shape)
        # Add cross at (0, 0)
        width = 50  # nm
        out[(np.abs(xx) < width) | (np.abs(yy) < width)] = 0
        return out.astype(int)

    def get_diffraction_image(
        self, shape: Tuple[int, int], crystal_indices: np.ndarray
    ) -> np.ndarray:
        out = np.zeros(shape)
        pose = self._stage_pose()

        # Handle camera length
        wavelength = microscope_config.wavelength
        detector_half_width = self.physical_pixelsize * self.dimensions[0] // 2
        max_theta = np.arctan(detector_half_width / (self.camera_length))
        max_recip_len = 2 * np.sin(max_theta) / wavelength
        for phi1, psi, phi2, t in zip(
            self.crystal_euler_angle_phi_1[crystal_indices],
            self.crystal_euler_angle_psi[crystal_indices],
            self.crystal_euler_angle_phi_2[crystal_indices],
            self.crystal_t[crystal_indices],
        ):
            # Crystal orientation, Bunge convention for euler angles
            X1 = _euler_angle_x_to_matrix(phi1)[:-1, :-1]
            Z = _euler_angle_z_to_matrix(psi)[:-1, :-1]
            X2 = _euler_angle_x_to_matrix(phi2)[:-1, :-1]
            R = pose[:-1, :-1] @ X1 @ Z @ X2
            beam_direction = R @ np.array([0, 0, -1])

            # Find intersect with Ewald's sphere, by computing excitation error
            # Instead of rotating all vectors, rotate Ewald's sphere (i.e. the beam) to find intersections.
            # Then only rotate the intersecting vectors.
            # Using notation from https://en.wikipedia.org/wiki/Line%E2%80%93sphere_intersection
            r = 1 / wavelength
            u = beam_direction
            c = r * u
            o = self.reflections

            diff = o.T - c
            dot = np.dot(u, diff.T)
            nabla = dot**2 - np.sum(diff**2, axis=1) + r**2
            # We know the relrods (assuming infinite length) are all going to intersect twice
            # Therefore, no need to look at the sign of nabla
            # We also know only the smaller root is important, i.e. -sqrt(nabla)
            sqrt_nabla = np.sqrt(nabla)
            d = -dot - sqrt_nabla

            intersection = np.abs(d) < self.max_excitation_error
            vecs = self.reflections[:, intersection]
            intensities = self.reflection_intensity[intersection]
            # Linear excitation error scaling
            intensities *= 1 - np.abs(d[intersection]) / self.max_excitation_error

            # Project vectors onto camera, ignoring curvature
            projected_vecs = R.T @ vecs

            # Prepare image
            for intensity, (xv, yv, _) in zip(intensities, projected_vecs.T):
                x = xv / max_recip_len * shape[0] / 2 + shape[0] / 2
                y = yv / max_recip_len * shape[1] / 2 + shape[1] / 2
                if not 0 <= x < shape[0]:
                    continue
                if not 0 <= y < shape[1]:
                    continue
                min_x = round(max(0, x - self.spot_radius))
                max_x = round(min(shape[1], x + self.spot_radius))
                min_y = round(max(0, y - self.spot_radius))
                max_y = round(min(shape[0], y + self.spot_radius))
                out[min_y:max_y, min_x:max_x] = intensity
        # Scale. Direct beam intensity is 25
        out = out * 0x8000 / 25
        return out.astype(int)

    def get_image(self, exposure: float = None, binsize: int = None, **kwargs) -> np.ndarray:
        self.actually_establish_connection()

        if exposure is None:
            exposure = self.default_exposure
        if binsize is None:
            binsize = self.default_binsize

        mode = self.tem.getFunctionMode()
        mag = self.tem.getMagnification()
        if mode == 'diff':
            self.camera_length = mag
        else:
            self.mag = mag

        shape_x, shape_y = self.get_camera_dimensions()
        shape = (shape_x // binsize, shape_y // binsize)

        # Compute "illuminated area" (really, what part of the stage is visible on the image)
        real_pixel_size = self.physical_pixelsize * 1e6  # nm
        stage_pixel_size = real_pixel_size / self.mag
        r = stage_pixel_size * (self.dimensions[0] ** 2 + self.dimensions[1] ** 2) ** 0.5 / 2

        # Should gun shift also be considered?
        x, y = self.tem.getBeamShift()
        # x, y, r is now center and radius of beam, compared to optical axis

        # Compute pixel coordinates on stage that are illuminated
        R = self._stage_pose()
        rp = r / 2**0.5  # Convert from full radius to square inside the circle
        x_beam_on_stage = np.linspace(x - rp, x + rp, shape[0])
        y_beam_on_stage = np.linspace(y - rp, y + rp, shape[1])
        # meshgrid of x, y, z and 1 (for the affine transform)
        z = self.tem.getStagePosition()[2]
        p_beam_on_stage = np.array(
            [p.flatten() for p in np.meshgrid(x_beam_on_stage, y_beam_on_stage, [z], [1])]
        )
        p_beam_in_column = np.linalg.inv(R) @ p_beam_on_stage
        xx = p_beam_in_column[0, :].reshape(shape)
        yy = p_beam_in_column[1, :].reshape(shape)
        # xx and yy are now 2d coordinate arrays of each pixel on the stage

        # Find which crystals are illuminated
        p_crystals = np.vstack(
            (
                self.crystal_x,
                self.crystal_y,
                np.zeros(self.n_crystals),
                np.ones(self.n_crystals),
            )
        )
        x_beam_center_on_stage, y_beam_center_on_stage, _, _ = np.linalg.inv(R) @ np.array(
            [x, y, 0, 1]
        )
        c_ind = (
            (p_crystals[0, :] - x_beam_center_on_stage) ** 2
            + (p_crystals[1, :] - y_beam_center_on_stage) ** 2
        ) < (self.crystal_r + r) ** 2
        # c_ind is now a boolean array of which crystals contribute to the image/diffraction pattern

        if mode == 'diff':
            return self.get_diffraction_image(
                shape,
                c_ind,
            )
        else:
            return self.get_realspace_image(xx, yy, c_ind)

    def acquire_image(self) -> int:
        """For TVIPS compatibility."""
        return 1

    def is_camera_info_available(self) -> bool:
        """Check if the camera is available."""
        return True

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    # Mimic EMMENU API

    def get_emmenu_version(self) -> str:
        return 'simu'

    def get_camera_type(self) -> str:
        return 'SimuType'

    def get_current_config_name(self) -> str:
        return 'SimuCfg'

    def set_autoincrement(self, value):
        self._autoincrement = value

    def get_autoincrement(self):
        return self._autoincrement

    def set_image_index(self, value):
        self._image_index = value

    def get_image_index(self):
        return self._image_index

    def stop_record(self) -> None:
        t1 = self._start_record_time
        if t1 >= 0:
            t2 = time.perf_counter()
            n_images = int((t2 - t1) / self._exposure)
            new_index = self.get_image_index() + n_images
            self.set_image_index(new_index)
            print('stop_record', t1, t2, self._exposure, new_index)
            self._start_record_time = -1
        else:
            pass

    def start_record(self) -> None:
        self._start_record_time = time.perf_counter()

    def stop_liveview(self) -> None:
        self.stop_record()
        print('Liveview stopped')

    def start_liveview(self, delay=3.0) -> None:
        time.sleep(delay)
        print('Liveview started')

    def set_exposure(self, exposure_time: int) -> None:
        self._exposure = exposure_time / 1000

    def get_exposure(self) -> int:
        return self._exposure

    def get_timestamps(self, start_index, end_index):
        return list(range(20))

    def write_tiffs(
        self, start_index: int, stop_index: int, path: str, clear_buffer=True
    ) -> None:
        pass
