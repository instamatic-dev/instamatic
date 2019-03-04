from pathlib import Path

import time
import numpy as np
import logging
logger = logging.getLogger(__name__)

import atexit

from instamatic import config


class CameraSimu(object):
    """docstring for CameraSimu"""

    def __init__(self, name="simulate"):
        """Initialize camera module """
        super(CameraSimu, self).__init__()

        self.name = name

        self.establishConnection()

        self.load_defaults()

        msg = f"Camera {self.getName()} initialized"
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = True

    def getImage(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine

        exposure: exposure time in seconds
        binsize: which binning to use
        """

        if not exposure:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        time.sleep(exposure)

        arr = np.random.randint(256, size=self.dimensions)

        return arr

    def isCameraInfoAvailable(self) -> bool:
        """Check if the camera is available"""
        return True

    def getDimensions(self) -> (int, int):
        """Get the dimensions reported by the camera"""
        return self.dimensions

    def getName(self) -> str:
        """Get the name reported by the camera"""
        return self.name

    def establishConnection(self) -> None:
        """Establish connection to the camera"""
        res = 1
        if res != 1:
            raise RuntimeError(f"Could not establish camera connection to {self.name}")

    def releaseConnection(self) -> None:
        """Release the connection to the camera"""
        name = self.getName()
        msg = f"Connection to camera '{name}' released" 
        logger.info(msg)
