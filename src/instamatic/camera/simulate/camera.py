from __future__ import annotations

from typing import Tuple

from numpy import ndarray

from instamatic.camera.camera_base import CameraBase
from instamatic.camera.simulate.stage import Stage


class CameraSimulation(CameraBase):
    streamable = True

    def __init__(self, name: str = 'simulate'):
        super().__init__(name)

        self.ready = False

        # TODO put parameters into config
        self.stage = Stage()
        self.mag = None

    def establish_connection(self):
        pass

    def actually_establish_connection(self):
        if self.ready:
            return
        import time

        time.sleep(2)
        from instamatic.controller import get_instance

        ctrl = get_instance()
        self.tem = ctrl.tem

        ctrl.stage.set(z=0, a=0, b=0)
        print(self.tem.getStagePosition())
        print(self.stage.samples[0].x, self.stage.samples[0].y)

        self.ready = True

    def release_connection(self):
        self.tem = None
        self.ready = False

    def get_image(self, exposure: float = None, binsize: int = None, **kwargs) -> ndarray:
        self.actually_establish_connection()

        if exposure is None:
            exposure = self.default_exposure
        if binsize is None:
            binsize = self.default_binsize

        # TODO this has inconsistent units. Assume m, deg
        pos = self.tem.getStagePosition()
        if pos is not None and len(pos) == 5:
            x, y, z, alpha, beta = pos
            self.stage.set_position(x=x, y=y, z=z, alpha_tilt=alpha, beta_tilt=beta)

        mode = self.tem.getFunctionMode()

        # Get real-space extent
        if mode == 'diff':
            # TODO this has inconsistent units. Assume mm
            self.camera_length = self.tem.getMagnification()
        else:
            mag = self.tem.getMagnification()
            if isinstance(mag, (float, int)):
                self.mag = mag
            else:
                print(mag, type(mag))
        if self.mag is None:
            raise ValueError('Must start in image mode')

        # TODO consider beam shift, tilt ect.
        x_min, x_max, y_min, y_max = self._mag_to_ranges(self.mag)
        x_min += self.stage.x
        x_max += self.stage.x
        y_min += self.stage.y
        y_max += self.stage.y

        # TODO I mean properly considering them, this has no regard for units ect
        bx, by = self.tem.getBeamShift()
        x_min += bx
        x_max += bx
        y_min += by
        y_max += by

        shape_x, shape_y = self.get_camera_dimensions()
        shape = (shape_x // binsize, shape_y // binsize)

        if mode == 'diff':
            return self.stage.get_diffraction_pattern(
                shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            )
        else:
            return self.stage.get_image(
                shape=shape, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
            )

    def _mag_to_ranges(self, mag: float) -> Tuple[float, float, float, float]:
        # assume 50x = 2mm full size
        half_width = 50 * 1e6 / mag  # 2mm/2 in nm is 1e6
        return -half_width, half_width, -half_width, half_width
