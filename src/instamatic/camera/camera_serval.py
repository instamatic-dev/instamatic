from __future__ import annotations

import atexit
import logging
import math
from typing import Tuple

import numpy as np
from serval_toolkit.camera import Camera as ServalCamera

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)

# Start servers in serval_toolkit:
# 1. `java -jar .\emu\tpx3_emu.jar`
# 2. `java -jar .\server\serv-2.1.3.jar`
# 3. launch `instamatic`


class CameraServal(CameraBase):
    """Interfaces with Serval from ASI."""

    streamable = True
    MIN_EXPOSURE = 0.000001
    MAX_EXPOSURE = 10.0
    BAD_EXPOSURE_MSG = 'Requested exposure exceeds native Serval support (>0–10s)'

    def __init__(self, name='serval'):
        """Initialize camera module."""
        super().__init__(name)
        self.establish_connection()
        self.dead_time = (
            self.detector_config['TriggerPeriod'] - self.detector_config['ExposureTime']
        )
        logger.info(f'Camera {self.get_name()} initialized')
        atexit.register(self.release_connection)

    def get_image(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        if exposure is None:
            exposure = self.default_exposure
        if exposure < self.MIN_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, exposure)
            return self._get_image_null()
        elif exposure > self.MAX_EXPOSURE:
            ...
        else:
            return self._get_image_single(exposure, binsize, **kwargs)
            logger.warning(f'{self.BAD_EXPOSURE_MSG}: {exposure}')
            n_triggers = math.ceil(exposure / self.MAX_EXPOSURE)
            exposure1 = (exposure + self.dead_time) / n_triggers - self.dead_time
            arrays = self.get_movie(n_triggers, exposure1, binsize, **kwargs)
            array_sum = sum(arrays, np.zeros_like(arrays[0]))
            scaling_factor = exposure / exposure1 * n_triggers  # account for dead time
            return (array_sum * scaling_factor).astype(array_sum.dtype)

    def _get_image_null(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        logger.debug('Creating a synthetic image with zero counts')
        return np.zeros(shape=self.get_image_dimensions(), dtype=np.int32)

    def _get_image_single(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
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

    def get_movie(self, n_frames, exposure=None, binsize=None, **kwargs):
        """Movie acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        n_frames:
            Number of frames to collect
        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        if exposure is None:
            exposure = self.default_exposure
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
        return images

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
