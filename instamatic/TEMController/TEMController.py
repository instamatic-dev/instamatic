#!/usr/bin/env python

import time
from instamatic.formats import write_tiff

from instamatic import config
from instamatic.camera import Camera
from .microscope import Microscope

from typing import Tuple
from contextlib import contextmanager
from collections import namedtuple
import numpy as np


_ctrl = None  # store reference of ctrl so it can be accessed without re-initializing

default_cam = config.camera.name
default_tem = config.microscope.name

use_tem_server = config.cfg.use_tem_server
use_cam_server = config.cfg.use_cam_server


class TEMControllerException(Exception):
    pass


def initialize(tem_name: str=default_tem, cam_name: str=default_cam, stream: bool=True) -> "TEMController":
    """Initialize TEMController object giving access to the TEM and Camera interfaces

    tem_name: Name of the TEM to use
    cam_name: Name of the camera to use, can be set to 'None' to skip camera initialization
    stream: Open the camera as a stream (this enables `TEMController.show_stream()`)
    """

    print(f"Microscope: {tem_name}{' (server)' if use_tem_server else ''}")
    tem = Microscope(tem_name, use_server=use_tem_server)
    
    if cam_name:
        if use_cam_server:
            cam_tag = ' (server)'
        elif stream:
            cam_tag = ' (stream)'
        else:
            cam_tag = ''

        print(f"Camera    : {cam_name}{cam_tag}")

        cam = Camera(cam_name, as_stream=stream, use_server=use_cam_server)
    else:
        cam = None

    global _ctrl
    ctrl = _ctrl = TEMController(tem=tem, cam=cam)

    return ctrl


def get_instance() -> "TEMController":
    """Gets the current `ctrl` instance if it has been initialized, otherwise
    initialize it using default parameters"""

    global _ctrl
    
    if _ctrl:
        ctrl = _ctrl
    else:
        ctrl = _ctrl = initialize()

    return ctrl


# namedtuples to store results from .get()
StagePositionTuple = namedtuple("StagePositionTuple", ["x", "y", "z", "a", "b"])
DeflectorTuple = namedtuple("DeflectorTuple", ["x", "y"])


class Deflector(object):
    """Generic microscope deflector object defined by X/Y values
    Must be subclassed to set the self._getter, self._setter functions"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._getter = None
        self._setter = None
        self.key = "def"

    def __repr__(self):
        x, y = self.get()
        return f"{self.name}(x={x}, y={y})"

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set(self, x: int, y: int):
        self._setter(x, y)

    def get(self) -> Tuple[int, int]:
        return DeflectorTuple(*self._getter())

    @property
    def x(self) -> int:
        x, y = self.get()
        return x

    @x.setter
    def x(self, value: int):
        self.set(value, self.y)

    @property
    def y(self) -> int:
        x, y = self.get()
        return y

    @y.setter
    def y(self, value: int):
        self.set(self.x, value)

    @property
    def xy(self) -> Tuple[int, int]:
        return self.get()

    @xy.setter
    def xy(self, values: Tuple[int, int]):
        x, y = values
        self.set(x=x, y=y)

    def neutral(self):
        self._tem.setNeutral(self.key)


class Lens(object):
    """Generic microscope lens object defined by one value
    Must be subclassed to set the self._getter, self._setter functions"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._getter = None
        self._setter = None
        self.key = "lens"
        
    def __repr__(self):
        try:
            value = self.value
        except ValueError:
            value="n/a"
        return f"{self.name}(value={value})"

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set(self, value: int):
        self._setter(value)

    def get(self) -> int:
        return self._getter()

    @property
    def value(self) -> int:
        return self.get()

    @value.setter
    def value(self, value: int):
        self.set(value)


class DiffFocus(Lens):
    """Control the Difffraction focus lens (IL1)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getDiffFocus
        self._setter = self._tem.setDiffFocus
        self.is_defocused = False

    def set(self, value: int, confirm_mode: bool=True):
        """
        confirm_mode: verify that TEM is set to the correct mode ('diff').
        IL1 maps to different values in image and diffraction mode. 
        Turning it off results in a 2x speed-up in the call, but it will silently fail if the TEM is in the wrong mode.
        """
        self._setter(value, confirm_mode=confirm_mode)

    def defocus(self, offset):
        """Apply a defocus to the IL1 lens, use `.refocus` to restore the previous setting"""
        if self.is_defocused:
            raise TEMControllerException(f"{self.__class__.__name__} is already defocused!")

        try:
            self._focused_value = current = self.get()
        except ValueError:
            self._tem.setFunctionMode("diff")
            self._focused_value = current = self.get()

        target = current + offset
        self.set(target)
        self.is_defocused = True
        print(f"Defocusing from {current} to {target}")

    def refocus(self):
        """Restore the IL1 lens to the focused condition a defocus has been applied using `.defocus`"""
        if self.is_defocused:
            target = self._focused_value
            self.set(target)
            self.is_defocused = False
            print(f"Refocusing to {target}")


class Brightness(Lens):
    """Control object for the Brightness (CL3)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getBrightness
        self._setter = self._tem.setBrightness

    def max(self):
        self.set(65535)

    def min(self):
        self.set(0)


class Magnification(Lens):
    """
    Magnification control. The magnification can be set directly, or
    by passing the corresponding index
    """
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getMagnification
        self._setter = self._tem.setMagnification
        self._indexgetter = self._tem.getMagnificationIndex
        self._indexsetter = self._tem.setMagnificationIndex

    def __repr__(self):
        value = self.value
        index = self.index
        return f"Magnification(value={value}, index={index})"

    @property
    def index(self) -> int:
        return self._indexgetter()

    @index.setter
    def index(self, index: int):
        self._indexsetter(index)

    def increase(self) -> None:
        try:
            self.index += 1
        except ValueError:
            print(f"Error: Cannot change magnficication index (current={self.value}).")

    def decrease(self) -> None:
        try:
            self.index -= 1
        except ValueError:
            print(f"Error: Cannot change magnficication index (current={self.value}).")

    def get_ranges(self) -> dict:
        """Runs through all modes and fetches all the magnification settings possible on the microscope"""
        return self._tem.getMagnificationRanges()


class GunShift(Deflector):
    """GunShift control"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunShift
        self._getter = self._tem.getGunShift
        self.key = "GUN1"


class GunTilt(Deflector):
    """GunTilt control"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunTilt
        self._getter = self._tem.getGunTilt
        self._tem = tem
        self.key = "GUN2"


class BeamShift(Deflector):
    """BeamShift control (CLA1)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamShift
        self._getter = self._tem.getBeamShift
        self.key = "CLA1"


class BeamTilt(Deflector):
    """BeamTilt control (CLA2)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamTilt
        self._getter = self._tem.getBeamTilt
        self.key = "CLA2"
        

class DiffShift(Deflector):
    """Control for the Diffraction Shift (PLA)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setDiffShift
        self._getter = self._tem.getDiffShift
        self.key = "PLA"
        
 
class ImageShift1(Deflector):
    """ImageShift control (IS1)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift1
        self._getter = self._tem.getImageShift1
        self.key = "IS1"


class ImageShift2(Deflector):
    """ImageShift control (IS2)"""
    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift2
        self._getter = self._tem.getImageShift2
        self.key = "IS2"


class Stage(object):
    """Stage control"""
    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._setter = self._tem.setStagePosition
        self._getter = self._tem.getStagePosition
        self._wait = True  # properties only
        
    def __repr__(self):
        x, y, z, a, b = self.get()
        return f"{self.name}(x={x:.1f}, y={y:.1f}, z={z:.1f}, a={a:.1f}, b={b:.1f})"

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set(self, x: int=None, y: int=None, z: int=None, a: int=None, b: int=None, wait: bool=True) -> None:
        """wait: bool, block until stage movement is complete (JEOL only)"""
        self._setter(x, y, z, a, b, wait=wait)
        
    def set_with_speed(self, x: int=None, y: int=None, z: int=None, a: int=None, b: int=None, wait: bool=True, speed: float=1.0) -> None:
        """
        speed: float, set stage rotation with specified speed (FEI only)
        """
        self._setter(x, y, z, a, b, wait=wait, speed=speed)

    def set_rotation_speed(self, speed=1) -> None:
        """Sets the stage (rotation) movement speed on the TEM"""
        self._tem.setRotationSpeed(value=speed)

    def set_a_with_speed(self, a: float, speed: int, wait: bool=False):
        """Rotate to angle `a` with speed (JEOL only).
        wait: bool, block until stage movement is complete.
        """
        with self.rotating_speed(speed):
            self.set(a=a, wait=False)
        # Do not wait on `set` to return to normal rotation speed quickly
        if wait:
            self.wait_for_stage()

    @contextmanager
    def rotating_speed(self, speed: int):
        """
        Context manager that sets the rotation speed for the duration of the `with` statement.

        Usage:
            with ctrl.stage.rotating_speed():
                ctrl.stage.a = 40.0
        """
        current_speed = self._tem.getRotationSpeed()
        if current_speed != speed:
            self.set_rotation_speed(speed)
            yield
            self.set_rotation_speed(current_speed)
        else:
            yield

    def get(self) -> Tuple[int, int, int, int, int]:
        """Get stage positions; x, y, z, and status of the rotation axes; a, b"""
        return StagePositionTuple(*self._getter())

    @property
    def x(self) -> int:
        x, y, z, a, b = self.get()
        return x

    @x.setter
    def x(self, value: int):
        self.set(x=value, wait=self._wait)

    @property
    def y(self) -> int:
        x, y, z, a, b = self.get()
        return y

    @y.setter
    def y(self, value: int):
        self.set(y=value, wait=self._wait)
    
    @property
    def xy(self) -> Tuple[int, int]:
        x, y, z, a, b = self.get()
        return x, y

    @xy.setter
    def xy(self, values: Tuple[int, int]):
        x, y = values
        self.set(x=x, y=y, wait=self._wait)


    def move_in_projection(self, delta_x: int, delta_y: int) -> None:
        r"""y and z are always perpendicular to the sample stage. To achieve the movement
        in the projection, x and yshould be broken down into the components z' and y'.

        y = y' * cos(a)
        z = y' * sin(a)

        z'|  / z
          | /
          |/_____ y'
           \ a
            \
             \ y
        """
        x, y, z, a, b = self.get()
        a = np.radians(a)
        x = x + delta_x
        y = y + delta_y * np.cos(a)
        z = z - delta_y * np.sin(a)
        self.set(x=x, y=y, z=z)

    def move_along_optical_axis(self, delta_z: int):
        """See `Stage.move_in_projection`"""
        x, y, z, a, b = self.get()
        a = np.radians(a)
        y = y + delta_z * np.sin(a)
        z = z + delta_z * np.cos(a)
        self.set(y=y, z=z) 

    @property
    def z(self) -> int:
        x, y, z, a, b = self.get()
        return z

    @z.setter
    def z(self, value: int):
        self.set(z=value, wait=self._wait)

    @property
    def a(self) -> int:
        x, y, z, a, b = self.get()
        return a

    @a.setter
    def a(self, value: int):
        self.set(a=value, wait=self._wait)

    @property
    def b(self) -> int:
        x, y, z, a, b = self.get()
        return b

    @b.setter
    def b(self, value: int):
        self.set(b=value, wait=self._wait)

    def neutral(self) -> None:
        """Reset the position of the stage to the 0-position"""
        self.set(x=0, y=0, z=0, a=0, b=0)

    def is_moving(self) -> bool:
        """Return 'True' if the stage is moving"""
        return self._tem.isStageMoving()

    def wait_for_stage(self) -> None:
        """Blocking call that waits for stage movement to finish"""
        self._tem.waitForStage()

    @contextmanager
    def no_wait(self):
        """
        Context manager that prevents blocking stage position calls on properties.

        Usage:
            with ctrl.stage.no_wait():
                ctrl.stage.x += 1000
                ctrl.stage.y += 1000
        """
        self._wait = False
        yield
        self._wait = True

    def stop(self) -> None:
        """This will halt the stage preemptively if `wait=False` is passed to Stage.set"""
        self._tem.stopStage()

    def alpha_wobbler(self, delta: float=5.0, event=None) -> None:
        """Tilt the stage by plus/minus the value of delta (degrees)
        If event is not set, press Ctrl-C to interrupt"""

        a_center = self.a
        print(f"Wobbling 'alpha': {a_center:.2f}±{delta:.2f}")

        if event:
            while not event.is_set():
                self.a = a_center + delta
                self.a = a_center - delta
        else:
            print("(press 'Ctrl-C' to interrupt)")
            try:
                while True:
                    self.a = a_center + delta
                    self.a = a_center - delta
            except KeyboardInterrupt:
                pass

        print(f"Restoring 'alpha': {a_center:.2f}")
        self.a = a_center
        print(f"Print z={self.z:.2f}")

    def relax_xy(self, step: int=100) -> None:
        """Relax the stage by moving it in the opposite direction from the last movement"""
        pass

    def set_xy_with_backlash_correction(self, x: int=None, y: int=None, step: float=10000, settle_delay: float=0.200) -> None:
        """
        Move to new x/y position with backlash correction. This is done
        by approaching the target x/y position always from the same direction.

        SerialEM uses the same approach (x first, y second, step=10000).

        step: float,
            stepsize in nm
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        """
        wait = True
        self.set(x=x-step, y=y-step)
        if settle_delay:
            time.sleep(settle_delay)
        
        self.set(x=x, y=y, wait=wait)
        if settle_delay:
            time.sleep(settle_delay)

    def move_xy_with_backlash_correction(self, shift_x: int=None, shift_y: int=None, step: float=5000, settle_delay: float=0.200, wait=True) -> None:
        """
        Move xy by given shifts in stage coordinates with backlash correction. This is done by moving backwards
        from the targeted position by `step`, before moving to the targeted position. This function is meant
        to be used when precise relative movements are needed, for example when a shift is calculated from an
        image. Based on Liu et al., Sci. Rep. (2016) DOI: 10.1038/srep29231

        shift_x, shift_y: float,
            relative movement in x and y (nm)
        step: float,
            stepsize in nm
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        wait: bool, 
            block until stage movement is complete (JEOL only)
        """

        stage = self.get()

        if shift_x:
            target_x = stage.x + shift_x
            if target_x > stage.x:
                pre_x = stage.x - step
            elif target_x < stage.x:
                pre_x = stage.x + step
        else:
            pre_x = None
            target_x = None

        if shift_y:
            target_y = stage.y + shift_y
            if target_y > stage.y:
                pre_y = stage.y - step
            elif target_y < stage.y:
                pre_y = stage.y + step
        else:
            pre_y = None
            target_y = None

        self.set(x=pre_x, y=pre_y)
        if settle_delay:
            time.sleep(settle_delay)
        
        self.set(x=target_x, y=target_y, wait=wait)
        if settle_delay:
            time.sleep(settle_delay)

    def eliminate_backlash_xy(self, step: float=10000, settle_delay: float=0.200) -> None:
        """
        Eliminate backlash by in XY by moving the stage away from the current position, and
        approaching it from the common direction. Uses `set_xy_with_backlash_correction`
        internally.

        step: float,
            stepsize in nm
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        """
        stage = self.get()
        self.set_xy_with_backlash_correction(x=stage.x, y=stage.y, step=step, settle_delay=settle_delay)

    def eliminate_backlash_a(self, target_angle: float=0.0, step: float=1.0, n_steps: int=3, settle_delay: float=0.200) -> None:
        """
        Eliminate backlash by relaxing the position. The routine will move in opposite direction
        of the targeted angle by `n_steps`*`step`, and walk up to the current 
        tilt angle in `n_steps`. 
        Based on Suloway et al., J. Struct. Biol. (2009), doi: 10.1016/j.jsb.2009.03.019

        target_angle: float,
            target angle for the rotation in degrees
        step: float,
            stepsize in degrees
        n_steps: int > 0,
            number of steps to walk up to current angle
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        """
        current = self.a
        
        if target_angle > current:
            s = +1
        elif target_angle < current:
            s = -1
        else:
            return

        n_steps += 1
        s = target_direction/abs(target_direction)  # get sign of movement
        
        for i in reversed(range(n_steps)):
            self.a = current - s*i*stepsize
            time.sleep(settle_delay)


class TEMController(object):
    """
    TEMController object that enables access to all defined microscope controls

    tem: Microscope control object (e.g. instamatic/TEMController/simu_microscope.SimuMicroscope)
    cam: Camera control object (see instamatic.camera) [optional]
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
        self.stage = Stage(tem)
        self.stageposition = self.stage  # for backwards compatibility
        self.magnification = Magnification(tem)
        self.brightness = Brightness(tem)
        self.difffocus = DiffFocus(tem)

        self.autoblank = False
        self._saved_alignments = config.get_alignments()

        print()
        print(self)
        self.store()

    def __repr__(self):
        return (f"Mode: {self.tem.getFunctionMode()}\n"
                f"High tension: {self.high_tension/1000:.0f} kV\n"
                f"Current density: {self.current_density:.2f} pA/cm2\n"
                f"{self.gunshift}\n"
                f"{self.guntilt}\n"
                f"{self.beamshift}\n"
                f"{self.beamtilt}\n"
                f"{self.imageshift1}\n"
                f"{self.imageshift2}\n"
                f"{self.diffshift}\n"
                f"{self.stage}\n"
                f"{self.magnification}\n"
                f"{self.difffocus}\n"
                f"{self.brightness}\n"
                f"SpotSize({self.spotsize})\n"
                f"Saved alignments: {tuple(self._saved_alignments.keys())}\n")

    @property
    def high_tension(self) -> float:
        """Get the high tension value in V"""
        return self.tem.getHTValue()

    @property
    def current_density(self) -> float:
        """Get current density from fluorescence screen in pA/cm2"""
        return self.tem.getCurrentDensity()

    @property
    def spotsize(self) -> int:
        return self.tem.getSpotSize()

    @spotsize.setter
    def spotsize(self, value: int):
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
    def screen(self):
        """Returns one of 'up', 'down'"""
        self.tem.getScreenPosition()

    @screen.setter
    def screen(self, value: str):
        """Should be one of 'up', 'down'"""
        self.tem.setScreenPosition(value)

    def screen_up(self):
        """Raise the fluorescence screen"""
        self.tem.setScreenPosition("up")

    def screen_down(self):
        """Lower the fluorescence screen"""
        self.tem.setScreenPosition("down")

    def beamblank_on(self):
        """Turn the beamblank on."""
        self.tem.setBeamBlank(True)

    def beamblank_off(self, delay: float=0.0):
        """Turn the beamblank off, optionally wait for `delay` ms to allow the beam to settle."""
        self.tem.setBeamBlank(False)
        if delay:
            time.sleep(delay)

    @property
    def mode(self):
        """Returns one of 'mag1', 'mag2', 'lowmag', 'samag', 'diff'"""
        return self.tem.getFunctionMode()

    @mode.setter
    def mode(self, value: str):
        """Should be one of 'mag1', 'mag2', 'lowmag', 'samag', 'diff'"""
        self.tem.setFunctionMode(value)

    @property
    def beamblank(self):
        return self.tem.isBeamBlanked()

    @beamblank.setter
    def beamblank(self, on: bool):
        self.tem.setBeamBlank(on)

    def acquire_at_items(self, *args, **kwargs) -> None:
        """See instamatic.acquire_at_items.AcquireAtItems for documentation"""
        from instamatic.acquire_at_items import AcquireAtItems

        ctrl = self

        aai = AcquireAtItems(ctrl, *args, **kwargs)
        aai.start()

    def run_script_at_items(self, nav_items: list, script: str, backlash: bool=True) -> None:
        """"Run the given script at all coordinates defined by the nav_items.
        
        Parameters
        ----------
        nav_items: list
            Takes a list of nav items (read from a SerialEM .nav file) and loops over the
            stage coordinates
        script: str
            Runs this script at each of the positions specified in coordinate list
                This function will call 3 functions, which must be defined as:
                    `acquire`
                    `pre_acquire`
                    `post_acquire`

        backlash: bool
            Toggle to move to each position with backlash correction
        """
        from instamatic.tools import find_script
        script = find_script(script)

        import importlib.util
        spec = importlib.util.spec_from_file_location("acquire", script)
        acquire = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(acquire)

        import time
        import msvcrt

        ctrl = self

        ntot = len(nav_items)

        print(f"Running script: {script} on {ntot} items.")
        
        pre_acquire = getattr(acquire, "pre_acquire", None)
        post_acquire = getattr(acquire, "post_acquire", None)
        acquire = getattr(acquire, "acquire", None)

        self.acquire_at_items(nav_items,
                              acquire=acquire, 
                              pre_acquire=pre_acquire, 
                              post_acquire=post_acquire, 
                              backlash=backlash)

    def run_script(self, script: str, verbose: bool=True) -> None:
        """Run a custom python script with access to the `ctrl` object. It will check
        if the script exists in the scripts directory if it cannot find it directly.
        """
        from instamatic.tools import find_script
        script = find_script(script)

        ctrl = self

        if verbose:
            print(f"Executing script: {script}\n")

        t0 = time.perf_counter()
        exec(open(script).read())
        t1 = time.perf_counter()

        if verbose:
            print(f"\nScript finished in {t1-t0:.4f} s")

    def get_stagematrix(self, binning: int=None, mag: int=None, mode: int=None):
        """Helper function to get the stage matrix from the config file.
        The stagematrix is used to convert from pixel coordinates to stage
        coordiantes. The parameters are optional and if not given, 
        the current values are read out from the microscope/camera.
        
        Parameters
        ----------
        binning: int
            Binning of the image that the stagematrix will be applied to
        mag: int
            Magnification value
        mode: str
            Current TEM mode ("lowmag", "mag1")
        
        Returns
        -------
        stagematrix : np.array[2, 2]
            Affine transformation matrix to convert from stage to pixel coordinates
        """

        if not mode:
            mode = self.mode
        if not mag:
            mag = self.magnification.value
        if not binning:
            binning = self.cam.getBinning()

        stagematrix = getattr(config.calibration, f"stagematrix_{mode}")[mag]

        stagematrix = np.array(stagematrix).reshape(2, 2) / (1000 * binning[0])  # um -> nm

        return stagematrix

    def align_to(self, ref_img: "np.array", 
                       apply: bool= True) -> list:
        """Align current view by comparing it against the given image using
        cross correlation. The stage is translated so that the object of interest
        (in the reference image) is at the center of the view.
        
        Parameters
        ----------
        ref_img: np.array
            Reference image that the microscope will be aligned to
        apply: bool
            Toggle to translate the stage to center the image
        
        Returns
        -------
        stage_shift : np.array[2]
            The stage shift vector determined from cross correlation
            
        """
        from skimage.feature import register_translation

        current_x, current_y = self.stage.xy
        print(f"Current stage position: {current_x:.0f} {current_y:.0f}")
        stagematrix = self.get_stagematrix()
        mati = np.linalg.inv(stagematrix)

        img = self.getRawImage()

        pixel_shift = register_translation(ref_img, img, upsample_factor=10)

        stage_shift = np.dot(pixel_shift, mati)

        print(f"Shifting stage by dx={stage_shift[0]:.2f} dy={stage_shift[1]:.2f}")

        new_x = current_x - stage_shift[0] 
        new_y = current_y + stage_shift[1] 
        print(f"New stage position: {new_x:.0f} {new_y:.0f}")
        if apply:
            self.stage.set_xy_with_backlash_correction(x=new_x, y=new_y)

        return stage_shift

    def find_eucentric_height(self, tilt: float=5, 
                                    steps: int=5, 
                                    dz: int=50_000, 
                                    apply: bool=True, 
                                    verbose: bool=True) -> float:
        """Automated routine to find the eucentric height, accurate up to ~1 um
        Measures the shift (cross correlation) between 2 angles (-+tilt) over 
        a range of z values (defined by `dz` and `steps`). The height is calculated
        by fitting the shifts vs. z.

        Fit: shift = alpha*z + beta -> z0 = -beta/alpha

        Takes roughly 35 seconds (2 steps) or 70 seconds (5 steps) on a JEOL 1400 with a TVIPS camera.

        Based on: Koster, et al., Ultramicroscopy 46 (1992): 207–27. 
                  https://doi.org/10.1016/0304-3991(92)90016-D.

        Parameters
        ----------
        tilt:
            Tilt angles (+-)
        steps: int
            Number of images to take along the defined Z range
        dz: int
            Range to cover in nm (i.e. from -dz to +dz) around the current Z value
        apply: bool
            apply the Z height immediately
        verbose: bool
            Toggle the verbosity level

        Returns
        -------
        z: float
            Optimized Z value for eucentric tilting
        """
        from skimage.feature import register_translation

        def one_cycle(tilt: float=5, sign=1) -> list:
            angle1 = -tilt*sign
            self.stage.a = angle1
            img1 = self.getRawImage()
            
            angle2 = +tilt*sign
            self.stage.a = angle2
            img2 = self.getRawImage()
            
            if sign < 1:
                img2, img1 = img1, img2

            shift = register_translation(img1, img2, upsample_factor=10)

            return shift

        self.stage.a = 0
        # self.stage.z = 0 # for testing

        zc = self.stage.z
        print(f"Current z = {zc:.1f} nm")

        zs = zc + np.linspace(-dz, dz, steps)
        shifts = []

        sign = 1

        for i, z in enumerate(zs):
            self.stage.z = z
            if verbose:
                print(f"z = {z:.1f} nm")

            di = one_cycle(tilt=tilt, sign=sign)
            shifts.append(di)

            sign *= -1

        mean_shift = shifts[-1] + shifts[0]
        mean_shift = mean_shift/np.linalg.norm(mean_shift)
        ds = np.dot(shifts, mean_shift)

        p = np.polyfit(zs, ds, 1)  # linear fit
        alpha, beta = p

        z0 = -beta/alpha

        print(f"alpha={alpha:.2f} | beta={beta:.2f} => z0={z0:.1f} nm")
        if apply:
            self.stage.set(a=0, z=z0)

        return z0

    def montage(self):
        from instamatic.gridmontage import GridMontage
        gm = GridMontage(self)
        return gm

    def to_dict(self, *keys) -> dict:
        """
        Store microscope parameters to dict

        keys: tuple of str (optional)
            If any keys are specified, dict is returned with only the given properties
        
        self.to_dict('all') or self.to_dict() will return all properties
        """
        
        ## Each of these costs about 40-60 ms per call on a JEOL 2100, stage is 265 ms per call
        funcs = { 
            'FunctionMode': self.tem.getFunctionMode,
            'GunShift': self.gunshift.get,
            'GunTilt': self.guntilt.get,
            'BeamShift': self.beamshift.get,
            'BeamTilt': self.beamtilt.get,
            'ImageShift1': self.imageshift1.get,
            'ImageShift2': self.imageshift2.get,
            'DiffShift': self.diffshift.get,
            'StagePosition': self.stage.get,
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
            except ValueError as e:
                # print(f"No such key: `{key}`")
                pass

        return dct

    def from_dict(self, dct: dict):
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
            'StagePosition': self.stage.set,
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

    def getRawImage(self, exposure: float=0.5, binsize: int=1) -> np.ndarray:
        """Simplified function equivalent to `getImage` that only returns the raw data array"""
        return self.cam.getImage(exposure=exposure, binsize=binsize)

    def getImage(self, exposure: float=0.5, binsize: int=1, comment: str="", out: str=None, plot: bool=False, verbose: bool=False, header_keys: Tuple[str]="all") -> Tuple[np.ndarray, dict]:
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
            raise AttributeError(f"{self.__class__.__name__} object has no attribute 'cam' (Camera has not been initialized)")

        if not header_keys:
            h = {}
        else:
            h = self.to_dict(header_keys)

        if self.autoblank and self.beamblank:
            self.beamblank = False
        
        h["ImageGetTimeStart"] = time.perf_counter()

        arr = self.cam.getImage(exposure=exposure, binsize=binsize)
        
        h["ImageGetTimeEnd"] = time.perf_counter()
        
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
            print(f"Image acquired - shape: {arr.shape}, size: {arr.nbytes / 1024:.0f} kB")

        if out:
            write_tiff(out, arr, header=h)

        if plot:
            import matplotlib.pyplot as plt
            plt.imshow(arr)
            plt.show()

        return arr, h

    def store_diff_beam(self, name: str="beam", save_to_file: bool=False):
        """Record alignment for current diffraction beam.
        Stores Guntilt (for dose control), diffraction focus, spot size, brightness,
        and the function mode.

        Restore the alignment using:
            `ctrl.restore("beam")`"""
        if not self.mode == "diff":
            raise TEMControllerException("Microscope is not in `diffraction mode`")
        keys = "FunctionMode", "Brightness", "GunTilt", "DiffFocus", "SpotSize"
        self.store(name=name, keys=keys, save_to_file=save_to_file)

    def store(self, name: str="stash", keys: tuple=None, save_to_file: bool=False):
        """Stores current settings to dictionary.
        Multiple settings can be stored under different names.
        Specify which settings should be stored using `keys`"""
        if not keys:
            keys = ()
        d = self.to_dict(*keys)
        d.pop("StagePosition", None)
        self._saved_alignments[name] = d

        if save_to_file:
            import yaml
            fn = config.alignments_drc / (name + ".yaml")
            yaml.dump(d, stream=open(fn, "w"))
            print(f"Saved alignment to file `{fn}`")

    def restore(self, name: str="stash"):
        """Restores alignment from dictionary by the given name."""
        d = self._saved_alignments[name]
        self.from_dict(d)
        print(f"Microscope alignment restored from '{name}'")

    def close(self):
        try:
            self.cam.close()
        except AttributeError:
            pass

    def show_stream(self):
        """If the camera has been opened as a stream, start a live view in a tkinter window"""
        try:
           self.cam.show_stream()
        except AttributeError:
            print("Cannot open live view. The camera interface must be initialized as a stream object.")


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

    ctrl.close()
