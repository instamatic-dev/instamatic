import atexit
import logging
import time
import multiprocessing

import comtypes.client
from numpy import pi

from instamatic import config
from instamatic.exceptions import FEIValueError
from instamatic.exceptions import TEMCommunicationError
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

"""
LM     Imaging mode, low magnification
Mi     Imaging mode, lower intermediate magnification range
SA     Imaging mode, high magnification
Mh     Imaging mode, highest magnification range
LAD    Diffraction, LAD mode (the mode entered from LM imaging)
D      Diffraction mode as entered from higher magnification imaging modes
"""
FUNCTION_MODES = {1: 'LM', 2: 'Mi', 3: 'SA', 4: 'Mh', 5: 'LAD', 6: 'D'}

# Need more checking
MagnificationMapping = {
    1: 45,
    2: 58,
    3: 73,
    4: 89,
    5: 115,
    6: 145,
    7: 185,
    8: 235,
    9: 300,
    10: 380,
    11: 470,
    12: 600,
    13: 760,
    14: 950,
    15: 1200,
    16: 1550,
    17: 3400,
    18: 4400,
    19: 5600,
    20: 7200,
    21: 8800,
    22: 11500,
    23: 14500,
    24: 18500,
    25: 24000,
    26: 30000,
    27: 38000,
    28: 49000,
    29: 61000,
    30: 77000,
    31: 100000,
    32: 130000,
    33: 165000,
    34: 215000,
    35: 265000,
    36: 340000,
    37: 430000,
    38: 550000,
    39: 700000,
    40: 890000,
    41: 1150000,
    42: 1250000,
    43: 960000,
    44: 750000,
    45: 600000,
    46: 470000,
    47: 360000,
    48: 285000,
    49: 225000,
    50: 175000,
    51: 145000,
    52: 115000,
    53: 89000,
    54: 66000,
    55: 52000,
    56: 41000,
    57: 32000,
    58: 26000,
    59: 21000,
    60: 8300,
    61: 6200,
    62: 3100}

# Checking if LAD mode CameraLengthMapping is different from D mode
CameraLengthMapping = {
    1: 34,
    2: 42,
    3: 53,
    4: 68,
    5: 90,
    6: 115,
    7: 140,
    8: 175,
    9: 215,
    10: 265,
    11: 330,
    12: 420,
    13: 530,
    14: 680,
    15: 830,
    16: 1050,
    17: 1350,
    18: 1700,
    19: 2100,
    20: 2700,
    21: 3700}

def move_stage(x=None, y=None, z=None, a=None, b=None, speed=1):
    """Rotate stage function. Mainly for start a new process and move the stage to achieve non-blocking stage manipulation"""
    tem = comtypes.client.CreateObject('TEMScripting.Instrument', comtypes.CLSCTX_ALL)
    tom = comtypes.client.CreateObject('TEM.Instrument', comtypes.CLSCTX_ALL)

    tom.Stage.Speed = speed
    goniospeed = tom.Stage.Speed
    pos = tem.Stage.Position
    axis = 0

    if x is not None:
        pos.X = x * 1e-6
        axis += 1
    if y is not None:
        pos.Y = y * 1e-6
        axis += 2
    if z is not None:
        pos.Z = z * 1e-6
        axis += 4
    if a is not None:
        pos.A = a / 180 * pi
        axis += 8
    if b is not None:
        pos.B = b / 180 * pi
        axis += 16
    if speed == 1:
        tem.Stage.Goto(pos, axis)
    else:
        if x is not None:
            tem.Stage.GotoWithSpeed(pos, 1, goniospeed)
        if y is not None:
            tem.Stage.GotoWithSpeed(pos, 2, goniospeed)
        if z is not None:
            tem.Stage.GotoWithSpeed(pos, 4, goniospeed)
        if a is not None:
            tem.Stage.GotoWithSpeed(pos, 8, goniospeed)
        if b is not None:
            tem.Stage.GotoWithSpeed(pos, 16, goniospeed)

class FEIMicroscope:
    """Python bindings to the FEI microscope using the COM interface."""

    def __init__(self, name='fei'):
        super().__init__()

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            comtypes.CoInitialize()

        print('FEI Themis Z initializing...')
        # tem interfaces the GUN, stage obj etc but does not communicate with the Instrument objects
        self.tem = comtypes.client.CreateObject('TEMScripting.Instrument', comtypes.CLSCTX_ALL)
        # tecnai does similar things as tem; the difference is not clear for now
        self.tecnai = comtypes.client.CreateObject('Tecnai.Instrument', comtypes.CLSCTX_ALL)
        # tom interfaces the Instrument, Projection objects
        self.tom = comtypes.client.CreateObject('TEM.Instrument', comtypes.CLSCTX_ALL)

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
        atexit.register(self.releaseConnection)

        self.name = name
        self.FUNCTION_MODES = FUNCTION_MODES

        self.FunctionMode_value = 0

        self.goniostopped = self.stage.Status

        input('Please select the type of sample stage before moving on.\nPress <ENTER> to continue...')

    def getHTValue(self):
        return self.tem.GUN.HTValue

    def setHTValue(self, htvalue):
        self.tem.GUN.HTValue = htvalue

    def getCurrentDensity(self) -> float:
        """Need to get the current density from the fluorescence screen in nA? Call it current density 
           for compatibility issues"""
        value = self.tem.Camera.ScreenCurrent * 1e9
        return value

    def getMagnification(self):
        if self.tom.Projection.Mode != 1:
            ind = self.proj.MagnificationIndex
            return MagnificationMapping[ind]
        else:
            ind = self.proj.CameraLengthIndex
            return CameraLengthMapping[ind]

    def setMagnification(self, value):
        """value has to be the index."""
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
        """Value be 0 - 1. 1.9ms per call"""
        if value > 1 or value < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {value}')

        self.tom.Stage.Speed = value

    def getStageSpeed(self):
        """return the number of stage speed between 0 and 1. 2ms per call"""
        return self.tom.Stage.Speed

    def getStagePosition(self):
        """return numbers in microns, angles in degs. 3ms per call"""
        return self.stage.Position.X * 1e6, self.stage.Position.Y * 1e6, self.stage.Position.Z * 1e6, self.stage.Position.A / pi * 180, self.stage.Position.B / pi * 180
    
    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, wait=True, speed=1):
        """x, y, z in the system are in unit of meters, angles in radians. 1s per call (without moving anything)."""
        if speed > 1 or speed < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {speed}')

        if not self.isStageMoving():
            if wait:
                move_stage(x, y, z, a, b, speed)
            else:
                p = multiprocessing.Process(target=move_stage, args=(x,y,z,a,b,speed,))
                p.start()

    def getGunShift(self):
        """150 ms per call"""
        x = self.tem.GUN.Shift.X
        y = self.tem.GUN.Shift.Y
        return x, y

    def setGunShift(self, x, y):
        """x y can only be float numbers between -1 and 1. 150 ms per call"""
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(f'GunShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')

        gs = self.tem.GUN.Shift

        if x is not None:
            gs.X = x
        if y is not None:
            gs.Y = y

        self.tem.GUN.Shift = gs

    def getGunTilt(self):
        """150ms per call"""
        x = self.tem.GUN.Tilt.X
        y = self.tem.GUN.Tilt.Y
        return x, y

    def setGunTilt(self, x, y):
        """150ms per call"""
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(f'GunTilt x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')

        gt = self.tem.Gun.Tilt

        if x is not None:
            gt.X = x
        if y is not None:
            gt.Y = y

        self.tem.Gun.Tilt = gt

    def getBeamShift(self):
        """User Shift. 6ms per call"""
        '1.19 ms in communication. Super fast!'
        x = self.tom.Illumination.BeamShift.X
        y = self.tom.Illumination.BeamShift.Y
        return x, y

    def setBeamShift(self, x, y):
        """User Shift. 10ms per call"""
        if abs(x) > 1 or abs(y) > 1:
            print('Invalid gunshift setting: can only be float numbers between -1 and 1.')
            return

        bs = self.tom.Illumination.BeamShift
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
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(f'BeamAlignShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')
        bs = self.tom.Illumination.BeamAlignShift

        if x is not None:
            bs.X = x
        if y is not None:
            bs.Y = y
        self.tom.Illumination.BeamAlignShift = bs

    def getBeamTilt(self):
        """rotation center in FEI. 5ms per call"""
        x = self.tom.Illumination.BeamAlignmentTilt.X
        y = self.tom.Illumination.BeamAlignmentTilt.Y
        return x, y

    def setBeamTilt(self, x, y):
        """rotation center in FEI. 9.8ms per call"""
        bt = self.tom.Illumination.BeamAlignmentTilt

        if x is not None:
            if abs(x) > 1:
                raise FEIValueError(f'BeamTilt x must be a floating number between -1 an 1. Input: x={x}')
            bt.X = x
        if y is not None:
            if abs(y) > 1:
                raise FEIValueError(f'BeamTilt y must be a floating number between -1 an 1. Input: y={y}')
            bt.Y = y
        self.tom.Illumination.BeamAlignmentTilt = bt

    def getImageShift1(self):
        """User image shift. 5ms per call
           The image shift with respect to the origin that is defined by alignment. Units: meters."""
        return self.tom.Projection.ImageShift.X, self.tom.Projection.ImageShift.Y

    def setImageShift1(self, x, y):
        """9.8ms per call
           The image shift with respect to the origin that is defined by alignment. Units: meters."""
        is1 = self.tom.Projection.ImageShift
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError(f'ImageShift1 x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')

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
        """image-beam shift. 5ms per call
           Image shift with respect to the origin that is defined by alignment. The apparent beam shift is compensated for, 
           without affecting the Shift-property of the Illumination-object. Units: meters.
           Attention: Avoid intermixing ImageShift and ImageBeamShift, otherwise it would mess up the beam shift 
           (=Illumination.Shift). If you want to use both alternately, then reset the other to zero first."""
        return self.tom.Projection.ImageBeamShift.X, self.tom.Projection.ImageBeamShift.Y

    def setImageBeamShift(self, x, y):
        """9.8ms per call
           Image shift with respect to the origin that is defined by alignment. The apparent beam shift is compensated for, 
           without affecting the Shift-property of the Illumination-object. Units: meters.
           Attention: Avoid intermixing ImageShift and ImageBeamShift, otherwise it would mess up the beam shift 
           (=Illumination.Shift). If you want to use both alternately, then reset the other to zero first."""
        is1 = self.tom.Projection.ImageBeamShift
        if abs(x) > 1 or abs(y) > 1:
            print('Invalid gunshift setting: can only be float numbers between -1 and 1.')
            return

        if x is not None:
            is1.X = x
        if y is not None:
            is1.Y = y

        self.tom.Projection.ImageBeamShift = is1

    def getImageBeamTilt(self):
        """Beam tilt with respect to the origin that is defined by alignment (rotation center). The resulting 
           diffraction shift is compensated for, without affecting the DiffractionShift-property of the Projection 
           object. For proper operation requires calibration (alignment) of the Beam Tilt - Diffraction Shift 
           (for more information, see a0050100.htm on the TEM software installation CD under privada\beamtiltdiffshift). Units: radians.
           Attention: Avoid intermixing Tilt (of the beam in Illumination) and ImageBeamTilt. If you want to 
           use both alternately, then reset the other to zero first."""
        pass

    def setImageBeamTilt(self, x, y):
        """Beam tilt with respect to the origin that is defined by alignment (rotation center). The resulting 
           diffraction shift is compensated for, without affecting the DiffractionShift-property of the Projection 
           object. For proper operation requires calibration (alignment) of the Beam Tilt - Diffraction Shift 
           (for more information, see a0050100.htm on the TEM software installation CD under privada\beamtiltdiffshift). Units: radians.
           Attention: Avoid intermixing Tilt (of the beam in Illumination) and ImageBeamTilt. If you want to 
           use both alternately, then reset the other to zero first."""
        pass

    def isStageMoving(self):
        """Check if sample stage is moving"""
        if self.stage.Status == 0:
            return False
        else:
            return True

    def stopStage(self):
        """Stop the sample stage, not working for FEI microscope now"""
        # self.stage.Status = self.goniostopped
        print("Unable to stop the stage for FEI microscope")
        return -1

    def getFunctionMode(self):
        """read only! {1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'} Submode of the projection system (either LM, Mi, ..., 
           LAD or D). The imaging submode can change, when the magnification is changed."""
        mode = self.tom.Projection.Submode
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """Read only! This function does not set the mode. {1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'} Submode of the 
           projection system (either LM, Mi, ..., LAD or D). The imaging submode can change, when the magnification is changed."""
        if isinstance(value, str):
            try:
                for key, val in FUNCTION_MODES.items():
                    if val == value:
                        value = key
            except ValueError:
                raise FEIValueError(f'Unrecognized function mode: {value}.')
        self.FunctionMode_value = value

    def getHolderType(self):
        return self.stage.Holder

    def getDiffFocus(self, confirm_mode=True):
        if confirm_mode and (self.getFunctionMode() not in ("LAD", "D")):
            raise FEIValueError("Must be in 'LAD' or 'D' mode to get DiffFocus")
        return self.tem.Projection.Defocus

    def setDiffFocus(self, value, confirm_model=True):
        if confirm_mode and (self.getFunctionMode() not in ("LAD", "D")):
            raise FEIValueError("Must be in 'LAD' or 'D' mode to get DiffFocus")
        self.tem.Projection.Defocus = value

    def getDefocus(self, confirm_mode=True):
        """1.2ms per call. 
           Defocus value of the currently active mode. Changing ‘Defocus’ will also change ‘Focus’ 
           and vice versa. ‘Defocus’ is in physical units (meters) and measured with respect to a origin that can 
           be set by using ‘ResetDefocus()’."""
        if confirm_mode and (self.getFunctionMode() not in ('LM','Mi','SA','Mh')):
            raise FEIValueError("Must be in ('LM','Mi','SA','Mh') mode to get Defocus")
        return self.tem.Projection.Defocus

    def setDefocus(self, value, confirm_mode=True):
        """defocus value in unit m. 6ms per call. 
           Defocus value of the currently active mode. Changing ‘Defocus’ will also change ‘Focus’ 
           and vice versa. ‘Defocus’ is in physical units (meters) and measured with respect to a origin that can 
           be set by using ‘ResetDefocus()’."""
        if confirm_mode and (self.getFunctionMode() not in ('LM','Mi','SA','Mh')):
            raise FEIValueError("Must be in ('LM','Mi','SA','Mh') mode to get Defocus")
        self.tem.Projection.Defocus = value

    def ResetDefocus(self):
        """Resets the current ‘Defocus’ to 0 nm. This does not change the ‘Focus’ value (the focussing lens current). 
           Use it when the image is properly focussed to adjust the ‘Defocus’ scale."""
        self.tem.ResetDefocus()

    def getFocus(self):
        """1.2ms per call
           Focus setting of the currently active mode. Range: maximum between -1.0  (= underfocussed) and 
           1.0 (= overfocussed), but the exact limits are mode dependent and may be a lot lower."""
        return self.tem.Projection.Focus

    def setFocus(self, value):
        """6.5ms per call
           Focus setting of the currently active mode. Range: maximum between -1.0  (= underfocussed) and 
           1.0 (= overfocussed), but the exact limits are mode dependent and may be a lot lower."""
        self.tem.Projection.Focus = value

    def getApertureSize(self, aperture):
        if aperture == 'C1':
            return self.tom.Illumination.C1ApertureSize * 1e3
        elif aperture == 'C2':
            return self.tom.Illumination.C2ApertureSize * 1e3
        else:
            raise FEIValueError("Aperture must be specified as 'C1' or 'C2'.")

    def getScreenCurrent(self):
        """return screen current in nA."""
        return self.tem.Camera.ScreenCurrent * 1e9

    def isfocusscreenin(self):
        return self.tom.Screen.IsFocusScreenIn

    def getScreenPosition(self):
        """return value: 'up' or 'down'"""
        dic = {0:'down', 1:'up'}
        return dic[self.tom.Screen.Position]

    def setScreenPosition(self, value):
        """value = 'up' or 'down'"""
        dic = {'down':0, 'up':1}
        self.tom.Screen.SetScreenPosition(dict[value])

    def getDiffShift(self):
        """user diff shift, encoded in a different way than system status on TEM USER INTERFACE: 
           180/pi*number = number on TEM USER INTERFACE. Not exactly though, close enough
           The diffraction pattern shift with respect to the origin that is defined by alignment. Units: radians."""
        return 180 / pi * self.tem.Projection.DiffractionShift.X, 180 / pi * self.tem.Projection.DiffractionShift.Y

    def setDiffShift(self, x, y):
        """user diff shift, encoded in a different way than system status on TEM USER INTERFACE: 
           180/pi*number = number on TEM USER INTERFACE. Not exactly though, close enough
           The diffraction pattern shift with respect to the origin that is defined by alignment. Units: radians."""
        ds1 = self.tem.Projection.DiffractionShift
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError('Invalid gunshift setting: can only be float numbers between -1 and 1.')

        if x is not None:
            ds1.X = x / 180 * pi
        if y is not None:
            ds1.Y = y / 180 * pi

        self.tem.Projection.DiffractionShift = ds1

    def releaseConnection(self):
        comtypes.CoUninitialize()
        logger.info('Connection to microscope released')
        print('Connection to microscope released')

    def isBeamBlanked(self):
        """to be tested."""
        return self.tem.Illumination.BeamBlanked

    def setBeamBlank(self, value):
        """True/False or 1/0."""
        self.tem.Illumination.BeamBlanked = value

    def setBeamUnblank(self):
        self.tem.Illumination.BeamBlanked = 0

    def getCondenserLensStigmator(self):
        return self.tom.Illumination.CondenserStigmator.X, self.tom.Illumination.CondenserStigmator.Y

    def setCondenserLensStigmator(self, x, y):
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError('Invalid condenser lens stigmator setting: can only be float numbers between -1 and 1.')
        self.tom.Illumination.CondenserStigmator.X = x
        self.tom.Illumination.CondenserStigmator.Y = y

    def getIntermediateLensStigmator(self):
        """diffraction stigmator."""
        return self.tom.Illumination.DiffractionStigmator.X, self.tom.Illumination.DiffractionStigmator.Y

    def setIntermediateLensStigmator(self, x, y):
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError('Invalid intermediate lens stigmator setting: can only be float numbers between -1 and 1.')
        self.tom.Illumination.DiffractionStigmator.X = x
        self.tom.Illumination.DiffractionStigmator.Y = y

    def getObjectiveLensStigmator(self):
        return self.tom.Illumination.ObjectiveStigmator.X, self.tom.Illumination.ObjectiveStigmator.Y

    def setObjectiveLensStigmator(self, x, y):
        if abs(x) > 1 or abs(y) > 1:
            raise FEIValueError('Invalid objective lens stigmator setting: can only be float numbers between -1 and 1.')
        self.tom.Illumination.ObjectiveStigmator.X = x
        self.tom.Illumination.ObjectiveStigmator.Y = y

    def getSpotSize(self):
        """The spot size index (usually ranging from 1 to 11). 220ms per call."""
        return self.tem.Illumination.SpotsizeIndex

    def setSpotSize(self, value):
        """The spot size index (usually ranging from 1 to 11). 224ms per call."""
        if value < 1 or value > 11:
            raise FEIValueError('The range of spot size is from 1 to 11.')
        self.tem.Illumination.SpotsizeIndex = value

    def getMagnificationIndex(self):
        """"""
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
        """return diameter in microns."""
        return self.tom.Illumination.IlluminatedAreaDiameter * 1e6

    def setBrightness(self, value):
        """return diameter in microns."""
        self.tom.Illumination.IlluminatedAreaDiameter = value * 1e-6

    def getIlluminatedArea(self):
        """return diameter in microns. The size of the illuminated area. Accessible only in Parallel mode."""
        return self.tem.Illumination.IlluminatedArea * 1e6

    def setIlluminatedArea(self, value):
        """return diameter in microns. The size of the illuminated area. Accessible only in Parallel mode."""
        self.tem.Illumination.IlluminatedArea = value * 1e-6

    def isStemAvailable(self):
        """Returns whether themicroscope has a STEM system or not."""
        return self.tem.InstrumentModeControl.StemAvailable

    def getInstrumentMode(self):
        """Switches between TEM and STEM modes."""
        dct = {0: "TEM", 1: "STEM"}
        return dct[self.tem.InstrumentModeControl.InstrumentMode]

    def setInstrumentMode(self, value):
        """Switches between TEM and STEM modes."""
        dct = {"TEM": 0, "STEM": 1}
        if value == "STEM":
            if not self.isStemAvailable():
                raise FEIValueError("There is no STEM mode in this microscope.")
            self.tem.InstrumentModeControl.InstrumentMode = dct[value]
        elif value == "TEM":
            self.tem.InstrumentModeControl.InstrumentMode = dct[value]
        else:
            print("Please input TEM mode or STEM mode.")

    def getProbeMode(self):
        """Mode of the illumination system (either nanoprobe or microprobe). 
           (Nearly) no effect for low magnifications (LM)."""
        return self.tem.Illumination.Mode

    def setProbeMode(self, value):
        """Mode of the illumination system (either nanoprobe or microprobe). 
           (Nearly) no effect for low magnifications (LM)."""
        if value != 0 or value != 1:
            raise FEIValueError('The probe mode must be 0 or 1.')
        self.tem.Illumination.Mode = value

    def getProbeIntensity(self):
        """Intensity value of the current mode (typically ranging from 0 to 1.0, 
           but on some microscopes the minimum may be higher"""
        return self.tem.Illumination.Intensity

    def setProbeIntensity(self, value):
        """Intensity value of the current mode (typically ranging from 0 to 1.0, 
           but on some microscopes the minimum may be higher"""
        if value < 0 or y > 1:
            raise FEIValueError('The range of intensity of probe is from 0 to 1.')
        self.tem.Illumination.Intensity = value


    def isIntensityZoomEnabled(self):
        """Activates/deactivates the intensity zoom in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        return self.tem.Illumination.IntensityZoomEnabled

    def setIntensityZoomEnabled(self, value: bool):
        """Activates/deactivates the intensity zoom in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        self.tem.Illumination.IntensityZoomEnabled = value

    def isIntensityLimitEnabled(self):
        """Activates/deactivates the intensity limit in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        return self.tem.Illumination.IntensityLimitEnabled

    def setIntensityLimitEnabled(self, value: bool):
        """Activates/deactivates the intensity limit in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        self.tem.Illumination.IntensityLimitEnabled = value

    def getProbeShift(self):
        """Beam shift relative to the origin stored at alignment time. Units: meters."""
        return self.tem.Illumination.Shift.X, self.tem.Illumination.Shift.Y

    def setProbeShift(self, x, y):
        """Beam shift relative to the origin stored at alignment time. Units: meters."""
        self.tem.Illumination.Shift.X = x
        self.tem.Illumination.Shift.Y = y

    def getDarkFieldTilt(self):
        """Dark field beam tilt relative to the origin stored at alignment time. Only operational, 
           if dark field mode is active. Units: radians, either in Cartesian (x,y) or polar (conical) tilt angles. 
           The accuracy of the beam tilt physical units depends on a calibration of the tilt angles"""
        return self.tem.Illumination.Tilt.X, self.tem.Illumination.Tilt.Y

    def setDarkFieldTilt(self, x, y):
        """Dark field beam tilt relative to the origin stored at alignment time. Only operational, 
           if dark field mode is active. Units: radians, either in Cartesian (x,y) or polar (conical) tilt angles. 
           The accuracy of the beam tilt physical units depends on a calibration of the tilt angles"""
        self.tem.Illumination.Tilt.X = x
        self.tem.Illumination.Tilt.Y = y

    def getRotationCenter(self):
        """Corresponds to the alignment beam tilt value. Units are radians, range is ± 0.2-0.3rad. 
           Do not confuse RotationCenter with dark field (Tilt). Be aware that this is an alignment function."""
        return self.tem.Illumination.RotationCenter.X, self.tem.Illumination.RotationCenter.Y

    def setRotationCenter(self, x, y):
        """Corresponds to the alignment beam tilt value. Units are radians, range is ± 0.2-0.3rad. 
           Do not confuse RotationCenter with dark field (Tilt). Be aware that this is an alignment function."""
        if abs(x) > 0.3 or abs(y) > 0.3:
            raise FEIValueError('Invalid rotation center setting: can only be float numbers between -0.3 and 0.3.')
        self.tem.Illumination.RotationCenter.X = x
        self.tem.Illumination.RotationCenter.Y = y

    def getStemMagnification(self):
        """The magnification value in STEM mode. You can change the magnification only in discrete steps 
           (the same as on the microscope). If you specify a value that is not one of those steps, the scripting 
           will select the nearest available step."""
        return self.tem.Illumination.StemMagnification

    def setStemMagnification(self, value):
        """The magnification value in STEM mode. You can change the magnification only in discrete steps 
           (the same as on the microscope). If you specify a value that is not one of those steps, the scripting 
           will select the nearest available step."""
        self.tem.Illumination.StemMagnification = value

    def getStemRotation(self):
        """The STEM rotation angle (in radians)."""
        return self.tem.Illumination.StemRotation

    def setStemRotation(self, value):
        """The STEM rotation angle (in radians)."""
        value = value * pi / 180
        self.tem.Illumination.StemRotation = value

    def getProbeDefocus(self):
        """The amount of probe defocus (in meters). Accessible only in Probe mode."""
        return self.tem.Illumination.ProbeDefocus

    def setProbeDefocus(self, value):
        """The amount of probe defocus (in meters). Accessible only in Probe mode."""
        self.tem.Illumination.ProbeDefocus = value

    def getConvergenceAngle(self):
        """The convergence angle (in radians). Accessible only in Probe mode."""
        return self.tem.Illumination.ConvergenceAngle

    def setConvergenceAngle(self, value):
        """The convergence angle (in radians). Accessible only in Probe mode."""
        self.tem.Illumination.ConvergenceAngle = value

    def NormalizeCondenser(self, index):
        """Normalizes the condenser lenses and/or the minicondenser lens, dependent on the choice of ‘Norm’.
           1: Spotsize       normalize lens C1 (spotsize)
           2: Intensity      normalize lens C2 (intensity) + C3
           3: Condenser      normalize C1 + C2 + C3
           4: MiniCondenser  normalize the minicondenser lens
           5: ObjectivePole  normalize minicondenser and objective
           6: All            normalize C1, C2, C3, minicondenser + objective"""
        if index not in range(1,7):
            raise FEIValueError('Invalid condenser normalize setting: index should between 1 and 6.')
        return self.tem.Illumination.Normalize(index)

    def NormalizeProjection(self):
        """Normalizes the objective lens or the projector lenses, dependent on the choice of ‘Norm’.
           10: Objective    Normalize objective lens
           11: Projector    Normalize Diffraction, Intermediate, P1 and P2 lenses
           12: All          Normalize objective, diffraction, intermediate, P1 and P2 lenses"""
        if index not in (10, 11, 12):
            raise FEIValueError('Invalid condenser normalize setting: index should between 10 and 12.')
        return self.tem.Projection.Normalize(index)

    def isAutoLoaderAvailable(self):
        """Returns whether the AutoLoader is available on the microscope."""
        return self.tem.AutoLoader.AutoLoaderAvailable

    def getNumberOfCassetteSlots(self):
        """The number of cassette slots in a cartridge."""
        return self.tem.AutoLoader.NumberOfCassetteSlots

    def getSlotStatus(self, index):
        """The status of the slot specified.
           CassetteSlotStatus_Unknown       Cassette slot status has not been determined
           CassetteSlotStatus_Occupied      Cassette slot contains a cartridge
           CassetteSlotStatus_Empty         Cassette slot is empty
           CassetteSlotStatus_Error         Cassette slot generated an error"""
        return self.tem.AutoLoader.SlotStatus(index)

    def LoadCartridge(self, index):
        """([in] fromSlot Long) Loads the cartride from the given slot into the microscope."""
        self.tem.AutoLoader.LoadCartridge(index)

    def UnloadCartridge(self):
        """Unloads the cartridge currently in the microscope and puts it back into its slot in the cassette."""
        self.tem.AutoLoader.UnloadCartridge()

    def getProjectionMode(self):
        """Main mode of the projection system (either imaging or diffraction).
           1: Imaging          Projector in imaging mode
           2: Diffraction      Projector in diffraction  mode"""
        return self.tem.Projection.Mode

    def setProjectionMode(self, value):
        """Main mode of the projection system (either imaging or diffraction).
           1: Imaging          Projector in imaging mode
           2: Diffraction      Projector in diffraction  mode"""
        self.tem.Projection.Mode = value

    def getLensProgram(self):
        """The lens program setting (currently EFTEM or Regular). This is the third property to 
           characterize a mode of the projection system.
           1: Regular        The default lens program
           2: EFTEM          Lens program used for EFTEM (energy-filtered TEM)"""
        return self.tem.Projection.LensProgram

    def setLensProgram(self, value):
        """The lens program setting (currently EFTEM or Regular). This is the third property to 
           characterize a mode of the projection system.
           1: Regular        The default lens program
           2: EFTEM          Lens program used for EFTEM (energy-filtered TEM)"""
        self.tem.Projection.LensProgram = value

    def getImageRotation(self):
        """The rotation of the image or diffraction pattern on the fluorescent screen 
           with respect to the specimen. Units: radians."""
        return self.tem.Projection.ImageRotation

    def getDetectorShift(self):
        """Sets the extra shift that projects the image/diffraction pattern onto a detector.
           0: pdsOnAxis       Does not shift the image/diffraction pattern
           1: pdsNearAxis     Shifts the image/diffraction pattern onto a near-axis detector/camera
           2: pdsOffAxis      Shifts the image/diffraction pattern onto an off-axis detector/camera"""
        return self.tem.Projection.DetectorShift

    def setDetectorShift(self, value):
        """Sets the extra shift that projects the image/diffraction pattern onto a detector.
           0: pdsOnAxis       Does not shift the image/diffraction pattern
           1: pdsNearAxis     Shifts the image/diffraction pattern onto a near-axis detector/camera
           2: pdsOffAxis      Shifts the image/diffraction pattern onto an off-axis detector/camera"""
        self.tem.Projection.DetectorShift = value

    def getDetectorShiftMode(self):
        """This property determines, whether the chosen DetectorShift is changed when the fluorescent screen is moved down.
           0: pdsmAutoIgnore       The 'DetectorShift' is set to zero, when the fluorescent screen moves down. 
                                When it moves up again, what happens depends on what detector TEM thinks is 
                                currently selected. Take care!.
           1: pdsmManual           The detectorshift is applied as it is chosen in the 'DetectorShift'-property
           2: pdsmAlignment        The detector shift is (temporarily) controlled by an active alignment procedure. 
                                Clients cannot set this value. Clients cannot set the 'DetectorShiftMode' to another 
                                value either, if this is the current value. They have to wait until the alignment is finished."""
        return self.tem.Projection.DetectorShiftMode

    def setDetectorShiftMode(self, value):
        """This property determines, whether the chosen DetectorShift is changed when the fluorescent screen is moved down.
           0: pdsmAutoIgnore       The 'DetectorShift' is set to zero, when the fluorescent screen moves down. 
                                When it moves up again, what happens depends on what detector TEM thinks is 
                                currently selected. Take care!.
           1: pdsmManual           The detectorshift is applied as it is chosen in the 'DetectorShift'-property
           2: pdsmAlignment        The detector shift is (temporarily) controlled by an active alignment procedure. 
                                Clients cannot set this value. Clients cannot set the 'DetectorShiftMode' to another 
                                value either, if this is the current value. They have to wait until the alignment is finished."""
        self.tem.Projection.DetectorShiftMode = value 

    def isShutterOverrideOn(self) -> bool:
        """The BlankerShutter object has only one property, ShutterOverrideOn. This property can be used in 
           cryo-electron microscopy to burn ice off the specimen while blocking the beam from hitting the CCD camera. 
           When the shutter override is true, the CCD camera no longer has control over the microscope shutters. 
           The shutter below the specimen is closed. Whether the beam is on the specimen is determined by the 
           BeamBlanked property of the Illumination object.
           Suggested procedure:
           1. Blank the beam using the BeamBlanked property of the Illumination object.
           2. Switch the shutter override on.
           3. If necessary, wait for a short delay (one second) to allow the system to execute the shuttering.
           4. Unblank the beam (the CCD no longer has control).
           5. Wait for the time necessary to burn off the ice (sleep, Windows timer, ...)
           6. Blank the beam.
           7. Switch the shutter override off.
           8. If necessary, wait for a short delay (one second) to allow the system to switch the shuttering back to normal.
           9. Unblank the beam (the CCD now has control again)."""
        return self.tem.BlankerShutter.ShutterOverrideOn

    def setShutterOverrideOn(self, value: bool):
        """The BlankerShutter object has only one property, ShutterOverrideOn. This property can be used in 
           cryo-electron microscopy to burn ice off the specimen while blocking the beam from hitting the CCD camera. 
           When the shutter override is true, the CCD camera no longer has control over the microscope shutters. 
           The shutter below the specimen is closed. Whether the beam is on the specimen is determined by the 
           BeamBlanked property of the Illumination object.
           Suggested procedure:
           1. Blank the beam using the BeamBlanked property of the Illumination object.
           2. Switch the shutter override on.
           3. If necessary, wait for a short delay (one second) to allow the system to execute the shuttering.
           4. Unblank the beam (the CCD no longer has control).
           5. Wait for the time necessary to burn off the ice (sleep, Windows timer, ...)
           6. Blank the beam.
           7. Switch the shutter override off.
           8. If necessary, wait for a short delay (one second) to allow the system to switch the shuttering back to normal.
           9. Unblank the beam (the CCD now has control again)."""
        self.tem.BlankerShutter.ShutterOverrideOn = value

    def getDiffractionShift(self):
        """The diffraction pattern shift with respect to the origin that is defined by alignment. Units: radians."""
        return self.tem.Projection.DiffractionShift.X, self.tem.Projection.DiffractionShift.Y

    def setDiffractionShift(self, x, y):
        """Parameter x and y are in degree. The diffraction pattern shift with respect to the origin that is 
           defined by alignment. Units: radians."""
        x = x * pi / 180
        y = y * pi / 180
        self.tem.Projection.DiffractionShift.X = x 
        self.tem.Projection.DiffractionShift.Y = y

