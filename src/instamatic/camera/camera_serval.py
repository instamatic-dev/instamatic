from __future__ import annotations

import atexit
import logging
import math
from itertools import batched
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from serval_toolkit.camera import Camera as ServalCamera

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)

# Start servers in serval_toolkit:
# 1. `java -jar .\emu\tpx3_emu.jar`
# 2. `java -jar .\server\serv-2.1.3.jar`
# 3. launch `instamatic`

Ignore = object()  # sentinel object: informs `_get_images` to get a single image


class CameraServal(CameraBase):
    """Interfaces with Serval from ASI."""

    streamable = True
    MIN_EXPOSURE = 0.000001
    MAX_EXPOSURE = 10.0
    BAD_EXPOSURE_MSG = 'Requested exposure exceeds native Serval support (>0-10s)'

    def __init__(self, name='serval'):
        """Initialize camera module."""
        super().__init__(name)
        self.establish_connection()
        self.dead_time = (
            self.detector_config['TriggerPeriod'] - self.detector_config['ExposureTime']
        )
        logger.info(f'Camera {self.get_name()} initialized')
        atexit.register(self.release_connection)

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Image acquisition interface. If the exposure is not given, the
        default value is read from the config file. Binning is ignored.

        exposure: `float` or `None`
            Exposure time in seconds.
        """
        return self._get_images(n_frames=Ignore, exposure=exposure, **kwargs)

    def get_movie(
        self, n_frames: int, exposure: Optional[float] = None, **kwargs
    ) -> List[np.ndarray]:
        """Movie acquisition interface. If the exposure is not given, the
        default value is read from the config file. Binning is ignored.

        n_frames: `int`
            Number of frames to collect
        exposure: `float` or `None`
            Exposure time in seconds.
        """
        return self._get_images(n_frames=n_frames, exposure=exposure, **kwargs)

    def _get_images(
        self,
        n_frames: Union[int, Ignore],
        exposure: Optional[float] = None,
        **kwargs,
    ) -> Union[np.ndarray, List[np.ndarray]]:
        """General media acquisition dispatcher for other protected methods."""
        n: int = 1 if n_frames is Ignore else n_frames
        e: float = self.default_exposure if exposure is None else exposure

        if n_frames == 0:  # single image is communicated via n_frames = Ignore
            return []

        elif e < self.MIN_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            if n_frames is Ignore:
                return self._get_image_null(exposure=e, **kwargs)
            return [self._get_image_null(exposure=e, **kwargs) for _ in range(n)]

        elif e > self.MAX_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            n1 = math.ceil(e / self.MAX_EXPOSURE)
            e = (e + self.dead_time) / n1 - self.dead_time
            images = self._get_image_stack(n_frames=n * n1, exposure=e, **kwargs)
            if n_frames is Ignore:
                return self._spliced_sum(images, exposure=e)
            return [self._spliced_sum(i, exposure=e) for i in batched(images, n1)]

        else:  # if exposure is within limits
            if n_frames is Ignore:
                return self._get_image_single(exposure=e, **kwargs)
            return self._get_image_stack(n_frames=n, exposure=e, **kwargs)

    def _spliced_sum(self, arrays: Sequence[np.ndarray], exposure: float) -> np.ndarray:
        """Sum a series of arrays while applying a dead time correction."""
        array_sum = sum(arrays, np.zeros_like(arrays[0]))
        total_exposure = len(arrays) * exposure + (len(arrays) - 1) * self.dead_time
        live_fraction = len(arrays) * exposure / total_exposure
        return (array_sum / live_fraction).astype(arrays[0].dtype)

    def _get_image_null(self, **_) -> np.ndarray:
        logger.debug('Creating a synthetic image with zero counts')
        return np.zeros(shape=self.get_image_dimensions(), dtype=np.int32)

    def _get_image_single(self, exposure: float, **_) -> np.ndarray:
        """Request a single frame in the mode in a trigger collection mode."""
        logger.debug(f'Collecting a single image with exposure {exposure} s')
        # Upload exposure settings (Note: will do nothing if no change in settings)
        self.conn.set_detector_config(
            ExposureTime=exposure,
            TriggerPeriod=exposure + self.dead_time,
        )

        # Check if measurement is running. If not: start
        db = self.conn.dashboard
        if db['Measurement'] is None or db['Measurement']['Status'] != 'DA_RECORDING':
            self.conn.measurement_start()

        # Start the acquisition
        self.conn.trigger_start()

        # Request a frame. Will be streamed *after* the exposure finishes
        img = self.conn.get_image_stream(nTriggers=1, disable_tqdm=True)[0]
        arr = np.array(img)
        return arr

    def _get_image_stack(self, n_frames: int, exposure: float, **_) -> list[np.ndarray]:
        """Get a series of images in a mode with minimal dead time."""
        logger.debug(f'Collecting {n_frames} images with exposure {exposure} s')
        mode = 'AUTOTRIGSTART_TIMERSTOP' if self.dead_time else 'CONTINUOUS'
        self.conn.measurement_stop()
        previous_config = self.conn.detector_config
        self.conn.set_detector_config(
            TriggerMode=mode,
            ExposureTime=exposure,
            TriggerPeriod=exposure + self.dead_time,
            nTriggers=n_frames,
        )
        self.conn.measurement_start()
        images = self.conn.get_image_stream(nTriggers=n_frames, disable_tqdm=True)
        self.conn.measurement_stop()
        self.conn.set_detector_config(**previous_config)
        return [np.array(image) for image in images]

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    def establish_connection(self) -> None:
        """Establish connection to the camera."""
        self.conn = ServalCamera()
        self.conn.connect(self.url)
        self.conn.set_chip_config_files(
            bpc_file_path=self.bpc_file_path, dacs_file_path=self.dacs_file_path
        )
        self.conn.set_detector_config(**self.detector_config)

        self.conn.destination = {
            'Image': [
                {
                    # Where to place the preview files (HTTP end-point: GET localhost:8080/measurement/image)
                    'Base': 'http://localhost',
                    # What (image) format to provide the files in.
                    'Format': 'tiff',
                    # What data to build a frame from
                    'Mode': 'count',
                    # 'QueueSize': 2,
                }
            ],
        }

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        self.conn.measurement_stop()
        name = self.get_name()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


if __name__ == '__main__':
    cam = CameraServal()
    from IPython import embed

    embed()
