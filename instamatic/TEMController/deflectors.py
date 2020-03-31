from collections import namedtuple
from typing import Tuple


DeflectorTuple = namedtuple('DeflectorTuple', ['x', 'y'])


class Deflector:
    """Generic microscope deflector object defined by X/Y values Must be
    subclassed to set the self._getter, self._setter functions."""

    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._getter = None
        self._setter = None
        self.key = 'def'

    def __repr__(self):
        x, y = self.get()
        return f'{self.name}(x={x}, y={y})'

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


class GunShift(Deflector):
    """GunShift control."""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunShift
        self._getter = self._tem.getGunShift
        self.key = 'GUN1'


class GunTilt(Deflector):
    """GunTilt control."""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setGunTilt
        self._getter = self._tem.getGunTilt
        self._tem = tem
        self.key = 'GUN2'


class BeamShift(Deflector):
    """BeamShift control (CLA1)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamShift
        self._getter = self._tem.getBeamShift
        self.key = 'CLA1'


class BeamTilt(Deflector):
    """BeamTilt control (CLA2)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamTilt
        self._getter = self._tem.getBeamTilt
        self.key = 'CLA2'


class DiffShift(Deflector):
    """Control for the Diffraction Shift (PLA)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setDiffShift
        self._getter = self._tem.getDiffShift
        self.key = 'PLA'


class ImageShift1(Deflector):
    """ImageShift control (IS1)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift1
        self._getter = self._tem.getImageShift1
        self.key = 'IS1'


class ImageShift2(Deflector):
    """ImageShift control (IS2)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setImageShift2
        self._getter = self._tem.getImageShift2
        self.key = 'IS2'
