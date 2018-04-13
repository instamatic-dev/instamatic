#!/usr/bin/env python

import time
from instamatic.formats import write_tiff
import sys

from instamatic import config


def initialize(camera=None, **kwargs):
    """
    camera: callable or str
        Pass custom camera initializer (callable) + kwargs
        Pass None to use default camera (read from config)
        Pass 'disable' to disable camera interface
    """
    import __main__ as main                        # disable stream if in interactive session -> crashes Tkinter
    isInteractive = not hasattr(main, '__file__')  # https://stackoverflow.com/a/2356420

    from instamatic.camera import Camera
    from instamatic.camera.videostream import VideoStream

    microscope_id = config.cfg.microscope
    camera_id = config.cfg.camera
    print("Microscope:", microscope_id)
    print("Camera    :", camera_id)

    if microscope_id == "jeol":
        from .jeol_microscope import JeolMicroscope
        tem = JeolMicroscope()
    elif microscope_id == "fei_simu":
        from .fei_simu_microscope import FEISimuMicroscope
        tem = FEISimuMicroscope()
    elif microscope_id == "simulate":
        from .simu_microscope import SimuMicroscope
        tem = SimuMicroscope()
    else:
        raise ValueError("No such microscope: `{}`".format(microscope_id))

    if camera:
        # TODO: make sure that all use the same interface, i.e. `cam` or `kind`
        if camera == 'disable':
            cam = None
        elif not callable(camera):
            raise RuntimeError(f"Camera {camera} is not callable")
        else:
            cam = camera(cam=camera_id, **kwargs)
    elif isInteractive:
        cam = Camera(kind=camera_id)
    elif not isInteractive:
        cam = VideoStream(cam=camera_id)
    else:
        raise ValueError("No such microscope: `{}`".format(camera_id))

    ctrl = TEMController(tem, cam)
    return ctrl

class Deflector(object):
    """docstring for Deflector"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self.key = "def"

    def __repr__(self):
        x, y = self.get()
        return f"{self.name}(x={x}, y={y})"

    @property
    def name(self):
        return self.__class__.__name__

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

    @property
    def xy(self):
        return self.get()

    @xy.setter
    def xy(self, values):
        x, y = values
        self.set(x=x, y=y)

    def neutral(self):
        self._tem.setNeutral(self.key)


class Lens(object):
    """docstring for Lens"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self.key = "lens"
        
    def __repr__(self):
        try:
            value = self.value
        except ValueError:
            value="n/a"
        return f"{self.name}(value={value})"

    @property
    def name(self):
        return self.__class__.__name__

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


class DiffFocus(Lens):
    """docstring for DiffFocus"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getDiffFocus
        self._setter = self._tem.setDiffFocus     


class Brightness(Lens):
    """docstring for Brightness"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getBrightness
        self._setter = self._tem.setBrightness

    def max(self):
        self.set(self._tem.MAX)

    def min(self):
        self.set(self._tem.MIN)


class Magnification(Lens):
    """docstring for Magnification"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getMagnification
        self._setter = self._tem.setMagnification
        self._indexgetter = self._tem.getMagnificationIndex
        self._indexsetter = self._tem.setMagnificationIndex

    def __repr__(self):
        value = self.value
        index = self.index
        return "Magnification(value={}, index={})".format(value, index)

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
            print("Error: Cannot go to higher magnification (current={}).".format(self.value))

    def decrease(self):
        try:
            self.index -= 1
        except ValueError:
            print("Error: Cannot go to higher magnification (current={}).".format(self.value))


class GunShift(Deflector):
    """docstring for GunShift"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunShift
        self._getter = self._tem.getGunShift
        self.key = "GUN1"


class GunTilt(Deflector):
    """docstring for GunTilt"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunTilt
        self._getter = self._tem.getGunTilt
        self._tem = tem
        self.key = "GUN2"


class BeamShift(Deflector):
    """docstring for BeamShift"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamShift
        self._getter = self._tem.getBeamShift
        self.key = "CLA1"


class BeamTilt(Deflector):
    """docstring for BeamTilt"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamTilt
        self._getter = self._tem.getBeamTilt
        self.key = "CLA2"
        

class DiffShift(Deflector):
    """docstring for DiffShift"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setDiffShift
        self._getter = self._tem.getDiffShift
        self.key = "PLA"
        
 
class ImageShift1(Deflector):
    """docstring for ImageShift"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift1
        self._getter = self._tem.getImageShift1
        self.key = "IS1"

class ImageShift2(Deflector):
    """docstring for ImageShift"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift2
        self._getter = self._tem.getImageShift2
        self.key = "IS1"
   

class StagePosition(object):
    """docstring for StagePosition"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._setter = self._tem.setStagePosition
        self._getter = self._tem.getStagePosition
        self._setter_nw = self._tem.setStagePosition_nw
        self._stop_stagemv = self._tem.stopStageMV
        
    def __repr__(self):
        x, y, z, a, b = self.get()
        return f"{self.name}(x={x:.1f}, y={y:.1f}, z={z:.1f}, a={a:.1f}, b={b:.1f})"

    @property
    def name(self):
        return self.__class__.__name__

    def set(self, x=None, y=None, z=None, a=None, b=None):
        self._setter(x, y, z, a, b)
        
    def set_no_waiting(self, x=None, y=None, z=None, a=None, b=None, wait=False):
        self._setter_nw(x, y, z, a, b, wait)
        
    def stop_stagemovement(self):
        self._stop_stagemv()

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

    def neutral(self):
        self.set(x=0, y=0, z=0, a=0, b=0)

    def is_moving(self):
        return self._tem.isStageMoving()


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
        self.imageshift1 = ImageShift1(tem)
        self.imageshift2 = ImageShift2(tem)
        self.diffshift = DiffShift(tem)
        self.stageposition = StagePosition(tem)
        self.magnification = Magnification(tem)
        self.brightness = Brightness(tem)
        self.difffocus = DiffFocus(tem)

        self.autoblank = False
        self._saved_settings = {}
        self.store()
        print()
        print(self)

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

    def mode_samag(self):
        self.tem.setFunctionMode("samag")

    def mode_diffraction(self):
        self.tem.setFunctionMode("diff")

    @property
    def mode(self):
        """Should be one of 'mag1', 'mag2', 'lowmag', 'samag', 'diff'"""
        return self.tem.getFunctionMode()

    @mode.setter
    def mode(self, value):
        """Should be one of 'mag1', 'mag2', 'lowmag', 'samag', 'diff'"""
        self.tem.setFunctionMode(value)

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
                          str(self.imageshift1),
                          str(self.imageshift2),
                          str(self.diffshift),
                          str(self.stageposition),
                          str(self.magnification),
                          str(self.difffocus),
                          str(self.brightness),
                          "SpotSize({})".format(self.spotsize),
                          "Saved settings: {}".format(", ".join(self._saved_settings.keys()))))

    def to_dict(self, *keys):
        """
        Store microscope parameters to dict

        keys: tuple of str (optional)
            If any keys are specified, dict is returned with only the given properties
        
        self.to_dict('all') or self.to_dict() will return all properties
        """
        
        ## Each of these costs about 62 ms per call, stageposition is 265 ms per call
        funcs = { 
            'FunctionMode': self.tem.getFunctionMode,
            'GunShift': self.gunshift.get,
            'GunTilt': self.guntilt.get,
            'BeamShift': self.beamshift.get,
            'BeamTilt': self.beamtilt.get,
            'ImageShift1': self.imageshift1.get,
            'ImageShift2': self.imageshift2.get,
            'DiffShift': self.diffshift.get,
            # 'StagePosition': self.stageposition.get,
            'Magnification': self.magnification.get,
            'DiffFocus': self.difffocus.get,
            'Brightness': self.brightness.get,
            'SpotSize': self.tem.getSpotSize
        }

        dct = {}

        if "all" in keys or not keys:
            keys = funcs.keys()

        for key in keys:
            try:
                dct[key] = funcs[key]()
            except ValueError:
                pass

        return dct

    def from_dict(self, dct):
        """Restore microscope parameters from dict"""

        funcs = {
            # 'FunctionMode': self.tem.setFunctionMode,
            'GunShift': self.gunshift.set,
            'GunTilt': self.guntilt.set,
            'BeamShift': self.beamshift.set,
            'BeamTilt': self.beamtilt.set,
            'ImageShift1': self.imageshift1.set,
            'ImageShift2': self.imageshift2.set,
            'DiffShift': self.diffshift.set,
            'StagePosition': self.stageposition.set,
            'Magnification': self.magnification.set,
            'DiffFocus': self.difffocus.set,
            'Brightness': self.brightness.set,
            'SpotSize': self.tem.setSpotSize
        }

        mode = dct["FunctionMode"]
        self.tem.setFunctionMode(mode)

        for k, v in dct.items():
            if k in funcs:
                func = funcs[k]
            else:
                continue
            
            try:
                func(*v)
            except TypeError:
                func(v)

        # print self

    def getImage(self, exposure=0.5, binsize=1, comment="", out=None, plot=False, verbose=False, header_keys="all"):
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
            full_header: bool,
                return the full header

        Returns:
            image: np.ndarray, headerfile: dict
                a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes

        Usage:
            img, h = self.getImage()
        """

        if not self.cam:
            raise AttributeError("{} object has no attribute 'cam'".format(repr(self.__class__.__name__)))

        if not header_keys:
            h = {}
        else:
            h = self.to_dict(header_keys)

        if self.autoblank and self.beamblank:
            self.beamblank = False

        arr = self.cam.getImage(t=exposure, binsize=binsize)
        
        if self.autoblank:
            self.beamblank = True

        h["ImageGetTime"] = time.time()
        h["ImageExposureTime"] = exposure
        h["ImageBinSize"] = binsize
        h["ImageResolution"] = arr.shape
        h["ImageComment"] = comment
        h["ImageCameraName"] = self.cam.name
        h["ImageCameraDimensions"] = self.cam.dimensions

        if verbose:
            print("Image acquired - shape: {}, size: {:.0f} kB".format(arr.shape, arr.nbytes / 1024))

        if out:
            write_tiff(out, arr, header=h)

        if plot:
            import matplotlib.pyplot as plt
            plt.imshow(arr)
            plt.show()

        return arr, h

    def store(self, name="stash"):
        """Stores current settings to dictionary.
        Multiple settings can be stored under different names."""
        d = self.to_dict()
        d.pop("StagePosition", None)
        self._saved_settings[name] = d

    def restore(self, name="stash"):
        """Restsores settings from dictionary by the given name."""
        d = self._saved_settings[name]
        self.from_dict(d)
        print("Microscope alignment restored from '{}'".format(name))

    def close(self):
        try:
            self.cam.close()
        except AttributeError:
            pass

def main_entry():
    import argparse
    description = """Python program to control Jeol TEM"""

    parser = argparse.ArgumentParser(  # usage=usage,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

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

    from IPython import embed
    embed(banner1="\nAssuming direct control.\n")
    ctrl.close()


if __name__ == '__main__':
    from IPython import embed
    ctrl = initialize()
    
    embed(banner1="\nAssuming direct control.\n")
