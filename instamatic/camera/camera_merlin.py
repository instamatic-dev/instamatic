import atexit
import logging
import time

import numpy as np

from instamatic import config

logger = logging.getLogger(__name__)


class CameraMerlin:
    """Camera interface for the Quantum Detectors Merlin camera."""

    def __init__(self, name='merlin'):
        """Initialize camera module."""
        super().__init__()

        self.name = name

        self.establishConnection()

        self.load_defaults()

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

        dim_x, dim_y = self.getCameraDimensions()

        dim_x = int(dim_x / binsize)
        dim_y = int(dim_y / binsize)

        time.sleep(exposure)

        arr = np.random.randint(256, size=(dim_x, dim_y))

        return arr

    def isCameraInfoAvailable(self) -> bool:
        """Check if the camera is available."""
        return True

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
        res = 1
        if res != 1:
            raise RuntimeError(f'Could not establish camera connection to {self.name}')

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        name = self.getName()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)
