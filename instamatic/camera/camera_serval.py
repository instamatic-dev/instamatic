import atexit
import logging
from pathlib import Path

import numpy as np
from pyserval import Camera as ServalCamera

from instamatic import config
logger = logging.getLogger(__name__)


class CameraServal:
    """Interfaces with Serval from ASI."""

    def __init__(self, name='serval'):
        """Initialize camera module."""
        super().__init__()

        self.name = name

        self.load_defaults()

        self.establishConnection()

        msg = f'Camera {self.getName()} initialized'
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.streamable = True

        self.__dict__.update(config.camera.mapping)

    def getImage(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
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

        arr = self.conn.get_image(ExposureTime=exposure)

        return arr

    def getImageDimensions(self) -> (int, int):
        """Get the binned dimensions reported by the camera."""
        binning = self.getBinning()
        dim_x, dim_y = self.getCameraDimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    def getCameraDimensions(self) -> (int, int):
        """Get the dimensions reported by the camera."""
        return self.dimensions

    def getName(self) -> str:
        """Get the name reported by the camera."""
        return self.name

    def establishConnection(self) -> None:
        """Establish connection to the camera."""
        self.conn = ServalCamera(self.url,
                                 self.bpc_file_path,
                                 self.dacs_file_path,
                                 )

        self.conn.connect()
        self.conn.configure()
        self.conn.set_detector_config(**self.detector_config)

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        name = self.getName()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


if __name__ == '__main__':
    cam = CameraServal()
    from IPython import embed
    embed()
