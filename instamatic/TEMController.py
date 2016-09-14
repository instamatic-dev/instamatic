#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
from camera.camera import gatanOrius, save_image_and_header
import time

from IPython.terminal.embed import InteractiveShellEmbed
InteractiveShellEmbed.confirm_exit = False
ipshell = InteractiveShellEmbed(banner1='')

__version__ = "2016-06-29"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"


def initialize():
    try:
        from instamatic.pyscope import jeolcom
        tem = jeolcom.Jeol()
        cam = gatanOrius()
    except WindowsError:
        from instamatic.pyscope import simtem
        print " >> Could not connect to JEOL, using SimTEM instead..."
        tem = simtem.SimTEM()
        cam = gatanOrius(simulate=True)
    ctrl = TEMController(tem, cam)
    return ctrl


class TEMValue(object):
    """docstring for TEMValue"""

    def __init__(self, var, getter, setter):
        super(TEMValue, self).__init__()
        self._getter = getter
        self._setter = setter
        self._var = var

    def __repr__(self):
        return str(self.__get__())

    def __get__(self, obj, objtype):
        d = self._getter()
        try:
            val = d[self._var]
        except KeyError:
            print " >> Error: Cannot retrieve value for", repr(self._var)
            val = np.NaN
        return val

    def __set__(self, obj, val):
        vector = {self._var: val}
        self._setter(vector)


class Magnification(object):
    """docstring for Magnification"""
    def __init__(self, tem):
        super(Magnification, self).__init__()
        self._tem = tem

        if not tem.getMagnificationsInitialized():
            answer = raw_input(" >> Magnification index not initialized, run initialization routine? \n [YES/no] >> ") or "y"
            if "y" in answer:
                tem.findMagnifications()
                print "done..."
            print "tem.magnifications"
            print tem.magnifications
            print "tem.submode_mags"
            print tem.submode_mags
            print "tem.projection_submode_map"
            print tem.projection_submode_map

    def __repr__(self):
        value = self.value
        index = self.index
        return "Magnification(value={}, index={})".format(value, index)

    @property
    def value(self):
        try:
            mag = self._tem.getMagnification()
        except ValueError:    
            mag = 0
        finally:
            return mag

    @value.setter
    def value(self, val):
        self._tem.setMagnification(val)

    @property
    def index(self):
        try:
            ind = self._tem.getMagnificationIndex()
        except ValueError:
            ind = 0
        finally:
            return ind

    @index.setter
    def index(self, val):
        self._tem.setMagnificationIndex(val)

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

# TODO
## Spotsize
## ScreenCurrent
## Intensity
## Defocus
class TEMController(object):
    """docstring for TEMController

    descriptors:
    https://docs.python.org/2/howto/descriptor.html
    """

    def __init__(self, tem, cam=None):
        super(TEMController, self).__init__()
        self.tem = tem
        self.cam = cam

        class GunShift(object):
            x = TEMValue("x", tem.getGunShift, tem.setGunShift)
            y = TEMValue("y", tem.getGunShift, tem.setGunShift)

            def __repr__(self):
                d = tem.getGunShift()
                return "GunShift(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setGunShift(kwargs)

        class GunTilt(object):
            x = TEMValue("x", tem.getGunTilt, tem.setGunTilt)
            y = TEMValue("y", tem.getGunTilt, tem.setGunTilt)

            def __repr__(self):
                d = tem.getGunTilt()
                return "GunTilt(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setGunTilt(kwargs)

        class BeamShift(object):
            x = TEMValue("x", tem.getBeamShift, tem.setBeamShift)
            y = TEMValue("y", tem.getBeamShift, tem.setBeamShift)

            def __repr__(self):
                d = tem.getBeamShift()
                return "BeamShift(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setBeamShift(kwargs)

        class BeamTilt(object):
            x = TEMValue("x", tem.getBeamTilt, tem.setBeamTilt)
            y = TEMValue("y", tem.getBeamTilt, tem.setBeamTilt)

            def __repr__(self):
                d = tem.getBeamTilt()
                return "BeamTilt(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setBeamTilt(kwargs)

        class ImageShift(object):
            x = TEMValue("x", tem.getImageShift, tem.setImageShift)
            y = TEMValue("y", tem.getImageShift, tem.setImageShift)

            def __repr__(self):
                d = tem.getGunTilt()
                return "ImageShift(x={x}, y={y})".format(**d)
            
            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)

        class StagePosition(object):
            x = TEMValue("x", tem.getStagePosition, tem.setStagePosition)
            y = TEMValue("y", tem.getStagePosition, tem.setStagePosition)
            z = TEMValue("z", tem.getStagePosition, tem.setStagePosition)
            a = TEMValue("a", tem.getStagePosition, tem.setStagePosition)
            b = TEMValue("b", tem.getStagePosition, tem.setStagePosition)

            def __repr__(self):
                d = tem.getStagePosition()
                if "b" not in d:
                    d["b"] = np.NaN
                return "StagePosition(x={x:.3e}, y={y:.3e}, z={z}, a={a}, b={b})".format(**d)

            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)


        self.gunshift = GunShift()
        self.guntilt = GunTilt()
        self.beamshift = BeamShift()
        self.beamtilt = BeamTilt()
        self.imageshift = ImageShift()
        self.stageposition = StagePosition()
        self.magnification = Magnification(tem)

        self.setDiffractionmode = self.tem.setDiffractionMode
        self.getDiffractionmode = self.tem.getDiffractionMode

        print self

    def __repr__(self):
        return "\n".join(("Mode: {}".format(self.getDiffractionmode()),
                          str(self.gunshift),
                          str(self.guntilt),
                          str(self.beamshift),
                          str(self.beamtilt),
                          str(self.imageshift),
                          str(self.stageposition),
                          str(self.magnification),
                        "Intensity: {}".format(self.tem.getIntensity())))

    def activate_nanobeam(self):
        raise NotImplementedError

    def deactivate_nanobeam(self):
        raise NotImplementedError

    def get_all(self):
        d = {
            'BeamShift': self.tem.getBeamShift(),
            'BeamTilt': self.tem.getBeamTilt(),
            'GunShift': self.tem.getGunShift(),
            'GunTilt': self.tem.getGunTilt(),
            'ImageShift': self.tem.getImageShift(),
            'StagePosition': self.tem.getStagePosition(),
            'Magnification': self.magnification.value,
            'DiffractionMode': self.getDiffractionmode(),
            'Intensity': self.tem.getIntensity()
        }
        return d

    def set_all(self, d):
        funcs = {
            'BeamShift': self.tem.setBeamShift,
            'BeamTilt': self.tem.setBeamTilt,
            'GunShift': self.tem.setGunShift,
            'GunTilt': self.tem.setGunTilt,
            'ImageShift': self.tem.setImageShift,
            'StagePosition': self.tem.setStagePosition,
            'Magnification': self.tem.setMagnification,
            'DiffractionMode': self.tem.setDiffractionMode
        }

        for k, v in d.items():
            func = funcs[k]
            func(v)

        print self

    def getImage(self, exposure=0.5, binsize=1, comment="", out=None, plot=False):
        if not self.cam:
            raise AttributeError("{} object has no attribute 'cam'".format(repr(self.__class__.__name__)))

        h = self.get_all()

        arr = self.cam.getImage(t=exposure, binsize=binsize)
        h["ImageExposureTime"] = exposure
        h["ImageBinSize"] = binsize
        h["ImageResolution"] = arr.shape
        h["ImageComment"] = comment
        h["Time"] = time.ctime()

        if out:
            save_image_and_header(out, img=arr, header=h)

        if plot:
            plt.imshow(arr)
            plt.show()

        return arr, h


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

    if options.simulate:
        from instamatic.pyscope import simtem
        tem = simtem.SimTEM()
        cam = gatanOrius(simulate=True)
    else:
        from instamatic.pyscope import jeolcom
        tem = jeolcom.Jeol()
        cam = gatanOrius(simulate=False)
    

    ctrl = TEMController(tem, cam=cam)

    ipshell()


if __name__ == '__main__':
    from instamatic.pyscope import simtem
    tem = simtem.SimTEM()
    ctrl = TEMController(tem)
    ipshell()
