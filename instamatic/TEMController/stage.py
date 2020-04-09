import time
from collections import namedtuple
from contextlib import contextmanager
from typing import Tuple

import numpy as np


# namedtuples to store results from .get()
StagePositionTuple = namedtuple('StagePositionTuple', ['x', 'y', 'z', 'a', 'b'])


class Stage:
    """Stage control."""

    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._setter = self._tem.setStagePosition
        self._getter = self._tem.getStagePosition
        self._wait = True  # properties only

    def __repr__(self):
        x, y, z, a, b = self.get()
        return f'{self.name}(x={x:.1f}, y={y:.1f}, z={z:.1f}, a={a:.1f}, b={b:.1f})'

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set(self, x: int = None, y: int = None, z: int = None, a: int = None, b: int = None, wait: bool = True) -> None:
        """wait: bool, block until stage movement is complete (JEOL only)"""
        self._setter(x, y, z, a, b, wait=wait)

    def set_with_speed(self, x: int = None, y: int = None, z: int = None, a: int = None, b: int = None, wait: bool = True, speed: float = 1.0) -> None:
        """Note that this function only works on FEI machines.

        wait: ignored, but necessary for compatibility with JEOL API
        speed: float, set stage rotation with specified speed (FEI only)
        """
        self._setter(x, y, z, a, b, wait=wait, speed=speed)

    def set_rotation_speed(self, speed=1) -> None:
        """Sets the stage (rotation) movement speed on the TEM."""
        self._tem.setRotationSpeed(value=speed)

    def set_a_with_speed(self, a: float, speed: int, wait: bool = False):
        """Rotate to angle `a` with speed (JEOL only).

        wait: bool, block until stage movement is complete.
        """
        with self.rotating_speed(speed):
            self.set(a=a, wait=False)
        # Do not wait on `set` to return to normal rotation speed quickly
        if wait:
            self.wait()

    @contextmanager
    def rotating_speed(self, speed: int):
        """Context manager that sets the rotation speed for the duration of the
        `with` statement (JEOL only).

        Usage:
            with ctrl.stage.rotating_speed(1):
                ctrl.stage.a = 40.0
        """
        try:
            current_speed = self._tem.getRotationSpeed()
        except BaseException:
            yield  # on error
        else:
            if current_speed != speed:
                self.set_rotation_speed(speed)
                yield  # default flow
                self.set_rotation_speed(current_speed)
            else:
                yield  # if requested speed is the same as current

    def get(self) -> Tuple[int, int, int, int, int]:
        """Get stage positions; x, y, z, and status of the rotation axes; a,
        b."""
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
        """Reset the position of the stage to the 0-position."""
        self.set(x=0, y=0, z=0, a=0, b=0)

    def is_moving(self) -> bool:
        """Return 'True' if the stage is moving."""
        return self._tem.isStageMoving()

    def wait(self) -> None:
        """Blocking call that waits for stage movement to finish."""
        self._tem.waitForStage()

    @contextmanager
    def no_wait(self):
        """Context manager that prevents blocking stage position calls on
        properties.

        Usage:
            with ctrl.stage.no_wait():
                ctrl.stage.x += 1000
                ctrl.stage.y += 1000
        """
        self._wait = False
        yield
        self._wait = True

    def stop(self) -> None:
        """This will halt the stage preemptively if `wait=False` is passed to
        Stage.set."""
        self._tem.stopStage()

    def alpha_wobbler(self, delta: float = 5.0, event=None) -> None:
        """Tilt the stage by plus/minus the value of delta (degrees) If event
        is not set, press Ctrl-C to interrupt."""

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
        print(f'Print z={self.z:.2f}')

    def relax_xy(self, step: int = 100) -> None:
        """Relax the stage by moving it in the opposite direction from the last
        movement."""
        pass

    def set_xy_with_backlash_correction(self, x: int = None, y: int = None, step: float = 10000, settle_delay: float = 0.200) -> None:
        """Move to new x/y position with backlash correction. This is done by
        approaching the target x/y position always from the same direction.

        SerialEM uses the same approach (x first, y second, step=10000).

        step: float,
            stepsize in nm
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        """
        wait = True
        self.set(x=x - step, y=y - step)
        if settle_delay:
            time.sleep(settle_delay)

        self.set(x=x, y=y, wait=wait)
        if settle_delay:
            time.sleep(settle_delay)

    def move_xy_with_backlash_correction(self, shift_x: int = None, shift_y: int = None, step: float = 5000, settle_delay: float = 0.200, wait=True) -> None:
        """Move xy by given shifts in stage coordinates with backlash
        correction. This is done by moving backwards from the targeted position
        by `step`, before moving to the targeted position. This function is
        meant to be used when precise relative movements are needed, for
        example when a shift is calculated from an image. Based on Liu et al.,
        Sci. Rep. (2016) DOI: 10.1038/srep29231.

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

    def eliminate_backlash_xy(self, step: float = 10000, settle_delay: float = 0.200) -> None:
        """Eliminate backlash by in XY by moving the stage away from the
        current position, and approaching it from the common direction. Uses
        `set_xy_with_backlash_correction` internally.

        step: float,
            stepsize in nm
        settle_delay: float,
            delay between movements in seconds to allow the stage to settle
        """
        stage = self.get()
        self.set_xy_with_backlash_correction(x=stage.x, y=stage.y, step=step, settle_delay=settle_delay)

    def eliminate_backlash_a(self, target_angle: float = 0.0, step: float = 1.0, n_steps: int = 3, settle_delay: float = 0.200) -> None:
        """Eliminate backlash by relaxing the position. The routine will move
        in opposite direction of the targeted angle by `n_steps`*`step`, and
        walk up to the current tilt angle in `n_steps`. Based on Suloway et
        al., J. Struct. Biol. (2009), doi: 10.1016/j.jsb.2009.03.019.

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

        for i in reversed(range(n_steps)):
            self.a = current - s * i * step
            time.sleep(settle_delay)
