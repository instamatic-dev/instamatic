from __future__ import print_function
import ctypes
from ctypes import c_int, c_long, c_float, c_double, c_bool, c_wchar_p
from ctypes import POINTER, create_unicode_buffer, byref, addressof

# import comtypes
# # initial COM in multithread mode if not initialized otherwise
# try:
#     comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
# except WindowsError:
#     comtypes.CoInitialize()

import numpy as np
import os, sys
import logging
logger = logging.getLogger(__name__)

import atexit
import time

from instamatic import config

__version__ = "2016-11-11"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"

__all__ = ["Camera"]

DLLPATH_SIMU    = "CCDCOM2_x64_simulation.dll"
DLLPATH_ORIUS   = "CCDCOM2_orius.dll"
# SoPhy > File > Medipix/Timepix control > Save parametrized settings
# Save updated config for timepix camera
DLLPATH_TIMEPIX = "CCDCOM2_timepix.dll"


def Camera(kind):
    if kind == "simulate":
        return CameraSimu(kind)
    elif kind == "simulateDLL":
        return CameraDLL(kind)
    elif kind == "orius":
        return CameraDLL(kind)
    elif kind == "timepix":
        return CameraDLL(kind)
    else:
        raise ValueError("No such camera: {}".format(kind))


class CameraDLL(object):
    """docstring for Camera"""

    def __init__(self, kind="orius"):
        """Initialize camera module

        kind:
            'orius'
            'timepix'
            'simulateDLL'
        """
        super(CameraDLL, self).__init__()

        # os.environ['PATH'] = cameradir + ';' + os.environ['PATH']

        self._cameradir = cameradir = os.path.join(os.path.dirname(__file__))
        self._curdir = curdir = os.path.abspath(os.curdir)

        if kind == "simulateDLL":
            libpath = os.path.join(cameradir, DLLPATH_SIMU)
        elif kind == "orius":
            libpath = os.path.join(cameradir, DLLPATH_ORIUS)
        elif kind == "timepix":
            libpath = os.path.join(cameradir, DLLPATH_TIMEPIX)
            os.chdir(cameradir)
        else:
            raise ValueError("No such camera: {}".format(kind))

        self.name = kind

        try:
            lib = ctypes.cdll.LoadLibrary(libpath)
        except WindowsError as e:
            print(e)
            raise RuntimeError("Cannot load DLL: {}".format(libpath))

        # Use dependency walker to get function names from DLL: http://www.dependencywalker.com/
        self._acquireImageNewFloat = getattr(lib, '?acquireImageNewFloat@@YAHHHHHHN_NPEAPEAMPEAH2@Z')
        self._acquireImageNewFloat.argtypes = [c_int, c_int, c_int, c_int, c_int, c_double, c_bool, POINTER(
            POINTER(c_float)), POINTER(c_int), POINTER(c_int)]
        self._cameraCount = getattr(lib, '?cameraCount@@YAHXZ')
        self._cameraCount.restype = c_int

        self._cameraDimensions = getattr(lib, '?cameraDimensions@@YA_NPEAH0@Z')
        self._cameraDimensions.argtypes = [POINTER(c_long), POINTER(c_long)]

        self._cameraName = getattr(lib, '?cameraName@@YA_NPEA_WH@Z')
        self._cameraName.argtypes = [c_wchar_p, c_int]
        self._cameraName.restype = c_bool

        self._CCDCOM2release = getattr(lib, '?CCDCOM2_release@@YAXPEAM@Z')
        self._CCDCOM2release.argtypes = [POINTER(c_float)]

        self._initCCDCOM = getattr(lib, '?initCCDCOM@@YAHH@Z')
        self._initCCDCOM.restype = c_int

        self._isCameraInfoAvailable = getattr(lib, '?isCameraInfoAvailable@@YA_NXZ')
        self._isCameraInfoAvailable.restype = c_bool

        self._releaseCCDCOM = getattr(lib, '?releaseCCDCOM@@YAXXZ')

        if kind == "timepix":
            self.establishConnection() # TODO: redirect to logger somehow...
            self._setCorrectionRatio = getattr(lib, '?setCorrectionRatio@@YAXN@Z')
            self._setCorrectionRatio.restype = c_bool
            os.chdir(curdir)
        else:
            self.establishConnection()

        self.load_defaults()

        msg = "Camera {} initialized".format(self.getName())
        logger.info(msg)

        # print "Dimensions {}x{}".format(*self.getDimensions())
        # print "Info {} | Count {}".format(self.isCameraInfoAvailable(), self.getCameraCount())

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        self.defaults = config.camera

        self.default_exposure = self.defaults.default_exposure
        self.default_binsize = self.defaults.default_binsize
        self.possible_binsizes = self.defaults.possible_binsizes
        self.dimensions = self.defaults.dimensions
        self.xmax, self.ymax = self.dimensions

        try:
            correction_ratio = self.defaults.correction_ratio
        except AttributeError:
            pass
        else:
            self._setCorrectionRatio(c_double(1/correction_ratio))

    def getImage(self, t=None, binsize=None, fastmode=False, **kwargs):
        """Image acquisition routine

        t: exposure time in seconds
        binsize: which binning to use
        showindm: show image in digital micrograph
        xmin, xmax, ymin, ymax: retrieve image with smaller size from a subset of pixels
        fastmode: Shaves off approximately 1ms by avoiding conversion to int
        """

        if not t:
            t = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        xmin = kwargs.get("xmin", 0)
        xmax = kwargs.get("xmax", self.xmax)
        ymin = kwargs.get("ymin", 0)
        ymax = kwargs.get("ymax", self.ymax)
        showindm = kwargs.get("showindm", False)

        if binsize not in self.possible_binsizes:
            raise ValueError(
                "Cannot use binsize={}..., should be one of {}".format(binsize, self.possible_binsizes))

        pdata = POINTER(c_float)()
        pnImgWidth = c_int(0)
        pnImgHeight = c_int(0)
        self._acquireImageNewFloat(ymin, xmin, ymax, xmax, binsize, t, showindm, byref(
            pdata), byref(pnImgWidth), byref(pnImgHeight))
        xres = pnImgWidth.value
        yres = pnImgHeight.value
        # print "shape: {} {}".format(xres, yres)
        arr = np.ctypeslib.as_array(
            (c_float * xres * yres).from_address(addressof(pdata.contents)))
        # memory is not shared between python and C, so we need to copy array
        arr = arr.copy()
        # next we can release pdata memory so that it isn't kept in memory
        self._CCDCOM2release(pdata)

        if fastmode:
            return arr
        else:
            return arr.astype(int)

    def getCameraCount(self):
        return self._cameraCount()

    def isCameraInfoAvailable(self):
        """Return Boolean"""
        return self._isCameraInfoAvailable()

    def getDimensions(self):
        """Return tuple shape: x,y"""
        pnWidth = c_int(0)
        pnHeight = c_int(0)
        self._cameraDimensions(byref(pnWidth), byref(pnHeight))
        return pnWidth.value, pnHeight.value

    def getName(self):
        """Return string"""
        buf = create_unicode_buffer(20)
        self._cameraName(buf, 20)
        return buf.value

    def establishConnection(self):
        res = self._initCCDCOM(20120101)
        if res != 1:
            raise RuntimeError("Could not establish camera connection to {}".format(self.name))

    def releaseConnection(self):
        name = self.getName()
        self._releaseCCDCOM()
        msg = "Connection to camera {} released".format(name) 
        logger.info(msg)


class CameraSimu(object):
    """docstring for Camera"""

    def __init__(self, kind="simulate"):
        """Initialize camera module
        """
        super(CameraSimu, self).__init__()

        # os.environ['PATH'] = cameradir + ';' + os.environ['PATH']

        self._cameradir = cameradir = os.path.join(os.path.dirname(__file__))
        self._curdir = curdir = os.path.abspath(os.curdir)

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

        try:
            correction_ratio = self.defaults.correction_ratio
        except AttributeError:
            pass
        else:
            self._setCorrectionRatio(c_double(1/correction_ratio))

    def getImage(self, t=None, binsize=None, fastmode=False, **kwargs):
        """Image acquisition routine

        t: exposure time in seconds
        binsize: which binning to use
        fastmode: Shaves off approximately 1ms by avoiding conversion to int
        """

        if not t:
            t = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        time.sleep(t)

        arr = np.random.random(self.dimensions)*256

        if fastmode:
            return arr
        else:
            return arr.astype(int)

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


def main_entry():
    import argparse
    from instamatic.formats import write_tiff
    # usage = """acquire"""

    description = """Program to acquire image data from gatan ORIUS ccd camera"""

    epilog = 'Updated: {}'.format(__version__)

    parser = argparse.ArgumentParser(  # usage=usage,
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        version=__version__)

    # parser.add_argument("args",
    #                     type=str, metavar="FILE",
    #                     help="Path to save cif")

    parser.add_argument("-b", "--binsize",
                        action="store", type=int, metavar="N", dest="binsize",
                        help="""Binsize to use. Must be one of 1, 2, or 4 (default 1)""")

    parser.add_argument("-e", "--exposure",
                        action="store", type=float, metavar="N", dest="exposure",
                        help="""Exposure time (default 0.5)""")

    parser.add_argument("-o", "--out",
                        action="store", type=str, metavar="image.png", dest="outfile",
                        help="""Where to store image""")

    parser.add_argument("-d", "--display",
                        action="store_true", dest="show_fig",
                        help="""Show the image (default True)""")

    # parser.add_argument("-t", "--tem",
    #                     action="store", type=str, dest="tem",
    #                     help="""Simulate microscope connection (default False)""")

    parser.add_argument("-u", "--simulate",
                        action="store_true", dest="simulate",
                        help="""Simulate camera/microscope connection (default False)""")
    
    parser.add_argument("-s", "--series",
                        action="store_true", dest="take_series",
                        help="""Enable mode to take a series of images (default False)""")
    
    parser.set_defaults(
        binsize=1,
        exposure=1,
        outfile=None,
        show_fig=False,
        test=False,
        simulate=False,
        camera="simulate",
        take_series=False
    )

    options = parser.parse_args()

    binsize = options.binsize
    exposure = options.exposure

    outfile = options.outfile
    show_fig = options.show_fig

    take_series = options.take_series

    from instamatic import TEMController
    ctrl = TEMController.initialize()
    
    if take_series:
        i = 1
        print("\nUsage:")
        print("    set b/e/i X -> set binsize/exposure/file number to X")
        print("    XXX         -> Add comment to header")
        print("    exit        -> exit the program")
    while take_series:
        outfile = "image_{:04d}".format(i)
        inp = raw_input("\nHit enter to take an image: \n >> [{}] ".format(outfile))
        if inp == "exit":
            break
        elif inp.startswith("set"):
            try:
                key, value = inp.split()[1:3]
            except ValueError:
                print("Input not understood")
                continue
            if key == "e":
                try:
                    value = float(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    exposure = value
            elif key == "b":
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value in (1,2,4):
                    binsize = value
            elif key == "i":
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    i = value
            print("binsize = {} | exposure = {} | file #{}".format(binsize, exposure, i))
        else:
            arr, h = ctrl.getImage(binsize=binsize, exposure=exposure, comment=inp)

            write_tiff(outfile, arr, header=h)
    
            i += 1
    else:
        import matplotlib.pyplot as plt

        arr, h = ctrl.getImage(binsize=binsize, exposure=exposure)

        if show_fig:
            save_header(sys.stdout, h)
            plt.imshow(arr, cmap="gray", interpolation="none")
            plt.show()
    
        if outfile:
            write_tiff(outfile, arr, header=h)
        else:
            write_tiff("out", arr, header=h)

    # cam.releaseConnection()


if __name__ == '__main__':
    # main_entry()
    cam = Camera(kind="timepix")
    arr = cam.getImage(t=0.1)
    print(arr)
    print(arr.shape)
