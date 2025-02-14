from __future__ import annotations

import atexit
import ctypes
import logging
import platform
import time
from ctypes import (
    POINTER,
    addressof,
    byref,
    c_bool,
    c_double,
    c_float,
    c_int,
    c_long,
    c_wchar_p,
    create_unicode_buffer,
)
from pathlib import Path
from typing import Tuple

import numpy as np

from instamatic import config
from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)


SYMBOLS = {}

if platform.architecture()[0] == '32bit':
    DLLPATH_SIMU = 'CCDCOM2_x86_simulation.dll'
    DLLPATH_GATAN = 'CCDCOM2_x86_gatan.dll'

    SYMBOLS['actual'] = {
        'acquireImageNewFloat': 'acquireImageNewFloat',
        'acquireImageNewInt': 'acquireImageNewInt',
        'cameraCount': None,
        'cameraDimensions': 'cameraDimensions',
        'cameraName': 'cameraName',
        'CCDCOM2_release': 'CCDCOM2_release',
        'initCCDCOM': 'initCCDCOM',
        'isCameraInfoAvailable': 'isCameraInfoAvailable',
        'releaseCCDCOM': 'releaseCCDCOM',
    }
    SYMBOLS['simu'] = {
        'acquireImageNewFloat': '?acquireImageNewFloat@@YAHHHHHHN_NPAPAMPAH2@Z',
        'acquireImageNewInt': '?acquireImageNewInt@@YAHHHHHPAH00HN_N@Z',
        'cameraCount': '?cameraCount@@YAHXZ',
        'cameraDimensions': '?cameraDimensions@@YA_NPAH0@Z',
        'cameraName': '?cameraName@@YA_NPA_WH@Z',
        'CCDCOM2_release': '?CCDCOM2_release@@YAXPAM@Z',
        'initCCDCOM': '?initCCDCOM@@YAHH@Z',
        'isCameraInfoAvailable': '?isCameraInfoAvailable@@YA_NXZ',
        'releaseCCDCOM': '?releaseCCDCOM@@YAXXZ',
    }
else:
    DLLPATH_SIMU = 'CCDCOM2_x64_simulation.dll'
    DLLPATH_GATAN = 'CCDCOM2_x64_gatan.dll'

    SYMBOLS['actual'] = {
        'acquireImageNewFloat': '?acquireImageNewFloat@@YAHHHHHHN_NPEAPEAMPEAH2@Z',
        'acquireImageNewInt': '?acquireImageNewInt@@YAHHHHHPEAH00HN_N@Z',
        'cameraCount': '?cameraCount@@YAHXZ',
        'cameraDimensions': '?cameraDimensions@@YA_NPEAH0@Z',
        'cameraName': '?cameraName@@YA_NPEA_WH@Z',
        'CCDCOM2_release': '?CCDCOM2_release@@YAXPEAM@Z',
        'initCCDCOM': '?initCCDCOM@@YAHH@Z',
        'isCameraInfoAvailable': '?isCameraInfoAvailable@@YA_NXZ',
        'releaseCCDCOM': '?releaseCCDCOM@@YAXXZ',
    }

    SYMBOLS['simu'] = SYMBOLS['actual']


class CameraDLL(CameraBase):
    """Interface with the CCDCOM DLLs to connect to the gatan software."""

    streamable = False

    def __init__(self, name: str = 'gatan'):
        """Initialize camera module.

        name:
            'gatan'
            'simulateDLL'
        """
        super().__init__(name)

        cameradir = Path(__file__).parent

        if name == 'simulateDLL':
            libpath = cameradir / DLLPATH_SIMU
            symbols = SYMBOLS['simu']
        elif name == 'gatan':
            libpath = cameradir / DLLPATH_GATAN
            symbols = SYMBOLS['actual']
        else:
            raise ValueError(f'No such camera: {name}')

        try:
            lib = ctypes.cdll.LoadLibrary(str(libpath))
        except OSError as e:
            print(e)
            raise RuntimeError(f'Cannot load DLL: {libpath}')

        # Use dependency walker to get function names from DLL: http://www.dependencywalker.com/
        self._acquireImageNewFloat = getattr(lib, symbols['acquireImageNewFloat'])
        self._acquireImageNewFloat.argtypes = [
            c_int,
            c_int,
            c_int,
            c_int,
            c_int,
            c_double,
            c_bool,
            POINTER(POINTER(c_float)),
            POINTER(c_int),
            POINTER(c_int),
        ]

        # self._cameraCount = getattr(lib, symbols['cameraCount'])
        # self._cameraCount.restype = c_int

        self._cameraDimensions = getattr(lib, symbols['cameraDimensions'])
        self._cameraDimensions.argtypes = [POINTER(c_long), POINTER(c_long)]

        self._cameraName = getattr(lib, symbols['cameraName'])
        self._cameraName.argtypes = [c_wchar_p, c_int]
        self._cameraName.restype = c_bool

        self._CCDCOM2release = getattr(lib, symbols['CCDCOM2_release'])
        self._CCDCOM2release.argtypes = [POINTER(c_float)]

        self._initCCDCOM = getattr(lib, symbols['initCCDCOM'])
        self._initCCDCOM.restype = c_int

        self._isCameraInfoAvailable = getattr(lib, symbols['isCameraInfoAvailable'])
        self._isCameraInfoAvailable.restype = c_bool

        self._releaseCCDCOM = getattr(lib, symbols['releaseCCDCOM'])

        self.establish_connection()

        msg = f'Camera {self.get_name()} initialized'
        logger.info(msg)

        # dim_x, dim_y = self.get_image_dimensions()
        # print(f"Dimensions {dim_x}x{dim_y}")
        # print(f"Info {self.is_camera_info_available()} | Count {self.getCameraCount()}")

        atexit.register(self.release_connection)

    def get_image(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine.

        exposure: exposure time in seconds
        binsize: which binning to use
        showindm: show image in digital micrograph
        xmin, xmax, ymin, ymax: retrieve image with smaller size from a subset of pixels
        """

        if not exposure:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        xmin = kwargs.get('xmin', 0)
        xmax = kwargs.get('xmax', self.dimensions[0])
        ymin = kwargs.get('ymin', 0)
        ymax = kwargs.get('ymax', self.dimensions[1])
        showindm = kwargs.get('showindm', False)

        if binsize not in self.possible_binsizes:
            raise ValueError(
                f'Cannot use binsize={binsize}..., should be one of {self.possible_binsizes}'
            )

        pdata = POINTER(c_float)()
        pnImgWidth = c_int(0)
        pnImgHeight = c_int(0)
        self._acquireImageNewFloat(
            ymin,
            xmin,
            ymax,
            xmax,
            binsize,
            exposure,
            showindm,
            byref(pdata),
            byref(pnImgWidth),
            byref(pnImgHeight),
        )
        xres = pnImgWidth.value
        yres = pnImgHeight.value
        print(f'shape: {xres} {yres}, binsize: {binsize}')
        arr = np.ctypeslib.as_array(
            (c_float * xres * yres).from_address(addressof(pdata.contents))
        )
        # memory is not shared between python and C, so we need to copy array
        arr = arr.copy()
        # next we can release pdata memory so that it isn't kept in memory
        self._CCDCOM2release(pdata)

        if self.name == 'simulateDLL':
            # add some noise to static simulated images
            arr *= np.random.random((xres, yres)) + 0.5
            time.sleep(exposure)

        return arr

    def is_camera_info_available(self) -> bool:
        """Return the status of the camera."""
        return self._isCameraInfoAvailable()

    def get_camera_dimensions(self) -> Tuple[int, int]:
        """Return the dimensions reported by the camera."""
        pnWidth = c_int(0)
        pnHeight = c_int(0)
        self._cameraDimensions(byref(pnWidth), byref(pnHeight))
        return pnWidth.value, pnHeight.value

    def get_name(self) -> str:
        """Return the name reported by the camera."""
        buf = create_unicode_buffer(20)
        self._cameraName(buf, 20)
        return buf.value

    def establish_connection(self) -> None:
        """Establish connection to the camera."""
        res = self._initCCDCOM(20120101)
        if res != 1:
            raise RuntimeError(f'Could not establish camera connection to {self.name}')

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        name = self.get_name()
        self._releaseCCDCOM()
        msg = f'Connection to camera {name} released'
        logger.info(msg)


if __name__ == '__main__':
    cam = CameraDLL()

    from IPython import embed

    embed()
