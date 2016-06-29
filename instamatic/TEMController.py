#!/usr/bin/env python

import numpy as np

from IPython.terminal.embed import InteractiveShellEmbed
InteractiveShellEmbed.confirm_exit = False
ipshell = InteractiveShellEmbed(banner1='')


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


class TEMController(object):
    """docstring for TEMController

    descriptors:
    https://docs.python.org/2/howto/descriptor.html
    """

    def __init__(self, tem):
        super(TEMController, self).__init__()
        self.tem = tem

        class GunShift(object):
            x = TEMValue("x", tem.getGunShift, tem.setGunShift)
            y = TEMValue("y", tem.getGunShift, tem.setGunShift)

            def __repr__(self):
                d = tem.getGunShift()
                return "GunShift(x={x}, y={y})".format(**d)

        class GunTilt(object):
            x = TEMValue("x", tem.getGunTilt, tem.setGunTilt)
            y = TEMValue("y", tem.getGunTilt, tem.setGunTilt)

            def __repr__(self):
                d = tem.getGunTilt()
                return "GunTilt(x={x}, y={y})".format(**d)

        class BeamShift(object):
            x = TEMValue("x", tem.getBeamShift, tem.setBeamShift)
            y = TEMValue("y", tem.getBeamShift, tem.setBeamShift)

            def __repr__(self):
                d = tem.getGunTilt()
                return "BeamShift(x={x}, y={y})".format(**d)

        class BeamTilt(object):
            x = TEMValue("x", tem.getBeamTilt, tem.setBeamTilt)
            y = TEMValue("y", tem.getBeamTilt, tem.setBeamTilt)

            def __repr__(self):
                d = tem.getGunTilt()
                return "BeamTilt(x={x}, y={y})".format(**d)

        class ImageShift(object):
            x = TEMValue("x", tem.getImageShift, tem.setImageShift)
            y = TEMValue("y", tem.getImageShift, tem.setImageShift)

            def __repr__(self):
                d = tem.getGunTilt()
                return "ImageShift(x={x}, y={y})".format(**d)

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
                return "StagePosition(x={x}, y={y}, z={z}, a={a}, b={b})".format(**d)

        self.gunshift = GunShift()
        self.guntilt = GunTilt()
        self.beamshift = BeamShift()
        self.beamtilt = BeamTilt()
        self.imageshift = ImageShift()
        self.stageposition = StagePosition()

        print self

    def __repr__(self):
        return "\n".join((str(self.gunshift),
                          str(self.guntilt),
                          str(self.beamshift),
                          str(self.beamtilt),
                          str(self.imageshift),
                          str(self.stageposition)))

    def get_all(self):
        d = {
            'beamshift': self.tem.getBeamShift(),
            'beamtilt': self.tem.getBeamTilt(),
            'gunshift': self.tem.getGunShift(),
            'guntilt': self.tem.getGunTilt(),
            'imageshift': self.tem.getImageShift(),
            'stageposition': self.tem.getStagePosition()
        }
        return d

    def set_all(self, d):
        funcs = {
            'beamshift': self.tem.setBeamShift,
            'beamtilt': self.tem.setBeamTilt,
            'gunshift': self.tem.setGunShift,
            'guntilt': self.tem.setGunTilt,
            'imageshift': self.tem.setImageShift,
            'stageposition': self.tem.setStagePosition
        }

        for k, v in d.items():
            func = funcs[k]
            func(v)

        print self


if __name__ == '__main__':
    from instamatic.pyscope import simtem
    tem = simtem.SimTEM()
    controller = TEMController(tem)

    d = {'beamshift': {'x': 2.0, 'y': 64.0},
         'beamtilt': {'x': 3.0, 'y': 23.0},
         'gunshift': {'x': 4.0, 'y': 4.0},
         'guntilt': {'x': 5.0, 'y': 23.0},
         'imageshift': {'x': 6.0, 'y': 9.0},
         'stageposition': {'a': 1.0, 'x': 0.0001, 'y': 0.0007, 'z': 0.0005}}

    controller.set_all(d)

    # ipshell()
