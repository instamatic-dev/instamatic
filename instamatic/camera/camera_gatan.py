import ctypes
from ctypes import c_int, c_long, c_float, c_double, c_bool, c_wchar_p
from ctypes import POINTER, create_unicode_buffer, byref, addressof

from pathlib import Path

import numpy as np
import platform
import logging
logger = logging.getLogger(__name__)

import atexit
import time

from instamatic import config

SYMBOLS = {}

if platform.architecture()[0] == '32bit':
    DLLPATH_SIMU    = "CCDCOM2_x86_simulation.dll"
    DLLPATH_GATAN   = "CCDCOM2_x86_gatan.dll"

    SYMBOLS["actual"] = {
        'acquireImageNewFloat' : 'acquireImageNewFloat',
        'acquireImageNewInt' : 'acquireImageNewInt',
        'cameraCount' : None,
        'cameraDimensions' : 'cameraDimensions',
        'cameraName' : 'cameraName',
        'CCDCOM2_release' : 'CCDCOM2_release',
        'initCCDCOM' : 'initCCDCOM',
        'isCameraInfoAvailable' : 'isCameraInfoAvailable',
        'releaseCCDCOM' : 'releaseCCDCOM'
        }
    SYMBOLS["simu"] = {
        'acquireImageNewFloat' : '?acquireImageNewFloat@@YAHHHHHHN_NPAPAMPAH2@Z',
        'acquireImageNewInt' : '?acquireImageNewInt@@YAHHHHHPAH00HN_N@Z',
        'cameraCount' : '?cameraCount@@YAHXZ',
        'cameraDimensions' : '?cameraDimensions@@YA_NPAH0@Z',
        'cameraName' : '?cameraName@@YA_NPA_WH@Z',
        'CCDCOM2_release' : '?CCDCOM2_release@@YAXPAM@Z',
        'initCCDCOM' : '?initCCDCOM@@YAHH@Z',
        'isCameraInfoAvailable' : '?isCameraInfoAvailable@@YA_NXZ',
        'releaseCCDCOM' : '?releaseCCDCOM@@YAXXZ'
        }
else:
    DLLPATH_SIMU    = "CCDCOM2_x64_simulation.dll"
    DLLPATH_GATAN   = "CCDCOM2_x64_gatan.dll"

    SYMBOLS["actual"] = {
        'acquireImageNewFloat' : '?acquireImageNewFloat@@YAHHHHHHN_NPEAPEAMPEAH2@Z',
        'acquireImageNewInt' : '?acquireImageNewInt@@YAHHHHHPEAH00HN_N@Z',
        'cameraCount' : '?cameraCount@@YAHXZ',
        'cameraDimensions' : '?cameraDimensions@@YA_NPEAH0@Z',
        'cameraName' : '?cameraName@@YA_NPEA_WH@Z',
        'CCDCOM2_release' : '?CCDCOM2_release@@YAXPEAM@Z',
        'initCCDCOM' : '?initCCDCOM@@YAHH@Z',
        'isCameraInfoAvailable' : '?isCameraInfoAvailable@@YA_NXZ',
        'releaseCCDCOM' : '?releaseCCDCOM@@YAXXZ'
        }

    SYMBOLS["simu"] = SYMBOLS["actual"]


class CameraDLL(object):
    """docstring for Camera"""

    def __init__(self, name="gatan"):
        """Initialize camera module

        name:
            'gatan'
            'simulateDLL'
        """
        super(CameraDLL, self).__init__()

        cameradir = Path(__file__).parent

        if name == "simulateDLL":
            libpath = cameradir / DLLPATH_SIMU
            symbols = SYMBOLS["simu"]
        elif name == "gatan":
            libpath = cameradir / DLLPATH_GATAN
            symbols = SYMBOLS["actual"]
        else:
            raise ValueError(f"No such camera: {name}")

        self.name = name

        try:
            lib = ctypes.cdll.LoadLibrary(str(libpath))
        except WindowsError as e:
            print(e)
            raise RuntimeError(f"Cannot load DLL: {libpath}")

        # Use dependency walker to get function names from DLL: http://www.dependencywalker.com/
        self._acquireImageNewFloat = getattr(lib, symbols['acquireImageNewFloat'])
        self._acquireImageNewFloat.argtypes = [c_int, c_int, c_int, c_int, c_int, c_double, c_bool, POINTER(
            POINTER(c_float)), POINTER(c_int), POINTER(c_int)]

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

        self.establishConnection()

        self.load_defaults()

        msg = f"Camera {self.getName()} initialized"
        logger.info(msg)

        # print("Dimensions {}x{}".format(*self.getDimensions()))
        # print("Info {} | Count {}".format(self.isCameraInfoAvailable(), self.getCameraCount()))

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = False

    def getImage(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine

        exposure: exposure time in seconds
        binsize: which binning to use
        showindm: show image in digital micrograph
        xmin, xmax, ymin, ymax: retrieve image with smaller size from a subset of pixels
        """

        if not exposure:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        xmin = kwargs.get("xmin", 0)
        xmax = kwargs.get("xmax", self.dimensions[0])
        ymin = kwargs.get("ymin", 0)
        ymax = kwargs.get("ymax", self.dimensions[1])
        showindm = kwargs.get("showindm", False)

        if binsize not in self.possible_binsizes:
            raise ValueError(
                "Cannot use binsize={}..., should be one of {}".format(binsize, self.possible_binsizes))

        pdata = POINTER(c_float)()
        pnImgWidth = c_int(0)
        pnImgHeight = c_int(0)
        self._acquireImageNewFloat(ymin, xmin, ymax, xmax, binsize, exposure, showindm, byref(
            pdata), byref(pnImgWidth), byref(pnImgHeight))
        xres = pnImgWidth.value
        yres = pnImgHeight.value
        print(f"shape: {xres} {yres}, binsize: {binsize}")
        arr = np.ctypeslib.as_array(
            (c_float * xres * yres).from_address(addressof(pdata.contents)))
        # memory is not shared between python and C, so we need to copy array
        arr = arr.copy()
        # next we can release pdata memory so that it isn't kept in memory
        self._CCDCOM2release(pdata)

        if self.name == "simulateDLL":
            # add some noise to static simulated images
            arr *= np.random.random((xres, yres)) + 0.5
            time.sleep(exposure)

        return arr

    def isCameraInfoAvailable(self) -> bool:
        """Return the status of the camera"""
        return self._isCameraInfoAvailable()

    def getDimensions(self) -> (int, int):
        """Return the dimensions reported by the camera"""
        pnWidth = c_int(0)
        pnHeight = c_int(0)
        self._cameraDimensions(byref(pnWidth), byref(pnHeight))
        return pnWidth.value, pnHeight.value

    def getName(self) -> str:
        """Return the name reported by the camera"""
        buf = create_unicode_buffer(20)
        self._cameraName(buf, 20)
        return buf.value

    def establishConnection(self) -> None:
        """Establish connection to the camera"""
        res = self._initCCDCOM(20120101)
        if res != 1:
            raise RuntimeError("Could not establish camera connection to {}".format(self.name))

    def releaseConnection(self) -> None:
        """Release the connection to the camera"""
        name = self.getName()
        self._releaseCCDCOM()
        msg = "Connection to camera {} released".format(name) 
        logger.info(msg)
