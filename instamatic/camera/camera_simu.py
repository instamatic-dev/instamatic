from pathlib import Path

import time
import numpy as np
import logging
logger = logging.getLogger(__name__)

import atexit

from instamatic import config


class CameraSimu(object):
    """docstring for Camera"""

    def __init__(self, kind="simulate"):
        """Initialize camera module
        """
        super(CameraSimu, self).__init__()

        self.name = kind

        self.establishConnection()

        self.load_defaults()

        msg = "Camera {} initialized".format(self.getName())
        logger.info(msg)

        atexit.register(self.releaseConnection)
    
    def load_defaults(self):
        self.defaults = config.camera

        self.default_exposure = self.defaults.default_exposure
        self.default_binsize = self.defaults.default_binsize
        self.possible_binsizes = self.defaults.possible_binsizes
        self.dimensions = self.defaults.dimensions
        self.xmax, self.ymax = self.dimensions

        self.streamable = True

    def getImage(self, exposure=None, binsize=None, **kwargs):
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

    def getCameraCount(self):
        return 1

    def isCameraInfoAvailable(self):
        """Return Boolean"""
        return True

    def getDimensions(self):
        """Return tuple shape: x,y"""
        return self.dimensions

    def getName(self):
        """Return string"""
        return self.name

    def establishConnection(self):
        res = 1
        if res != 1:
            raise RuntimeError("Could not establish camera connection to {}".format(self.name))

    def releaseConnection(self):
        name = self.getName()
        msg = "Connection to camera {} released".format(name)
        logger.info(msg)
