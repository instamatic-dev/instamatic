import atexit
import logging
from pathlib import Path

import numpy as np
from serval_toolkit.camera import Camera as ServalCamera

from instamatic import config

logger = logging.getLogger(__name__)

# Start servers in serval_toolkit:
# 1. `java -jar .\emu\tpx3_emu.jar`
# 2. `java -jar .\server\serv-2.1.3.jar`
# 3. launch `instamatic`


class CameraServal:
    """Interfaces with Serval from ASI."""

    def __init__(self, name='serval'):
        """Initialize camera module."""
        super().__init__()

        self.name = name

        self.load_defaults()

        self.establish_connection()

        msg = f'Camera {self.get_name()} initialized'
        logger.info(msg)

        atexit.register(self.release_connection)

    def load_defaults(self):
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.streamable = True

        self.__dict__.update(config.camera.mapping)

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
        if not binsize:
            binsize = self.default_binsize

        # Upload exposure settings (Note: will do nothing if no change in settings)
        self.conn.set_detector_config(ExposureTime=exposure,
                                      TriggerPeriod=exposure + 0.00050001)

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
        if not binsize:
            binsize = self.default_binsize

        self.conn.set_detector_config(TriggerMode='CONTINUOUS')

        arr = self.conn.get_images(
            nTriggers=n_frames,
            ExposureTime=exposure,
            TriggerPeriod=exposure,
        )

        return arr

    def get_image_dimensions(self) -> (int, int):
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    def get_camera_dimensions(self) -> (int, int):
        """Get the dimensions reported by the camera."""
        return self.dimensions

    def get_name(self) -> str:
        """Get the name reported by the camera."""
        return self.name

    def establish_connection(self) -> None:
        """Establish connection to the camera."""
        self.conn = ServalCamera()
        self.conn.connect(self.url)
        self.conn.set_chip_config_files(
            bpc_file_path=self.bpc_file_path,
            dacs_file_path=self.dacs_file_path)
        self.conn.set_detector_config(**self.detector_config)
        # Check pixel depth. If 24 bit mode is used, the pgm format does not work
        # (has support up to 16 bits) so use tiff in that case. In other cases (1, 6, 12 bits)
        # use pgm since it is more efficient
        self.pixel_depth = self.conn.detector_config['PixelDepth']
        if self.pixel_depth == 24:
            file_format = 'tiff'
        else:
            file_format = 'pgm'
        self.conn.destination = {
            'Image':
            [{
                # Where to place the preview files (HTTP end-point: GET localhost:8080/measurement/image)
                'Base': 'http://localhost',
                        # What (image) format to provide the files in.
                        'Format': file_format,
                        # What data to build a frame from
                        'Mode': 'count',
            }],
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
