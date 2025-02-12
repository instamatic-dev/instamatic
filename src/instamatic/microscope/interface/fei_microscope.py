from __future__ import annotations

import atexit
import logging
import time
from typing import Optional

import comtypes.client
from numpy import pi

from instamatic import config
from instamatic.exceptions import FEIValueError, TEMCommunicationError
from instamatic.microscope.base import MicroscopeBase
from instamatic.microscope.utils import StagePositionTuple
from instamatic.typing import float_deg, int_nm

logger = logging.getLogger(__name__)


# speed table (deg/s):
# 1.00: 21.14
# 0.90: 19.61
# 0.80: 18.34
# 0.70: 16.90
# 0.60: 14.85
# 0.50: 12.69
# 0.40: 10.62
# 0.30: 8.20
# 0.20: 5.66
# 0.10: 2.91
# 0.05: 1.48
# 0.04: 1.18
# 0.03: 0.888
# 0.02: 0.593
# 0.01: 0.297

FUNCTION_MODES = {0: 'LM', 1: 'Mi', 2: 'SA', 3: 'Mh', 4: 'LAD', 5: 'D'}


def get_magnification_mapping():
    functions = ('LM', 'Mi', 'SA', 'Mh')
    values = (val for function in functions for val in config.microscope.ranges[function])
    return {num + 1: val for num, val in enumerate(values)}


def get_camera_length_mapping():
    return {num + 1: val for num, val in enumerate(config.microscope.ranges['D'])}


MagnificationMapping = get_magnification_mapping()
CameraLengthMapping = get_camera_length_mapping()


class FEIMicroscope(MicroscopeBase):
    """Python bindings to the FEI microscope using the COM interface."""

    def __init__(self, name='fei'):
        super().__init__()

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            comtypes.CoInitialize()

        print('FEI Themis Z initializing...')
        # tem interfaces the GUN, stage obj etc but does not communicate with the Instrument objects
        self.tem = comtypes.client.CreateObject(
            'TEMScripting.Instrument.1', comtypes.CLSCTX_ALL
        )
        # tecnai does similar things as tem; the difference is not clear for now
        self.tecnai = comtypes.client.CreateObject('Tecnai.Instrument', comtypes.CLSCTX_ALL)
        # tom interfaces the Instrument, Projection objects
        self.tom = comtypes.client.CreateObject('TEM.Instrument.1', comtypes.CLSCTX_ALL)

        # TEM Status constants
        self.tem_constant = comtypes.client.Constants(self.tem)

        self.stage = self.tem.Stage
        self.proj = self.tom.Projection
        t = 0
        while True:
            ht = self.tem.GUN.HTValue
            if ht > 0:
                break
            time.sleep(1)
            t += 1
            if t > 3:
                print(f'Waiting for microscope, t = {t}s')
            if t > 30:
                raise TEMCommunicationError('Cannot establish microscope connection (timeout).')

        logger.info('Microscope connection established')
        atexit.register(self.release_connection)

        self.name = name
        self.FUNCTION_MODES = FUNCTION_MODES

        self.FunctionMode_value = 0

        self.goniostopped = self.stage.Status

        input(
            'Please select the type of sample stage before moving on.\nPress <ENTER> to continue...'
        )

    def getHTValue(self):
        return self.tem.GUN.HTValue

    def setHTValue(self, htvalue):
        self.tem.GUN.HTValue = htvalue

    def getCurrentDensity(self) -> float:
        """Get the current density from the fluorescence screen in nA?"""
        value = self.tecnai.Camera.ScreenCurrent
        # value = -1
        return value

    def getMagnification(self):
        if self.tom.Projection.Mode != 1:
            ind = self.proj.MagnificationIndex
            return MagnificationMapping[ind]
        else:
            ind = self.proj.CameraLengthIndex
            return CameraLengthMapping[ind]

    def setMagnification(self, value):
        """Value has to be the index."""
        if self.tom.Projection.Mode != 1:
            ind = [key for key, v in MagnificationMapping.items() if v == value][0]
            try:
                self.proj.MagnificationIndex = ind
            except ValueError:
                pass
        else:
            ind = [key for key, v in CameraLengthMapping.items() if v == value][0]
            self.tom.Projection.CameraLengthIndex = ind

    def getMagnificationRanges(self) -> dict:
        raise NotImplementedError

    def setStageSpeed(self, value):
        """Value be 0 - 1"""
        if value > 1 or value < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {value}')

        self.tom.Stage.Speed = value

    def getStageSpeed(self):
        return self.tom.Stage.Speed

    def getStagePosition(self) -> StagePositionTuple:
        """Return x, y, z in nanometers (used to be microns), angles in deg."""
        return StagePositionTuple(
            round(self.stage.Position.X * 1e9),
            round(self.stage.Position.Y * 1e9),
            round(self.stage.Position.Z * 1e9),
            float(self.stage.Position.A / pi * 180),
            float(self.stage.Position.B / pi * 180),
        )

    def setStagePosition(
        self,
        x: Optional[int_nm] = None,
        y: Optional[int_nm] = None,
        z: Optional[int_nm] = None,
        a: Optional[float_deg] = None,
        b: Optional[float_deg] = None,
        wait: bool = True,
        speed: float = 1.0,
    ) -> None:
        """X, y, z in the system are in unit of meters, angles in radians."""
        pos = self.stage.Position
        axis = 0

        if speed > 1 or speed < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {speed}')

        self.tom.Stage.Speed = speed
        goniospeed = self.tom.Stage.Speed

        if x is not None:
            pos.X = x * 1e-9
            axis += 1
        if y is not None:
            pos.Y = y * 1e-9
            axis += 2
        if z is not None:
            pos.Z = z * 1e-9
            axis += 4
        if a is not None:
            pos.A = a / 180 * pi
            axis += 8
        if b is not None:
            pos.B = b / 180 * pi
            axis += 16

        if speed == 1:
            self.stage.Goto(pos, axis)
        else:
            if x is not None:
                self.stage.GotoWithSpeed(pos, 1, goniospeed)
            if y is not None:
                self.stage.GotoWithSpeed(pos, 2, goniospeed)
            if z is not None:
                self.stage.GotoWithSpeed(pos, 4, goniospeed)
            if a is not None:
                self.stage.GotoWithSpeed(pos, 8, goniospeed)
            if b is not None:
                self.stage.GotoWithSpeed(pos, 16, goniospeed)

    def getGunShift(self):
        x = self.tem.GUN.Shift.X
        y = self.tem.GUN.Shift.Y
        return x, y

    def setGunShift(self, x, y):
        """X y can only be float numbers between -1 and 1."""
        gs = self.tem.GUN.Shift
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(
                f'GunShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}'
            )

        if x is not None:
            gs.X = x
        if y is not None:
            gs.Y = y

        self.tem.GUN.Shift = gs

    def getGunTilt(self):
        x = self.tem.GUN.Tilt.X
        y = self.tem.GUN.Tilt.Y
        return x, y

    def setGunTilt(self, x, y):
        gt = self.tecnai.Gun.Tilt
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(
                f'GunTilt x/y must be a floating number between -1 an 1. Input: x={x}, y={y}'
            )

        if x is not None:
            gt.X = x
        if y is not None:
            gt.Y = y

        self.tecnai.Gun.Tilt = gt

    def getBeamShift(self):
        """User Shift."""
        '1.19 ms in communication. Super fast!'
        x = self.tom.Illumination.BeamShift.X
        y = self.tom.Illumination.BeamShift.Y
        return x, y

    def setBeamShift(self, x, y):
        """User Shift."""
        bs = self.tom.Illumination.BeamShift
        if abs(x) > 1 or abs(y) > 1:
            print('Invalid gunshift setting: can only be float numbers between -1 and 1.')
            return

        if x is not None:
            bs.X = x
        if y is not None:
            bs.Y = y
        self.tom.Illumination.BeamShift = bs

    def getBeamAlignShift(self):
        """Align Shift."""
        x = self.tom.Illumination.BeamAlignShift.X
        y = self.tom.Illumination.BeamAlignShift.Y
        return x, y

    def setBeamAlignShift(self, x, y):
        """Align Shift."""
        bs = self.tom.Illumination.BeamAlignShift
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(
                f'BeamAlignShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}'
            )

        if x is not None:
            bs.X = x
        if y is not None:
            bs.Y = y
        self.tom.Illumination.BeamAlignShift = bs

    def getBeamTilt(self):
        """Rotation center in FEI."""
        x = self.tom.Illumination.BeamAlignmentTilt.X
        y = self.tom.Illumination.BeamAlignmentTilt.Y
        return x, y

    def setBeamTilt(self, x, y):
        """Rotation center in FEI."""
        bt = self.tom.Illumination.BeamAlignmentTilt

        if x is not None:
            if abs(x) > 1:
                raise FEIValueError(
                    f'BeamTilt x must be a floating number between -1 an 1. Input: x={x}'
                )
            bt.X = x
        if y is not None:
            if abs(y) > 1:
                raise FEIValueError(
                    f'BeamTilt y must be a floating number between -1 an 1. Input: y={y}'
                )
            bt.Y = y
        self.tom.Illumination.BeamAlignmentTilt = bt

    def getImageShift1(self):
        """User image shift."""
        return self.tom.Projection.ImageShift.X, self.tom.Projection.ImageShift.Y

    def setImageShift1(self, x, y):
        is1 = self.tom.Projection.ImageShift
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(
                f'ImageShift1 x/y must be a floating number between -1 an 1. Input: x={x}, y={y}'
            )

        if x is not None:
            is1.X = x
        if y is not None:
            is1.Y = y

        self.tom.Projection.ImageShift = is1

    def getImageShift2(self):
        return 0, 0

    def setImageShift2(self, x, y):
        return 0

    def getImageBeamShift(self):
        """Image-beam shift."""
        return self.tom.Projection.ImageBeamShift.X, self.tom.Projection.ImageBeamShift.Y

    def setImageBeamShift(self, x, y):
        is1 = self.tom.Projection.ImageBeamShift
        if abs(x) > 1 or abs(y) > 1:
            print('Invalid gunshift setting: can only be float numbers between -1 and 1.')
            return

        if x is not None:
            is1.X = x
        if y is not None:
            is1.Y = y

        self.tom.Projection.ImageBeamShift = is1

    def isStageMoving(self):
        if self.stage.Status == 0:
            return False
        else:
            return True

    def stopStage(self):
        # self.stage.Status = self.goniostopped
        raise NotImplementedError

    def getFunctionMode(self):
        """{1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'}"""
        mode = self.tom.Projection.Submode
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """{1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'}"""
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise FEIValueError(f'Unrecognized function mode: {value}')
        self.FunctionMode_value = value

    def getHolderType(self):
        return self.stage.Holder

    """What is the relationship between defocus and focus?? Both are changing the defoc value"""

    def getDiffFocus(self):
        return self.tom.Projection.Defocus

    def setDiffFocus(self, value):
        """Defocus value in unit m."""
        self.tom.Projection.Defocus = value

    def getFocus(self):
        return self.tom.Projection.Focus

    def setFocus(self, value):
        self.tom.Projection.Focus = value

    def getApertureSize(self, aperture):
        if aperture == 'C1':
            return self.tom.Illumination.C1ApertureSize * 1e3
        elif aperture == 'C2':
            return self.tom.Illumination.C2ApertureSize * 1e3
        else:
            raise FEIValueError("aperture must be specified as 'C1' or 'C2'.")

    def getDarkFieldTilt(self):
        return self.tom.Illumination.DarkfieldTilt.X, self.tom.Illumination.DarkfieldTilt.Y

    def setDarkFieldTilt(self, x, y):
        """Does not set."""
        return 0

    def getScreenCurrent(self):
        """Return screen current in nA."""
        return self.tom.Screen.Current * 1e9

    def isfocusscreenin(self):
        return self.tom.Screen.IsFocusScreenIn

    def getDiffShift(self):
        """User diff shift, encoded in a different way than system status on
        TEM USER INTERFACE: 180/pi*number = number on TEM USER INTERFACE.

        Not exactly though, close enough
        """
        return (
            180 / pi * self.tem.Projection.DiffractionShift.X,
            180 / pi * self.tem.Projection.DiffractionShift.Y,
        )

    def setDiffShift(self, x, y):
        ds1 = self.tem.Projection.DiffractionShift
        if abs(x) > 1 or abs(y) > 1:
            print('Invalid gunshift setting: can only be float numbers between -1 and 1.')
            return

        if x is not None:
            ds1.X = x / 180 * pi
        if y is not None:
            ds1.Y = y / 180 * pi

        self.tem.Projection.DiffractionShift = ds1

    def release_connection(self):
        comtypes.CoUninitialize()
        logger.info('Connection to microscope released')
        print('Connection to microscope released')

    def isBeamBlanked(self):
        """To be tested."""
        return self.tem.Illumination.BeamBlanked

    def setBeamBlank(self, value):
        """True/False or 1/0."""
        self.tem.Illumination.BeamBlanked = value

    def setBeamUnblank(self):
        self.tem.Illumination.BeamBlanked = 0

    def getCondensorLensStigmator(self):
        return (
            self.tom.Illumination.CondenserStigmator.X,
            self.tom.Illumination.CondenserStigmator.Y,
        )

    def setCondensorLensStigmator(self, x, y):
        self.tom.Illumination.CondenserStigmator.X = x
        self.tom.Illumination.CondenserStigmator.Y = y

    def getIntermediateLensStigmator(self):
        """Diffraction stigmator."""
        return (
            self.tom.Illumination.DiffractionStigmator.X,
            self.tom.Illumination.DiffractionStigmator.Y,
        )

    def setIntermediateLensStigmator(self, x, y):
        self.tom.Illumination.DiffractionStigmator.X = x
        self.tom.Illumination.DiffractionStigmator.Y = y

    def getObjectiveLensStigmator(self):
        return (
            self.tom.Illumination.ObjectiveStigmator.X,
            self.tom.Illumination.ObjectiveStigmator.Y,
        )

    def setObjectiveLensStigmator(self, x, y):
        self.tom.Illumination.ObjectiveStigmator.X = x
        self.tom.Illumination.ObjectiveStigmator.Y = y

    def getSpotSize(self):
        """0-based indexing for GetSpotSize, add 1 for consistency."""
        return self.tom.Illumination.SpotsizeIndex

    def setSpotSize(self, value):
        self.tom.Illumination.SpotsizeIndex = value

    def getMagnificationIndex(self):
        if self.tom.Projection.Mode != 1:
            ind = self.proj.MagnificationIndex
            return ind
        else:
            ind = self.proj.CameraLengthIndex
            return ind

    def getMagnificationAbsoluteIndex(self) -> int:
        raise NotImplementedError

    def setMagnificationIndex(self, index):
        if self.tom.Projection.Mode != 1:
            self.proj.MagnificationIndex = index
        else:
            self.proj.CameraLengthIndex = index

    def getBrightness(self):
        """Return diameter in microns."""
        return self.tom.Illumination.IlluminatedAreaDiameter * 1e6

    def setBrightness(self, value):
        self.tom.Illumination.IlluminatedAreaDiameter = value * 1e-6

    def getScreenPosition(self) -> str:
        raise NotImplementedError

    def setScreenPosition(self, value: str) -> None:
        raise NotImplementedError
