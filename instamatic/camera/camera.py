import ctypes
from ctypes import c_int, c_long, c_float, c_double, c_bool, c_wchar_p
from ctypes import POINTER, create_unicode_buffer, byref, addressof

import comtypes
# initial COM in multithread mode if not initialized otherwise
try:
    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
except WindowsError:
    comtypes.CoInitialize()

try:
    import fabio
except IOError:
    pass

import numpy as np
import os, sys

import atexit

__version__ = "2016-05-19"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"

__all__ = ["gatanOrius"]

DLLPATH_SIMU = "CCDCOM2_x64_simulation.dll"
DLLPATH      = "CCDCOM2.dll"


@atexit.register
def exit_func():
    """Uninitialize comtypes to prevent the program from hanging"""
    comtypes.CoUninitialize()
    print "Uninitialize com connection to camera"


class gatanOrius(object):
    """docstring for gatanOrius"""

    def __init__(self, simulate=False):
        super(gatanOrius, self).__init__()

        if simulate:
            libpath = os.path.join(os.path.dirname(
                __file__), DLLPATH_SIMU)
        else:
            libpath = os.path.join(os.path.dirname(
                __file__), DLLPATH)

        try:
            lib = ctypes.cdll.LoadLibrary(libpath)
        except WindowsError as e:
            print e
            print "Missing DLL:", DLLPATH
            exit()

        ## not used
        # self._acquireImage = getattr(lib, '?acquireImage@@YAHPEAFHHHN_N@Z') # not used
        # self._acquireImageNew = getattr(lib, '?acquireImageNew@@YAHHHHHPEAFPEAH1HN_N@Z') # not used
        # self._acquireImageNewInt = getattr(lib, '?acquireImageNewInt@@YAHHHHHPEAH00HN_N@Z') # not used
        # self._execScript = getattr(lib, '?execScript@@YAHPEB_W@Z') # not used

        self._acquireImageNewFloat = getattr(
            lib, '?acquireImageNewFloat@@YAHHHHHHN_NPEAPEAMPEAH2@Z')
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

        self._isCameraInfoAvailable = getattr(
            lib, '?isCameraInfoAvailable@@YA_NXZ')
        self._isCameraInfoAvailable.restype = c_bool

        self._releaseCCDCOM = getattr(lib, '?releaseCCDCOM@@YAXXZ')

        self.establishConnection()

        print "Camera {} initialized".format(self.getName())
        print "Dimensions {}x{}".format(*self.getDimensions())
        print "Info {} | Count {}".format(self.isCameraInfoAvailable(), self.getCameraCount())

        atexit.register(self.releaseConnection)


    def getImage(self, t=0.5, binsize=1, xmin=0, xmax=2048, ymin=0, ymax=2048, showindm=False):
        """Image acquisition routine

        t: exposure time in seconds
        binsize: which binning to use
        showindm: show image in digital micrograph
        xmin, xmax, ymin, ymax: retrieve image with smaller size from a subset of pixels
        """
        bins = (1, 2, 4)
        if binsize not in bins:
            raise ValueError(
                "Cannot use binsize={}..., should be one of {}".format(binsize, bins))

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

        print "Image acquired - shape: {}x{}, size: {} kB".format(xres, yres, arr.nbytes / 1024)

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
            raise RuntimeError("Could not establish camera connection...")

    def releaseConnection(self):
        name = self.getName()
        self._releaseCCDCOM()
        print "Connection to camera {} released".format(name) 


def save_image(outfile, img):
    if not outfile:
        return
    root, ext = os.path.splitext(outfile)
    if ext.lower() == ".npy":
        np.save(outfile, img)
    else:
        plt.imsave(outfile, img, cmap="gray")
    # print " >> Image written to {}".format(outfile) 


def save_header(outfile, header):
    import json
    if not outfile:
        return
    if isinstance(outfile, str):
        root, ext = os.path.splitext(outfile)
        outfile = open(root+".json", "w")
    json.dump(header, outfile, indent=2)
    if outfile.name == "<stdout>":
        print
    # else:
        # print " >> Header written to {}".format(outfile.name) 


def save_image_and_header(outfile, img=None, header=None):
    root, ext = os.path.splitext(outfile)
    ext = ext.lower()
    if ext == "":
        ext = ".edf"
        outfile = root + ext
    if ext == ".cbf":
        im = fabio.cbfimage.cbfimage(data=img, header=header)
        im.write(outfile)
    elif ext == ".edf":
        im = fabio.edfimage.edfimage(data=img, header=header)
        im.write(outfile)
    # elif ext == ".dm3":
    #     im = fabio.dm3image.dm3image(data=img, header=header)
    #     im.write(outfile)
    elif ext == ".tif" or ext == ".tiff":
        im = fabio.tifimage.tifimage(data=img, header=header)
        im.write(outfile)
    # elif ext == ".xml" or ext == "xsd":
    #     im = fabio.xsdimage.xsdimage(data=img, header=header)
    #     im.write(outfile)
    # elif ext == ".npy":
    #     im = fabio.numpyimage.numpyimage(data=img, header=header)
    #     im.write(outfile)
    elif ext == ".npy":
        if img is not None:
            save_image(outfile, img)
        if header:
            save_header(outfile, header)
    else:
        raise IOError("Extension {} not understood (edf cbf tif npy)".format(ext))
    print " >> Image written to {}".format(outfile)
    return outfile

def main_entry():
    import argparse
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
        tem="simtem",
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
        print "\nUsage:"
        print "    set b/e/i X -> set binsize/exposure/file number to X"
        print "    XXX         -> Add comment to header"
        print "    exit        -> exit the program"
    while take_series:
        outfile = "image_{:04d}".format(i)
        inp = raw_input("\nHit enter to take an image: \n >> [{}] ".format(outfile))
        if inp == "exit":
            break
        elif inp.startswith("set"):
            try:
                key, value = inp.split()[1:3]
            except ValueError:
                print "Input not understood"
                continue
            if key == "e":
                try:
                    value = float(value)
                except ValueError as e:
                    print e
                if value > 0:
                    exposure = value
            elif key == "b":
                try:
                    value = int(value)
                except ValueError as e:
                    print e
                if value in (1,2,4):
                    binsize = value
            elif key == "i":
                try:
                    value = int(value)
                except ValueError as e:
                    print e
                if value > 0:
                    i = value
            print "binsize = {} | exposure = {} | file #{}".format(binsize, exposure, i)
        else:
            arr, h = ctrl.getImage(binsize=binsize, exposure=exposure, comment=inp)

            save_image_and_header(outfile, img=arr, header=h)
    
            i += 1
    else:
        import matplotlib.pyplot as plt

        arr, h = ctrl.getImage(binsize=binsize, exposure=exposure)

        if show_fig:
            save_header(sys.stdout, h)
            plt.imshow(arr, cmap="gray", interpolation="none")
            plt.show()
    
        if outfile:
            save_image_and_header(outfile, img=arr, header=h)
        else:
            save_image_and_header("out", img=arr, header=h)

    # cam.releaseConnection()


if __name__ == '__main__':
    main_entry()
