#!/usr/bin/env python

import numpy as np

from IPython.terminal.embed import InteractiveShellEmbed
InteractiveShellEmbed.confirm_exit = False
ipshell = InteractiveShellEmbed(banner1='')

__version__ = "2016-06-29"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"

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

            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)

        class GunTilt(object):
            x = TEMValue("x", tem.getGunTilt, tem.setGunTilt)
            y = TEMValue("y", tem.getGunTilt, tem.setGunTilt)

            def __repr__(self):
                d = tem.getGunTilt()
                return "GunTilt(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)

        class BeamShift(object):
            x = TEMValue("x", tem.getBeamShift, tem.setBeamShift)
            y = TEMValue("y", tem.getBeamShift, tem.setBeamShift)

            def __repr__(self):
                d = tem.getGunTilt()
                return "BeamShift(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)

        class BeamTilt(object):
            x = TEMValue("x", tem.getBeamTilt, tem.setBeamTilt)
            y = TEMValue("y", tem.getBeamTilt, tem.setBeamTilt)

            def __repr__(self):
                d = tem.getGunTilt()
                return "BeamTilt(x={x}, y={y})".format(**d)

            def goto(self, **kwargs):
                tem.setStagePosition(kwargs)

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
    else:
        from instamatic.pyscope import jeolcom
        tem = jeolcom.Jeol()
    
    ctrl = TEMController(tem)

    ipshell()


if __name__ == '__main__':
    from instamatic.pyscope import simtem
    tem = simtem.SimTEM()
    ctrl = TEMController(tem)
    ipshell()
