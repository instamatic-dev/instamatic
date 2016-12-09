#!/usr/bin/env python

import matplotlib.pyplot as plt
from instamatic.camera import Camera
import time
from instamatic.formats import write_tiff

from IPython.terminal.embed import InteractiveShellEmbed
InteractiveShellEmbed.confirm_exit = False
ipshell = InteractiveShellEmbed(banner1='')

__version__ = "2016-09-15"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"


def initialize(camera="orius"):
    try:
        from jeol_microscope import JeolMicroscope
        tem = JeolMicroscope()
        cam = Camera(kind=camera)
    except WindowsError:
        from simu_microscope import SimuMicroscope
        print " >> Could not connect to JEOL, using simulated TEM/CAM instead"
        tem = SimuMicroscope()
        cam = Camera(kind="simulate")
    ctrl = TEMController(tem, cam)
    return ctrl


class DiffFocus(object):
    """docstring for DiffFocus"""
    def __init__(self, tem):
        super(DiffFocus, self).__init__()
        self._getter = tem.getDiffFocus
        self._setter = tem.setDiffFocus
        self._tem = tem

    def __repr__(self):
        value = self.value
        return "DiffFocus(value={})".format(value)

    def set(self, value):
        self._setter(value)

    def get(self):
        try:
            return self._getter()
        except ValueError:
            return -1

    @property
    def value(self):
            return self.get()

    @value.setter
    def value(self, value):
        self.set(value)


class Brightness(object):
    """docstring for Brightness"""
    def __init__(self, tem):
        super(Brightness, self).__init__()
        self._getter = tem.getBrightness
        self._setter = tem.setBrightness
        self._tem = tem

    def __repr__(self):
        value = self.value
        return "Brightness(value={})".format(value)

    def set(self, value):
        self._setter(value)

    def get(self):
        return self._getter()

    @property
    def value(self):
        return self.get()

    @value.setter
    def value(self, value):
        self.set(value)

    def max(self):
        self.set(self._tem.MAX)

    def min(self):
        self.set(self._tem.MIN)


class Magnification(object):
    """docstring for Magnification"""
    def __init__(self, tem):
        super(Magnification, self).__init__()
        self._getter = tem.getMagnification
        self._setter = tem.setMagnification
        self._indexgetter = tem.getMagnificationIndex
        self._indexsetter = tem.setMagnificationIndex

    def __repr__(self):
        value = self.value
        index = self.index
        return "Magnification(value={}, index={})".format(value, index)

    def set(self, value):
        self._setter(value)

    def get(self):
        return self._getter()

    @property
    def value(self):
        return self.get()

    @value.setter
    def value(self, value):
        self.set(value)

    @property
    def index(self):
        return self._indexgetter()

    @index.setter
    def index(self, index):
        self._indexsetter(index)

    def increase(self):
        try:
            self.index += 1
        except ValueError:
            print "Error: Cannot go to higher magnification (current={}).".format(self.value)

    def decrease(self):
        try:
            self.index -= 1
        except ValueError:
            print "Error: Cannot go to higher magnification (current={}).".format(self.value)


class GunShift(object):
    """docstring for GunShift"""
    def __init__(self, tem):
        super(GunShift, self).__init__()
        self._setter = tem.setGunShift
        self._getter = tem.getGunShift
        self._tem = tem
        self.name = "GUN1"

    def __repr__(self):
        x, y = self.get()
        return "GunShift(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)


class GunTilt(object):
    """docstring for GunTilt"""
    def __init__(self, tem):
        super(GunTilt, self).__init__()
        self._setter = tem.setGunTilt
        self._getter = tem.getGunTilt
        self._tem = tem
        self.name = "GUN2"

    def __repr__(self):
        x, y = self.get()
        return "GunTilt(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)    


class BeamShift(object):
    """docstring for BeamShift"""
    def __init__(self, tem):
        super(BeamShift, self).__init__()
        self._setter = tem.setBeamShift
        self._getter = tem.getBeamShift
        self._tem = tem
        self.name = "CLA1"

    def __repr__(self):
        x, y = self.get()
        return "BeamShift(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)


class BeamTilt(object):
    """docstring for BeamTilt"""
    def __init__(self, tem):
        super(BeamTilt, self).__init__()
        self._setter = tem.setBeamTilt
        self._getter = tem.getBeamTilt
        self._tem = tem
        self.name = "CLA2"
        
    def __repr__(self):
        x, y = self.get()
        return "BeamTilt(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)


class DiffShift(object):
    """docstring for DiffShift"""
    def __init__(self, tem):
        super(DiffShift, self).__init__()
        self._setter = tem.setDiffShift
        self._getter = tem.getDiffShift
        self._tem = tem
        self.name = "PLA"
        
    def __repr__(self):
        x, y = self.get()
        return "DiffShift(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)


class ImageShift(object):
    """docstring for ImageShift"""
    def __init__(self, tem):
        super(ImageShift, self).__init__()
        self._setter = tem.setImageShift
        self._getter = tem.getImageShift
        self._tem = tem
        self.name = "IS1"
        
    def __repr__(self):
        x, y = self.get()
        return "ImageShift(x={}, y={})".format(x, y)

    def set(self, x, y):
        self._setter(x, y)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(value, self.y)

    @property
    def y(self):
        x, y = self.get()
        return y

    @y.setter
    def y(self, value):
        self.set(self.x, value)

    def neutral(self):
        self._tem.setNeutral(self.name)


class StagePosition(object):
    """docstring for StagePosition"""
    def __init__(self, tem):
        super(StagePosition, self).__init__()
        self._setter = tem.setStagePosition
        self._getter = tem.getStagePosition
        self._reset = tem.forceStageBacklashCorrection
        self._tem = tem
        
    def __repr__(self):
        x, y, z, a, b = self.get()
        return "StagePosition(x={:.1f}, y={:.1f}, z={:.1f}, a={:.1f}, b={:.1f})".format(x,y,z,a,b)

    def set(self, x=None, y=None, z=None, a=None, b=None):
        self._setter(x, y, z, a, b)

    def get(self):
        return self._getter()

    @property
    def x(self):
        x, y, z, a, b = self.get()
        return x

    @x.setter
    def x(self, value):
        self.set(x=value)

    @property
    def y(self):
        x, y, z, a, b = self.get()
        return y

    @property
    def xy(self):
        x, y, z, a, b = self.get()
        return x, y

    @xy.setter
    def xy(self, values):
        x, y = values
        self.set(x=x, y=y)

    @y.setter
    def y(self, value):
        self.set(y=value)

    @property
    def z(self):
        x, y, z, a, b = self.get()
        return z

    @z.setter
    def z(self, value):
        self.set(z=value)

    @property
    def a(self):
        x, y, z, a, b = self.get()
        return a

    @a.setter
    def a(self, value):
        self.set(a=value)

    @property
    def b(self):
        x, y, z, a, b = self.get()
        return b

    @b.setter
    def b(self, value):
        self.set(b=value)

    def reset_xy(self):
        self._reset(x=True, y=True)

    def neutral(self):
        self.set(x=0, y=0, z=0, a=0, b=0)

    def rotate_to(self, target, start=None, speed=5, delay=0.01, wait_for_stage=False):
        """
        Control rotation of the microscope

        target: float
            final angle in degrees
        start: float
            starting angle in degrees (optional)
        speed: float
            overall rate of rotation in degrees / second
        delay: float
            delay in seconds between updates sent to the microscope (accurate to 10 - 13 milliseconds)
        """
        if not start:
            start = self.a
        else:
            self.a = start
        speed = abs(speed)

        # m equals -1 for positive direction, 1 for negative direction
        m = cmp(start, target)
        
        angle = start
        
        t0 = time.time()
        while cmp(angle, target) == m:
            t1 = time.time()
            angle = start - m * (t1 - t0) * speed
            ctrl.tem.stage3.SetTiltAngle(angle)
            time.sleep(delay)
            while wait_for_stage and self._tem.stage3.GetStatus()[3]:  # is stage moving?
                pass
            # print t1-t0, angle


class TEMController(object):
    """docstring for TEMController

    descriptors:
    https://docs.python.org/2/howto/descriptor.html
    """

    def __init__(self, tem, cam=None):
        super(TEMController, self).__init__()
        self.tem = tem
        self.cam = cam

        self.gunshift = GunShift(tem)
        self.guntilt = GunTilt(tem)
        self.beamshift = BeamShift(tem)
        self.beamtilt = BeamTilt(tem)
        self.imageshift = ImageShift(tem)
        self.diffshift = DiffShift(tem)
        self.stageposition = StagePosition(tem)
        self.magnification = Magnification(tem)
        self.brightness = Brightness(tem)
        self.difffocus = DiffFocus(tem)

        self.autoblank = False
        self._saved_settings = {}
        self.store()
        print
        print self

    @property
    def spotsize(self):
        return self.tem.getSpotSize()

    @spotsize.setter
    def spotsize(self, value):
        self.tem.setSpotSize(value)

    def mode_lowmag(self):
        self.tem.setFunctionMode("lowmag")

    def mode_mag1(self):
        self.tem.setFunctionMode("mag1")

    def mode_diffraction(self):
        self.tem.setFunctionMode("diff")

    @property
    def mode(self):
        return self.tem.getFunctionMode()

    @property
    def beamblank(self):
        return self.tem.isBeamBlanked()

    @beamblank.setter
    def beamblank(self, on):
        self.tem.setBeamBlank(on)

    def __repr__(self):
        return "\n".join(("Mode: {}".format(self.tem.getFunctionMode()),
                          str(self.gunshift),
                          str(self.guntilt),
                          str(self.beamshift),
                          str(self.beamtilt),
                          str(self.imageshift),
                          str(self.diffshift),
                          str(self.stageposition),
                          str(self.magnification),
                          str(self.difffocus),
                          str(self.brightness),
                          "SpotSize({})".format(self.spotsize),
                          "Saved settings: {}".format(", ".join(self._saved_settings.keys()))))

    def to_dict(self):
        d = {
            'FunctionMode': self.tem.getFunctionMode(),
            'GunShift': self.gunshift.get(),
            'GunTilt': self.guntilt.get(),
            'BeamShift': self.beamshift.get(),
            'BeamTilt': self.beamtilt.get(),
            'ImageShift': self.imageshift.get(),
            'DiffShift': self.diffshift.get(),
            'StagePosition': self.stageposition.get(),
            'Magnification': self.magnification.get(),
            'DiffFocus': self.difffocus.get(),
            'Brightness': self.brightness.get(),
            'SpotSize': self.tem.getSpotSize()
        }
        return d

    def from_dict(self, d):
        funcs = {
            'FunctionMode': self.tem.setFunctionMode,
            'GunShift': self.gunshift.set,
            'GunTilt': self.guntilt.set,
            'BeamShift': self.beamshift.set,
            'BeamTilt': self.beamtilt.set,
            'ImageShift': self.imageshift.set,
            'DiffShift': self.diffshift.set,
            'StagePosition': self.stageposition.set,
            'Magnification': self.magnification.set,
            'DiffFocus': self.difffocus.set,
            'Brightness': self.brightness.set,
            'SpotSize': self.tem.setSpotSize
        }

        mode = d.pop("FunctionMode")
        self.tem.setFunctionMode(mode)

        for k, v in d.items():
            if k in funcs:
                func = funcs[k]
            else:
                continue
            
            try:
                func(*v)
            except TypeError:
                func(v)

        print self

    def getImage(self, exposure=0.5, binsize=1, comment="", out=None, plot=False):
        """Retrieve image as numpy array from camera

        Parameters:
            exposure: float, 
                exposure time in seconds
            binsize: int, 
                which binning to use for the image, must be 1, 2, or 4
            comment: str, 
                arbitrary comment to add to the header file under 'ImageComment'
            out: str, 
                path or filename to which the image/header is saved (defaults to tiff)
            plot: bool, 
                toggle whether to show the image using matplotlib after acquisition

        Returns:
            image: np.ndarray, headerfile: dict
                a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes

        Usage:
            img, h = self.getImage()
        """

        if not self.cam:
            raise AttributeError("{} object has no attribute 'cam'".format(repr(self.__class__.__name__)))

        h = self.to_dict()

        if self.autoblank and self.beamblank:
            self.beamblank = False

        arr = self.cam.getImage(t=exposure, binsize=binsize)
        h["ImageExposureTime"] = exposure
        h["ImageBinSize"] = binsize
        h["ImageResolution"] = arr.shape
        h["ImageComment"] = comment
        h["ImageCamera"] = self.cam.name
        h["Time"] = time.ctime()

        if self.autoblank:
            self.beamblank = True

        if out:
            write_tiff(out, arr, header=h)

        if plot:
            plt.imshow(arr)
            plt.show()

        return arr, h

    def store(self, name="stash"):
        """Stores current settings to dictionary.
        Multiple settings can be stored under different names."""
        d = self.to_dict()
        del d["StagePosition"]
        self._saved_settings[name] = d

    def restore(self, name="stash"):
        """Restsores settings from dictionary by the given name."""
        d = self._saved_settings[name]
        self.from_dict(d)
        print "Restored from '{}'".format(name)


def main_entry():
    import argparse
    description = """Python program to control Jeol TEM"""

    epilog = 'Updated: {}'.format(__version__)

    parser = argparse.ArgumentParser(  # usage=usage,
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        version=__version__)

    # parser.add_argument("args",
    #                     type=str, metavar="FILE",
    #                     help="Path to save cif")

    parser.add_argument("-u", "--simulate",
                        action="store_true", dest="simulate",
                        help="""Simulate microscope connection (default False)""")
    
    parser.set_defaults(
        simulate=False,
        tem="simtem",
    )

    options = parser.parse_args()
    ctrl = initialize()

    ipshell()


if __name__ == '__main__':
    ctrl = initialize()
    ipshell()
