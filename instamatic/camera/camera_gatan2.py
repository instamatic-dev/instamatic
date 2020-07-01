import atexit
import logging
import sys
import time
from pathlib import Path

import numpy as np

from instamatic import config
from instamatic.camera.gatansocket3 import GatanSocket
logger = logging.getLogger(__name__)


class CameraGatan2:
    """Connect to Digital Microsgraph using the SerialEM Plugin."""

    def __init__(self, name: str = 'gatan2'):
        """Initialize camera module."""
        super().__init__()

        self.name = name

        self.g = GatanSocket()

        self._recording = False

        self.load_defaults()

        msg = f'Camera `{self.getCameraName()}` ({self.name}) initialized'
        # print(msg)
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self) -> None:
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.__dict__.update(config.camera.mapping)

        self.streamable = False

    def getCameraType(self) -> str:
        """Get the name of the camera currently in use."""
        raise NotImplementedError

    def getDMVersion(self) -> str:
        """Get the version number of DM."""
        return self.g.GetDMVersion()

    def getCameraDimensions(self) -> (int, int):
        """Get the maximum dimensions reported by the camera."""
        raise NotImplementedError

    def getImageDimensions(self) -> (int, int):
        """Get the dimensions of the image."""
        binning = self.getBinning()
        dim_x, dim_y = self.getCameraDimensions()
        return int(dim_x / binning), int(dim_y / binning)

    def getPhysicalPixelsize(self) -> (int, int):
        """Returns the physical pixel size of the camera nanometers."""
        raise NotImplementedError

    def getBinning(self) -> int:
        """Returns the binning corresponding to the currently selected camera
        config."""
        raise NotImplementedError

    def getCameraName(self) -> str:
        """Get the name reported by the camera."""
        return self.name

    def writeTiff(self, filename: str) -> None:
        """Write tiff file using the DM machinery."""
        raise NotImplementedError

    def writeTiffs(self) -> None:
        """Write a series of data in tiff format and writes them to the given
        `path`"""
        raise NotImplementedError

        path = Path(path)
        i = 0

        print(f'Wrote {i+1} images to {path}')

    def getImage(self,
                 exposure=0.400,
                 binning=1,
                 processing='gain normalized',
                 ) -> 'np.array':
        """Acquire image through DM and return data as np array."""

        width, height = self.dimensions
        top = 0
        left = 0
        bottom = height
        right = width

        arr = self.g.getImage(processing=processing,
                              height=height,
                              width=width,
                              binning=binning,
                              top=top,
                              left=left,
                              bottom=bottom,
                              right=right,
                              exposure=exposure,
                              shutterDelay=0,
                              )

        return arr

    def acquireImage(self, **kwargs) -> 'np.array':
        """Acquire image through DM."""
        return self.getImage(**kwargs)

    def get_ready_for_record(self) -> None:
        self.reset_record_vars()

        while True:
            ready_for_acquire = self.get_tag('ready_for_acquire')
            if ready_for_acquire:
                break
            time.sleep(0.5)

        self.set_tag('ready_for_acquire', 0)

    def reset_record_vars(self):
        self.set_tag('start_acquire', 0)
        self.set_tag('stop_acquire', 0)
        self.set_tag('ready_for_acquire', 0)
        self.set_tag('prepare_acquire', 1)
        self.set_tag('finish_acquire', 0)

    def start_record(self) -> None:
        cmd = 'SetPersistentNumberNote("start_acquire", 1)'
        self.g.ExecuteScript(cmd)

    def stop_record(self) -> int:
        cmd = 'SetPersistentNumberNote("stop_acquire", 1)'
        self.g.ExecuteScript(cmd)

    def stop_liveview(self) -> None:
        raise NotImplementedError

    def start_liveview(self, delay: float = 3.0) -> None:
        raise NotImplementedError

    def set_exposure(self, exposure_time: int) -> None:
        """Set exposure time in ms."""
        raise NotImplementedError

    def get_exposure(self) -> int:
        """Return exposure time in ms."""
        raise NotImplementedError

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        msg = f'Connection to camera `{self.getCameraName()}` ({self.name}) released'
        # print(msg)
        logger.info(msg)

    def set_tag(self, key: str, value: float) -> None:
        """Set the tag `key` in the DM persistent parameters."""
        if isinstance(value, str):
            value = value.replace('\\', '\\\\')
            set_tag = f'SetPersistentStringNote("{key}", "{value}")'
        else:
            set_tag = f'SetPersistentNumberNote("{key}", {value})'
        self.g.ExecuteScript(set_tag)

    def get_tag(self, key: str, delete: bool = False) -> float:
        """Get the tag given by `key`.

        Clear the tag if `delete` is specfified`
        get_tag = f'number value\nGetPersistentNumberNote("{key}", value)\nExit(value)'
        value = self.g.ExecuteGetDoubleScript(get_tag)
        """

        if delete:
            self.delete_tag(key)

        return value

    def delete_tag(self, key: str) -> None:
        """Delete the tag `key` in DM."""
        delete_tag = f'DeletePersistentNote("{key}")'
        self.g.ExecuteScript(delete_tag)

    def readout(self) -> dict:
        """Readout tag structure with metadata from last cRED experiment."""
        d = {}

        keys = ('nframes', 'bin_x', 'bin_y', 'cam_res_x', 'cam_res_y', 'image_res_x', 'image_res_y', 'pixelsize_x', 'pixelsize_y',
                'phys_pixelsize_x', 'phys_pixelsize_y', 'total_time', 'exposure')

        for key in keys:
            value = self.get_tag(key, delete=True)
            d[key] = value

        return d


if __name__ == '__main__':
    cam = CameraGatan2()

    from IPython import embed
    embed()

    # set_tag("work_drc", work_drc)  # instamatic work drc
    # set_tag("sample_name", sample_name)  # experiment_x
