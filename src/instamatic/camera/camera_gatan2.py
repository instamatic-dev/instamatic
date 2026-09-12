from __future__ import annotations

import atexit
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

from instamatic import config
from instamatic.camera.camera_base import CameraBase
from instamatic.camera.gatansocket3 import GatanSocket
from instamatic.utils.deprecated import VisibleDeprecationWarning

logger = logging.getLogger(__name__)


class CameraGatan2(CameraBase):
    """Connect to Digital Microsgraph using the SerialEM Plugin."""

    streamable = False

    def __init__(self, name: str = 'gatan2'):
        """Initialize camera module."""
        super().__init__(name)

        self.g = GatanSocket()

        self._recording = False

        self.load_defaults()

        msg = f'Camera `{self.get_camera_name()}` ({self.name}) initialized'
        logger.info(msg)

        atexit.register(self.release_connection)

    def get_camera_type(self) -> str:
        """Get the name of the camera currently in use."""
        raise NotImplementedError

    def get_dm_version(self) -> str:
        """Get the version number of DM."""
        return self.g.GetDMVersion()

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the dimensions of the image."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)

    def get_physical_pixelsize(self) -> Tuple[int, int]:
        """Returns the physical pixel size of the camera nanometers."""
        raise NotImplementedError

    def get_camera_name(self) -> str:
        """Get the name reported by the camera."""
        return self.name

    def write_tiff(self, filename: str) -> None:
        """Write tiff file using the DM machinery."""
        raise NotImplementedError

    def write_tiffs(self) -> None:
        """Write a series of data in tiff format and writes them to the given
        `path`"""
        raise NotImplementedError

        path = Path(path)
        i = 0

        print(f'Wrote {i + 1} images to {path}')

    def get_image(
        self,
        exposure: float | None = None,
        binsize: int | None = None,
        *,
        binning: int | None = None,
        processing: str = 'gain normalized',
        **kwargs,
    ) -> 'np.array':
        """Acquire image through DM and return data as np array.

        Notes
        -----
        Instamatic's public API uses `binsize` everywhere (controller,
        videostream, CLI). Historically this driver used `binning` instead,
        which prevented GUI/Controller code from changing binning.
        This implementation accepts both names. `binsize`, `binning`,
        and `default_binsize` take precedence in this order.
        Use of `binning` is deprecated and might be removed in the future.
        """

        exposure = exposure if exposure is not None else self.default_exposure

        if binning is not None:
            msg = 'Argument `binning` is deprecated since v2.3.0. Use `binsize` instead.'
            warnings.warn(msg, VisibleDeprecationWarning, stacklevel=2)

        if binsize is None:
            binsize = binning if binning is not None else self.default_binsize

        if (p := getattr(self, 'possible_binsizes', [])) and binsize not in p:
            msg = f'Cannot use {binsize=}, should be one of {self.possible_binsizes=}'
            raise ValueError(msg)

        width, height = [int(wh) for wh in self.dimensions][:2]
        top = 0
        left = 0
        bottom = int(height)
        right = int(width)

        arr = self.g.get_image(
            processing=processing,
            height=height,
            width=width,
            binning=binsize,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            exposure=exposure,
            shutterDelay=0,
            **kwargs,
        )

        return arr

    def get_movie(self, n_frames: int, *args, **kwargs) -> Iterator[np.ndarray]:
        """Yield `n_frames` images by repeatedly calling `get_image`.

        The SerialEMCCD socket protocol seems to have no native streaming call,
        so each frame here is a full round trip: re-arm, expose, read. There is
        no guarantee of even dead time or frame spacing - this is a convenience
        wrapper only. Provide a better implementation if you can.
        """
        for _ in range(n_frames):
            yield self.get_image(*args, **kwargs)

    def acquire_image(self, **kwargs) -> 'np.array':
        """Acquire image through DM."""
        return self.get_image(**kwargs)

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

    def establish_connection(self):
        # Already done by the constructor of GatanSocket
        # self.g.connect()
        pass

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        self.g.disconnect()
        msg = f'Connection to camera `{self.get_camera_name()}` ({self.name}) released'
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

        keys = (
            'nframes',
            'bin_x',
            'bin_y',
            'cam_res_x',
            'cam_res_y',
            'image_res_x',
            'image_res_y',
            'pixelsize_x',
            'pixelsize_y',
            'phys_pixelsize_x',
            'phys_pixelsize_y',
            'total_time',
            'exposure',
        )

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
