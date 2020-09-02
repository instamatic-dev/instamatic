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

USETOM = False

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
STEM_FOCUS_STRATEGY = {1: 'Intensity', 2: 'Objective', 3: 'StepSize', 4: 'Both'}

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

# Unit: mm
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

# Unit: mm
CameraLengthMapping_LAD = {
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

    stage_tom = tom.Stage
    stage_tem = tem.Stage

    stage_tom.Speed = speed
    goniospeed = stage_tom.Speed
    if USETOM:
        pos = stage_tom.Position
        axis = 0
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
        if axis != 0:
            if speed == 1:
                stage_tom.Goto(pos, axis)
            else:
                if x is not None:
                    stage_tom.GotoWithSpeed(0, pos.X)
                if y is not None:
                    stage_tom.GotoWithSpeed(1, pos.Y)
                if z is not None:
                    stage_tom.GotoWithSpeed(2, pos.Z)
                if a is not None:
                    stage_tom.GotoWithSpeed(3, pos.A)
                if b is not None:
                    raise FEIValueError("Beta tilt cannot be moved with speed")
    else:
        pos = stage_tem.Position
        axis = 0

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
        if axis != 0:
            if speed == 1:
                stage_tem.Goto(pos, axis)
            else:
                if x is not None:
                    stage_tem.GotoWithSpeed(pos, 1, goniospeed)
                if y is not None:
                    stage_tem.GotoWithSpeed(pos, 2, goniospeed)
                if z is not None:
                    stage_tem.GotoWithSpeed(pos, 4, goniospeed)
                if a is not None:
                    stage_tem.GotoWithSpeed(pos, 8, goniospeed)
                if b is not None:
                    raise FEIValueError("Beta tilt cannot be moved with speed")

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
        # tom interfaces the Instrument, Projection objects, much faster than tem interfaces
        self.tom = comtypes.client.CreateObject('TEM.Instrument', comtypes.CLSCTX_ALL)

        # TEM Status constants
        self.tem_constant = comtypes.client.Constants(self.tem)

        self.gun_tom = self.tom.Gun
        self.illu_tom = self.tom.Illumination
        self.stage_tom = self.tom.Stage
        self.proj_tom = self.tom.Projection
        self.gun_tem = self.tem.Gun
        self.illu_tem = self.tem.Illumination
        self.stage_tem = self.tem.Stage
        self.proj_tem = self.tem.Projection

        t = 0
        while True:
            ht = self.getHTValue()
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

        input('Please select the type of sample stage before moving on.\nPress <ENTER> to continue...')

    def getHTValue(self):
        '''The value of the HT setting as displayed in the TEM user interface. Units: Volts.'''
        if USETOM:
            return self.gun_tom.HT
        else:
            return self.gun_tem.HTValue

    def setHTValue(self, htvalue):
        '''The value of the HT setting as displayed in the TEM user interface. Units: Volts.'''
        if USETOM:
            self.gun_tom.HT = htvalue
        else:
            self.gun_tem.HTValue = htvalue

    def getCurrentDensity(self) -> float:
        """Need to get the current density from the fluorescence screen in nA? Call it current density 
           for compatibility issues"""
        raise FEIValueError("Cannot obtain current density in FEI microscope")

    def getMagnification(self):
        if USETOM:
            if self.getProjectionMode() == 'imaging':
                ind = self.proj_tom.MagnificationIndex
                return MagnificationMapping[ind]
            else:
                ind = self.proj_tom.CameraLengthIndex
                return CameraLengthMapping[ind]
        else:
            if self.getProjectionMode() == 'imaging':
                ind = self.proj_tem.MagnificationIndex
                return MagnificationMapping[ind]
            else:
                ind = self.proj_tem.CameraLengthIndex
                return CameraLengthMapping[ind]

    def setMagnification(self, value):
        """value has to be the index."""
        if USETOM:
            if self.getProjectionMode() == 'imaging':
                ind = [key for key, v in MagnificationMapping.items() if v == value][0]
                try:
                    self.proj_tom.MagnificationIndex = ind
                except ValueError:
                    pass
            else:
                ind = [key for key, v in CameraLengthMapping.items() if v == value][0]
                self.proj_tom.CameraLengthIndex = ind
        else:
            if self.getProjectionMode() == 'imaging':
                ind = [key for key, v in MagnificationMapping.items() if v == value][0]
                try:
                    self.proj_tem.MagnificationIndex = ind
                except ValueError:
                    pass
            else:
                ind = [key for key, v in CameraLengthMapping.items() if v == value][0]
                self.proj_tem.CameraLengthIndex = ind

    def getMagnificationRanges(self) -> dict:
        raise NotImplementedError

    def setStageSpeed(self, value):
        """Value be 0 - 1. 1.9ms per call"""
        if value > 1 or value < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {value}')

        self.stage_tom.Speed = value

    def getStageSpeed(self):
        """return the number of stage speed between 0 and 1. 2ms per call"""
        return self.stage_tom.Speed

    def getStagePosition(self):
        """return numbers in microns, angles in degs. 3ms per call"""
        pos = self.stage_tem.Position
        return pos.X * 1e9, pos.Y * 1e9, pos.Z * 1e9, pos.A / pi * 180, pos.B / pi * 180
    
    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, wait=True, speed=1):
        """x, y, z in the system are in unit of nm, angles in radians. 1s per call (without moving anything)."""
        if speed > 1 or speed < 0:
            raise FEIValueError(f'setStageSpeed value must be between 0 and 1. Input: {speed}')

        if not self.isStageMoving():
            if wait:
                self.stage_tom.Speed = speed
                goniospeed = self.stage_tom.Speed
                if USETOM:
                    pos = self.stage_tom.Position
                    axis = 0

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
                    if axis != 0:
                        if speed == 1:
                            self.stage_tom.Goto(pos, axis)
                        else:
                            if x is not None:
                                self.stage_tom.GotoWithSpeed(0, pos.X)
                            if y is not None:
                                self.stage_tom.GotoWithSpeed(1, pos.Y)
                            if z is not None:
                                self.stage_tom.GotoWithSpeed(2, pos.Z)
                            if a is not None:
                                self.stage_tom.GotoWithSpeed(3, pos.A)
                            if b is not None:
                                raise FEIValueError("Beta tilt cannot be moved with speed")
                else:
                    pos = self.stage_tem.Position
                    axis = 0

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
                    if axis != 0:
                        if speed == 1:
                            self.stage_tem.Goto(pos, axis)
                        else:
                            if x is not None:
                                self.stage_tem.GotoWithSpeed(pos, 1, goniospeed)
                            if y is not None:
                                self.stage_tem.GotoWithSpeed(pos, 2, goniospeed)
                            if z is not None:
                                self.stage_tem.GotoWithSpeed(pos, 4, goniospeed)
                            if a is not None:
                                self.stage_tem.GotoWithSpeed(pos, 8, goniospeed)
                            if b is not None:
                                raise FEIValueError("Beta tilt cannot be moved with speed")
            else:
                p = multiprocessing.Process(target=move_stage, args=(x,y,z,a,b,speed,))
                p.start()

    def getGunShift(self):
        """The gunshift alignment values. Range from -1.0 to +1.0 in x and y directions (logical units).150 ms per call"""
        x = self.gun_tem.Shift.X
        y = self.gun_tem.Shift.Y
        return x, y

    def setGunShift(self, x=None, y=None):
        """The gunshift alignment values. Range from -1.0 to +1.0 in x and y directions (logical units). 150 ms per call"""
        try:
            if abs(x) > 1 or abs(y) > 1:
                raise FEIValueError(f'GunShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')
        except TypeError:
            pass

        gs = self.gun_tem.Shift

        if x is not None:
            gs.X = x
        if y is not None:
            gs.Y = y

        self.gun_tem.Shift = gs

    def getGunTilt(self):
        """The gun tilt alignment values. Range from -1.0 to +1.0 in x and y directions (logical units). 
           The beamblanker changes the gun tilt. Therefore changing the gun tilt alignment is blocked as long as 
           the beamblanker is active. 150ms per call"""
        x = self.gun_tem.Tilt.X
        y = self.gun_tem.Tilt.Y
        return x, y

    def setGunTilt(self, x=None, y=None):
        """The gun tilt alignment values. Range from -1.0 to +1.0 in x and y directions (logical units). 
           The beamblanker changes the gun tilt. Therefore changing the gun tilt alignment is blocked as long as 
           the beamblanker is active. 150ms per call"""
        try:
            if abs(x) > 1 or abs(y) > 1:
                raise FEIValueError(f'GunTilt x/y must be a floating number between -1 an 1. Input: x={x}, y={y}')
        except TypeError:
            pass

        gt = self.gun_tem.Tilt

        if x is not None:
            gt.X = x
        if y is not None:
            gt.Y = y

        self.gun_tem.Tilt = gt

    def getBeamShift(self):
        """User Shift. Beam shift relative to the origin stored at alignment time. Units: nm. 6ms per call"""
        '1.19 ms in communication. Super fast!'
        if USETOM:
            x = self.illu_tom.BeamShift.X * 1e9
            y = self.illu_tom.BeamShift.Y * 1e9
        else:
            x = self.illu_tem.Shift.X * 1e9
            y = self.illu_tem.Shift.Y * 1e9
        return x, y

    def setBeamShift(self, x=None, y=None):
        """User Shift. Beam shift relative to the origin stored at alignment time. Units: nm. 10ms per call"""
        if USETOM:
            bs = self.illu_tom.BeamShift
            if x is not None:
                bs.X = x * 1e-9
            if y is not None:
                bs.Y = y * 1e-9
            self.illu_tom.Shift = bs
        else:
            bs = self.illu_tem.Shift
            if x is not None:
                bs.X = x * 1e-9
            if y is not None:
                bs.Y = y * 1e-9
            self.illu_tem.Shift = bs

    def getBeamAlignShift(self):
        """Align Shift. I suppose the units is unknown."""
        x = self.illu_tom.BeamAlignShift.X * 1e9
        y = self.illu_tom.BeamAlignShift.Y * 1e9
        return x, y

    def setBeamAlignShift(self, x=None, y=None):
        """Align Shift. I suppose the units is unknown."""
        bs = self.illu_tom.BeamAlignShift

        if x is not None:
            bs.X = x * 1e-9
        if y is not None:
            bs.Y = y * 1e-9
        self.illu_tom.BeamAlignShift = bs

    def getBeamShiftCalibration(self):
        """Not sure what it does. I suppose the units is unknown."""
        bs = self.illu_tom.BeamShiftCalibration
        return bs.X, bs.Y

    def setBeamShiftCalibration(self, x=None, y=None):
        """Not sure what it does. I suppose the units is unknown."""
        bs = self.illu_tom.BeamShiftCalibration

        if x is not None:
            bs.X = x * 1e-9
        if y is not None:
            bs.Y = y * 1e-9
        self.illu_tom.BeamShiftCalibration = bs

    def getBeamShiftPhysical(self):
        """Not sure what it does. I suppose the units is unknown."""
        bs = self.illu_tom.BeamShiftPhysical
        return bs.X, bs.Y

    def setBeamShiftPhysical(self, x=None, y=None):
        """Not sure what it does. I suppose the units is unknown."""
        bs = self.illu_tom.BeamShiftPhysical

        if x is not None:
            bs.X = x * 1e-9
        if y is not None:
            bs.Y = y * 1e-9
        self.illu_tom.BeamShiftPhysical = bs

    def getBeamTilt(self):
        """rotation center in FEI. 5ms per call"""
        if USETOM:
            x = self.illu_tom.BeamAlignmentTilt.X *180 / pi
            y = self.illu_tom.BeamAlignmentTilt.Y *180 / pi
        else:
            x = self.illu_tem.RotationCenter.X *180 / pi
            y = self.illu_tem.RotationCenter.Y *180 / pi
        return x, y

    def setBeamTilt(self, x=None, y=None):
        """rotation center in FEI. 9.8ms per call"""
        if USETOM:
            bt = self.illu_tom.BeamAlignmentTilt
            if x is not None:
                bt.X = x * pi / 180
            if y is not None:
                bt.Y = y * pi / 180
            self.illu_tom.BeamAlignmentTilt = bt
        else:
            bt = self.illu_tem.RotationCenter
            if x is not None:
                bt.X = x * pi / 180
            if y is not None:
                bt.Y = y * pi / 180
            self.illu_tem.RotationCenter = bt
        
    def getImageShift1(self):
        """User image shift. 5ms per call
           The image shift with respect to the origin that is defined by alignment. Units: nm."""
        if USETOM:
            return self.proj_tom.ImageShift.X * 1e9, self.proj_tom.ImageShift.Y * 1e9
        else:
            return self.proj_tem.ImageShift.X * 1e9, self.proj_tem.ImageShift.Y * 1e9

    def setImageShift1(self, x=None, y=None):
        """9.8ms per call
           The image shift with respect to the origin that is defined by alignment. Units: nm."""
        if USETOM:
            is1 = self.proj_tom.ImageShift
            if x is not None:
                is1.X = x * 1e-9
            if y is not None:
                is1.Y = y * 1e-9
            self.proj_tom.ImageShift = is1
        else:
            is1 = self.proj_tem.ImageShift
            if x is not None:
                is1.X = x * 1e-9
            if y is not None:
                is1.Y = y * 1e-9
            self.proj_tem.ImageShift = is1

    def getImageShift2(self):
        """image-beam shift. 5ms per call    def getImageBeamShift(self)?
           Image shift with respect to the origin that is defined by alignment. The apparent beam shift is compensated for, 
           without affecting the Shift-property of the Illumination-object. Units: nm.
           Attention: Avoid intermixing ImageShift and ImageBeamShift, otherwise it would mess up the beam shift 
           (=Illumination.Shift). If you want to use both alternately, then reset the other to zero first."""
        if USETOM:
            return self.proj_tom.ImageBeamShift.X * 1e9, self.proj_tom.ImageBeamShift.Y * 1e9
        else:
            return self.proj_tem.ImageBeamShift.X * 1e9, self.proj_tem.ImageBeamShift.Y * 1e9

    def setImageShift2(self, x=None, y=None):
        """9.8ms per call     def setImageBeamShift(self, x, y)?
           Image shift with respect to the origin that is defined by alignment. The apparent beam shift is compensated for, 
           without affecting the Shift-property of the Illumination-object. Units: nm.
           Attention: Avoid intermixing ImageShift and ImageBeamShift, otherwise it would mess up the beam shift 
           (=Illumination.Shift). If you want to use both alternately, then reset the other to zero first."""
        if USETOM:
            is1 = self.proj_tom.ImageBeamShift
            if x is not None:
                is1.X = x / 1e9
            if y is not None:
                is1.Y = y / 1e9
            self.proj_tom.ImageBeamShift = is1
        else:
            is1 = self.proj_tem.ImageBeamShift
            if x is not None:
                is1.X = x / 1e9
            if y is not None:
                is1.Y = y / 1e9
            self.proj_tem.ImageBeamShift = is1
        
    def getImageBeamTilt(self):
        """Beam tilt with respect to the origin that is defined by alignment (rotation center). The resulting 
           diffraction shift is compensated for, without affecting the DiffractionShift-property of the Projection 
           object. For proper operation requires calibration (alignment) of the Beam Tilt - Diffraction Shift 
           (for more information, see a0050100.htm on the TEM software installation CD under privada\beamtiltdiffshift). Units: radians.
           Attention: Avoid intermixing Tilt (of the beam in Illumination) and ImageBeamTilt. If you want to 
           use both alternately, then reset the other to zero first."""
        if USETOM:
            return self.proj_tom.ImageBeamTilt.X * 1e9, self.proj_tom.ImageBeamTilt.Y * 1e9
        else:
            return self.proj_tem.ImageBeamTilt.X * 1e9, self.proj_tem.ImageBeamTilt.Y * 1e9

    def setImageBeamTilt(self, x=None, y=None):
        """Beam tilt with respect to the origin that is defined by alignment (rotation center). The resulting 
           diffraction shift is compensated for, without affecting the DiffractionShift-property of the Projection 
           object. For proper operation requires calibration (alignment) of the Beam Tilt - Diffraction Shift 
           (for more information, see a0050100.htm on the TEM software installation CD under privada\beamtiltdiffshift). Units: radians.
           Attention: Avoid intermixing Tilt (of the beam in Illumination) and ImageBeamTilt. If you want to 
           use both alternately, then reset the other to zero first."""
        if USETOM:
            is1 = self.proj_tom.ImageBeamTilt
            if x is not None:
                is1.X = x / 1e9
            if y is not None:
                is1.Y = y / 1e9
            self.proj_tom.ImageBeamTilt = is1
        else:
            is1 = self.proj_tem.ImageBeamTilt
            if x is not None:
                is1.X = x / 1e9
            if y is not None:
                is1.Y = y / 1e9
            self.proj_tem.ImageBeamTilt = is1

    def isStageMoving(self):
        """Check if sample stage is moving"""
        if self.getStageStatus() == 'Ready':
            return False
        elif self.getStageStatus() == 'Going':
            return True
        else:
            raise FEIValueError('The microscope is not ready for checking stage movement')

    def getStageStatus(self):
        """stReady    The stage is ready (capable to perform all position management functions)
        stDisabled    The stage has been disabled either by the user or due to an error.
        stNotReady    The stage is not (yet) ready to perform position management functions for reasons other than already accounted for by the other constants
        stGoing       The stage is performing a ‘GoTo()’
        stMoving      The stage is performing a ‘MoveTo()’
        stWobbling    The stage is wobbling"""
        dct = {0: 'Ready', 1: 'Disabled', 2: 'NotReady', 
               3: 'Going', 4: 'Moving', 5: 'Wobbling'}
        if USETOM:
            return dct[self.stage_tom.Status]
        else:
            return dct[self.stage_tem.Status]

    def stopStage(self):
        """Stop the sample stage, not working for FEI microscope now"""
        # self.stage.Status = self.goniostopped
        print("Unable to stop the stage for FEI microscope")
        return -1

    def getFunctionMode(self):
        """read only! {1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'} Submode of the projection system (either LM, Mi, ..., 
           LAD or D). The imaging submode can change, when the magnification is changed."""
        if USETOM:
            mode = self.proj_tom.Submode
        else:
            mode = self.proj_tem.Submode
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
        return self.stage_tem.Holder

    def getDiffFocus(self, confirm_mode=True):
        if confirm_mode and (self.getFunctionMode() not in ("LAD", "D")):
            raise FEIValueError("Must be in 'LAD' or 'D' mode to get DiffFocus")
        if USETOM:
            return self.proj_tom.Defocus * 1e9
        else:
            return self.proj_tem.Defocus * 1e9

    def setDiffFocus(self, value, confirm_mode=True):
        if confirm_mode and (self.getFunctionMode() not in ("LAD", "D")):
            raise FEIValueError("Must be in 'LAD' or 'D' mode to get DiffFocus")
        if USETOM:
            self.proj_tom.Defocus = value * 1e-9
        else:
            self.proj_tem.Defocus = value * 1e-9

    def getDefocus(self, confirm_mode=True):
        """1.2ms per call. 
           Defocus value of the currently active mode. Changing ‘Defocus’ will also change ‘Focus’ 
           and vice versa. ‘Defocus’ is in physical units (meters) and measured with respect to a origin that can 
           be set by using ‘ResetDefocus()’."""
        if confirm_mode and (self.getFunctionMode() not in ('LM','Mi','SA','Mh')):
            raise FEIValueError("Must be in ('LM','Mi','SA','Mh') mode to get Defocus")
        if USETOM:
            return self.proj_tom.Defocus * 1e9
        else:
            return self.proj_tem.Defocus * 1e9

    def setDefocus(self, value, confirm_mode=True):
        """defocus value in unit m. 6ms per call. 
           Defocus value of the currently active mode. Changing ‘Defocus’ will also change ‘Focus’ 
           and vice versa. ‘Defocus’ is in physical units (meters) and measured with respect to a origin that can 
           be set by using ‘ResetDefocus()’."""
        if confirm_mode and (self.getFunctionMode() not in ('LM','Mi','SA','Mh')):
            raise FEIValueError("Must be in ('LM','Mi','SA','Mh') mode to get Defocus")
        if USETOM:
            self.proj_tom.Defocus = value * 1e-9
        else:
            self.proj_tem.Defocus = value * 1e-9

    def ResetDefocus(self):
        """Resets the current ‘Defocus’ to 0 nm. This does not change the ‘Focus’ value (the focussing lens current). 
           Use it when the image is properly focussed to adjust the ‘Defocus’ scale."""
        self.proj_tem.ResetDefocus()

    def getFocus(self):
        """1.2ms per call
           Focus setting of the currently active mode. Range: maximum between -1.0  (= underfocussed) and 
           1.0 (= overfocussed), but the exact limits are mode dependent and may be a lot lower."""
        if USETOM:
            return self.proj_tom.Focus
        else:
            return self.proj_tem.Focus

    def setFocus(self, value):
        """6.5ms per call
           Focus setting of the currently active mode. Range: maximum between -1.0  (= underfocussed) and 
           1.0 (= overfocussed), but the exact limits are mode dependent and may be a lot lower."""
        if value < -1 or value > 1:
            raise FEIValueError("Value must within -1 and 1")
        if USETOM:
            self.proj_tom.Focus = value
        else:
            self.proj_tem.Focus = value

    def getApertureSize(self, aperture):
        '''Not sure about the unit'''
        if aperture == 'C1':
            return self.illu_tom.C1ApertureSize
        elif aperture == 'C2':
            return self.illu_tom.C2ApertureSize
        else:
            raise FEIValueError("Aperture must be specified as 'C1' or 'C2'.")

    def getScreenCurrent(self):
        """return screen current in nA."""
        if USETOM:
            return self.tom.Screen.Current * 1e9
        else:
            return self.tem.Camera.ScreenCurrent * 1e9

    def isfocusscreenin(self):
        if USETOM:
            return self.tom.Screen.IsFocusScreenIn
        else:
            return self.tem.Camera.IsSmallScreenDown

    def getScreenPosition(self):
        """return value: 'up' or 'down'"""
        if USETOM:
            dic = {0: 'down', 1: 'up'}
            return dic[self.tom.Screen.Position]
        else:
            dic = {0: 'unknown', 1: 'up', 2: 'down'}
            return dic[self.tem.Camera.MainScreen]

    def setScreenPosition(self, value):
        """value = 'up' or 'down'"""
        if USETOM:
            dic = {'down': 0, 'up': 1}
            self.tom.Screen.SetScreenPosition(dic[value])
        else:
            dic = {'unknown': 1, 'up': 2, 'down': 3}
            self.tem.Camera.MainScreen(dic[value])

    def getDiffShift(self):
        """user diff shift, encoded in a different way than system status on TEM USER INTERFACE: 
           180/pi*number = number on TEM USER INTERFACE. Not exactly though, close enough
           The diffraction pattern shift with respect to the origin that is defined by alignment. Units: radians."""
        return 180 / pi * self.proj_tem.DiffractionShift.X, 180 / pi * self.proj_tem.DiffractionShift.Y

    def setDiffShift(self, x=None, y=None):
        """user diff shift, encoded in a different way than system status on TEM USER INTERFACE: 
           180/pi*number = number on TEM USER INTERFACE. Not exactly though, close enough
           The diffraction pattern shift with respect to the origin that is defined by alignment. Units: degree."""
        ds1 = self.proj_tem.DiffractionShift

        if x is not None:
            ds1.X = x / 180 * pi
        if y is not None:
            ds1.Y = y / 180 * pi

        self.proj_tem.DiffractionShift = ds1

    def releaseConnection(self):
        comtypes.CoUninitialize()
        logger.info('Connection to microscope released')
        print('Connection to microscope released')

    def isBeamBlanked(self):
        """to be tested."""
        return self.illu_tem.BeamBlanked

    def setBeamBlank(self, value):
        """True/False or 1/0."""
        self.illu_tem.BeamBlanked = value

    def setBeamUnblank(self):
        self.illu_tem.BeamBlanked = 0

    def getCondenserLensStigmator(self):
        if USETOM:
            return self.illu_tom.CondenserStigmator.X, self.illu_tom.CondenserStigmator.Y
        else:
            return self.illu_tem.CondenserStigmator.X, self.illu_tem.CondenserStigmator.Y

    def setCondenserLensStigmator(self, x=None, y=None):
        try:
            if abs(x) > 1 or abs(y) > 1:
                raise FEIValueError('Invalid condenser lens stigmator setting: can only be float numbers between -1 and 1.')
        except TypeError:
            pass

        if USETOM:
            ds1 = self.illu_tom.CondenserStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tom.CondenserStigmator = ds1
        else:
            ds1 = self.illu_tem.CondenserStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tem.CondenserStigmator = ds1

    def getIntermediateLensStigmator(self):
        """diffraction stigmator."""
        if USETOM:
            return self.proj_tom.DiffractionStigmator.X, self.proj_tom.DiffractionStigmator.Y
        else:
            return self.proj_tem.DiffractionStigmator.X, self.proj_tem.DiffractionStigmator.Y

    def setIntermediateLensStigmator(self, x=None, y=None):
        try:
            if abs(x) > 1 or abs(y) > 1:
                raise FEIValueError('Invalid intermediate lens stigmator setting: can only be float numbers between -1 and 1.')
        except TypeError:
            pass

        if USETOM:
            ds1 = self.proj_tom.DiffractionStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.proj_tom.DiffractionStigmator = ds1
        else:
            ds1 = self.proj_tem.DiffractionStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.proj_tem.DiffractionStigmator = ds1

    def getObjectiveLensStigmator(self):
        if USETOM:
            return self.proj_tom.ObjectiveStigmator.X, self.proj_tom.ObjectiveStigmator.Y
        else:
            return self.proj_tem.ObjectiveStigmator.X, self.proj_tem.ObjectiveStigmator.Y

    def setObjectiveLensStigmator(self, x=None, y=None):
        try:
            if abs(x) > 1 or abs(y) > 1:
                raise FEIValueError('Invalid objective lens stigmator setting: can only be float numbers between -1 and 1.')
        except TypeError:
            pass

        if USETOM:
            ds1 = self.proj_tom.ObjectiveStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.proj_tom.ObjectiveStigmator = ds1
        else:
            ds1 = self.proj_tem.ObjectiveStigmator
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.proj_tem.ObjectiveStigmator = ds1

    def getSpotSize(self):
        """The spot size index (usually ranging from 1 to 11). Adjust C1 current. 220ms per call."""
        if USETOM:
            return self.illu_tom.SpotsizeIndex
        else:
            return self.illu_tem.SpotsizeIndex

    def setSpotSize(self, value):
        """The spot size index (usually ranging from 1 to 11). Adjust C1 current. 224ms per call."""
        if value < 1 or value > 11:
            raise FEIValueError('The range of spot size is from 1 to 11.')
        if USETOM:
            self.illu_tom.SpotsizeIndex = value
        else:
            self.illu_tem.SpotsizeIndex = value

    def getMagnificationIndex(self):
        """"""
        if USETOM:
            if self.getProjectionMode() == 'imaging':
                ind = self.proj_tom.MagnificationIndex
                return ind
            else:
                ind = self.proj_tom.CameraLengthIndex
                return ind
        else:
            if self.getProjectionMode() == 'imaging':
                ind = self.proj_tem.MagnificationIndex
                return ind
            else:
                ind = self.proj_tem.CameraLengthIndex
                return ind

    def getMagnificationAbsoluteIndex(self) -> int:
        raise NotImplementedError

    def setMagnificationIndex(self, index):
        if USETOM:
            if self.getProjectionMode() == 'imaging':
                self.proj_tom.MagnificationIndex = index
            else:
                self.proj_tom.CameraLengthIndex = index
        else:
            if self.getProjectionMode() == 'imaging':
                self.proj_tem.MagnificationIndex = index
            else:
                self.proj_tem.CameraLengthIndex = index
        
    def getBrightness(self):
        """Intensity value of the current mode (typically ranging from 0 to 1.0, 
           but on some microscopes the minimum may be higher"""
        if USETOM:
            return self.illu_tom.Intensity
        else:
            return self.illu_tem.Intensity

    def setBrightness(self, value):
        """Intensity value of the current mode (typically ranging from 0 to 1.0, 
           but on some microscopes the minimum may be higher"""
        if value < 0 or value > 1:
            raise FEIValueError('The range of intensity of probe is from 0 to 1.')
        if USETOM:
            self.illu_tom.Intensity = value
        else:
            self.illu_tem.Intensity = value

    def getIlluminatedArea(self):
        """return diameter in nm. The size of the illuminated area. Accessible only in Parallel mode."""
        if USETOM:
            return self.illu_tom.IlluminatedAreaDiameter * 1e9
        else:
            return self.illu_tem.IlluminatedArea * 1e9

    def setIlluminatedArea(self, value):
        """return diameter in nm. The size of the illuminated area. Accessible only in Parallel mode."""
        if USETOM:
            self.illu_tom.IlluminatedAreaDiameter = value * 1e-9
        else:
            self.illu_tem.IlluminatedArea = value * 1e-9

    def isStemAvailable(self):
        """Returns whether themicroscope has a STEM system or not."""
        if USETOM:
            return self.illu_tom.StemAvailable
        else:
            return self.illu_tem.InstrumentModeControl.StemAvailable

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
        dct = {0: 'micro', 1: 'nano'}
        if USETOM:
            return dct[self.illu_tom.ProbeMode]
        else:
            return dct[self.illu_tem.Mode]

    def setProbeMode(self, value):
        """Mode of the illumination system (either nanoprobe or microprobe). 
           (Nearly) no effect for low magnifications (LM)."""
        dct = {'micro': 0, 'nano': 1}
        if value != 'micro' or value != 'nano':
            raise FEIValueError('The probe mode must be \'micro\' or \'nano\'.')
        if USETOM:
            self.illu_tom.ProbeMode = value
        else:
            self.illu_tem.Mode = value

    def isIntensityZoomEnabled(self):
        """Activates/deactivates the intensity zoom in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        if USETOM:
            return self.illu_tom.IntensityZoomEnabled
        else:
            return self.illu_tem.IntensityZoomEnabled

    def setIntensityZoomEnabled(self, value: bool):
        """Activates/deactivates the intensity zoom in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        if USETOM:
            self.illu_tom.IntensityZoomEnabled = value
        else:
            self.illu_tem.IntensityZoomEnabled = value

    def isIntensityLimitEnabled(self):
        """Activates/deactivates the intensity limit in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        if USETOM:
            return self.illu_tom.IntensityLimitEnabled
        else:
            return self.illu_tem.IntensityLimitEnabled

    def setIntensityLimitEnabled(self, value: bool):
        """Activates/deactivates the intensity limit in the current mode. This function only works, 
           when it has been initialized by means of the microscope alignments (it needs to know at which 
           intensity setting the spot is focused)."""
        if USETOM:
            self.illu_tom.IntensityLimitEnabled = value
        else:
            self.illu_tem.IntensityLimitEnabled = value

    def getProbeShift(self):
        """Beam shift relative to the origin stored at alignment time. Units: nm."""
        if USETOM:
            return self.illu_tom.Shift.X * 1e9, self.illu_tom.Shift.Y * 1e9
        else:
            return self.illu_tem.Shift.X * 1e9, self.illu_tem.Shift.Y * 1e9

    def setProbeShift(self, x=None, y=None):
        """Beam shift relative to the origin stored at alignment time. Units: nm."""
        if USETOM:
            ds1 = self.illu_tom.Shift
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tom.Shift = ds1
        else:
            ds1 = self.illu_tem.Shift
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tem.Shift = ds1

    def getDarkFieldTilt(self):
        """Dark field beam tilt relative to the origin stored at alignment time. Only operational, 
           if dark field mode is active. Units: degree, either in Cartesian (x,y) or polar (conical) tilt angles. 
           The accuracy of the beam tilt physical units depends on a calibration of the tilt angles"""
        if USETOM:
            return self.illu_tom.Tilt.X / pi * 180, self.illu_tom.Tilt.Y / pi * 180
        else:
            return self.illu_tem.Tilt.X / pi * 180, self.illu_tem.Tilt.Y / pi * 180

    def setDarkFieldTilt(self, x=None, y=None):
        """Dark field beam tilt relative to the origin stored at alignment time. Only operational, 
           if dark field mode is active. Units: degree, either in Cartesian (x,y) or polar (conical) tilt angles. 
           The accuracy of the beam tilt physical units depends on a calibration of the tilt angles"""
        if USETOM:
            ds1 = self.illu_tom.Tilt
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tom.Tilt = ds1
        else:
            ds1 = self.illu_tem.Tilt
            if x is not None:
                ds1.X = x
            if y is not None:
                ds1.Y = y
            self.illu_tem.Tilt = ds1

    def getRotationCenter(self):
        """Corresponds to the alignment beam tilt value. Units are degree, range is ± 0.2-0.3rad. 
           Do not confuse RotationCenter with dark field (Tilt). Be aware that this is an alignment function."""
        return self.illu_tem.RotationCenter.X / pi * 180, self.illu_tem.RotationCenter.Y / pi * 180

    def setRotationCenter(self, x=None, y=None):
        """Corresponds to the alignment beam tilt value. Units are degree, range is ± 0.2-0.3rad. 
           Do not confuse RotationCenter with dark field (Tilt). Be aware that this is an alignment function."""
        try:
            if abs(x) > 0.3 or abs(y) > 0.3:
                raise FEIValueError('Invalid rotation center setting: can only be float numbers between -0.3 and 0.3.')
        except TypeError:
            pass

        ds1 = self.illu_tem.RotationCenter
        if x is not None:
            ds1.X = x
        if y is not None:
            ds1.Y = y
        self.illu_tem.RotationCenter = ds1

    def getStemMagnification(self):
        """The magnification value in STEM mode. You can change the magnification only in discrete steps 
           (the same as on the microscope). If you specify a value that is not one of those steps, the scripting 
           will select the nearest available step."""
        if USETOM:
            return self.tom.STEM.Magnification
        else:
            return self.illu_tem.StemMagnification

    def setStemMagnification(self, value):
        """The magnification value in STEM mode. You can change the magnification only in discrete steps 
           (the same as on the microscope). If you specify a value that is not one of those steps, the scripting 
           will select the nearest available step."""
        if USETOM:
            self.tom.STEM.Magnification = value
        else:
            self.illu_tem.StemMagnification = value

    def getStemRotation(self):
        """The STEM rotation angle (in radians)."""
        if USETOM:
            return self.tom.STEM.Rotation / pi * 180
        else:
            return self.illu_tem.StemRotation / pi * 180

    def setStemRotation(self, value):
        """The STEM rotation angle (in radians)."""
        value = value * pi / 180
        if USETOM:
            self.tom.STEM.Rotation = value
        else:
            self.illu_tem.StemRotation = value

    def getProbeDefocus(self):
        """The amount of probe defocus (in nm). Accessible only in Probe mode."""
        return self.illu_tem.ProbeDefocus * 1e9

    def setProbeDefocus(self, value):
        """The amount of probe defocus (in nm). Accessible only in Probe mode."""
        self.illu_tem.ProbeDefocus = value / 1e9

    def getConvergenceAngle(self):
        """The convergence angle (in radians). Accessible only in Probe mode."""
        if USETOM:
            return self.illu_tom.ProbConvergenceAngle / pi * 180
        else:
            return self.illu_tem.ConvergenceAngle / pi * 180

    def setConvergenceAngle(self, value):
        """The convergence angle (in radians). Accessible only in Probe mode."""
        if USETOM:
            self.illu_tom.ProbConvergenceAngle = value / 180 * pi
        else:
            self.illu_tem.ConvergenceAngle = value / 180 * pi

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
        return self.illu_tem.Normalize(index)

    def NormalizeProjection(self):
        """Normalizes the objective lens or the projector lenses, dependent on the choice of ‘Norm’.
           10: Objective    Normalize objective lens
           11: Projector    Normalize Diffraction, Intermediate, P1 and P2 lenses
           12: All          Normalize objective, diffraction, intermediate, P1 and P2 lenses"""
        if index not in (10, 11, 12):
            raise FEIValueError('Invalid condenser normalize setting: index should between 10 and 12.')
        return self.proj_tem.Normalize(index)

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
        if USETOM:
            dct = {0: 'imaging', 1: 'diffraction'}
            return dct[self.proj_tom.Mode]
        else:
            dct = {1: 'imaging', 2: 'diffraction'}
            return dct[self.proj_tem.Mode]

    def setProjectionMode(self, value):
        """Main mode of the projection system (either imaging or diffraction).
           1: Imaging          Projector in imaging mode
           2: Diffraction      Projector in diffraction  mode"""
        try:
            if USETOM:
                dct = {'imaging': 0, 'diffraction': 1}
                self.proj_tom.Mode = dct[value]
            else:
                dct = {'imaging': 1, 'diffraction': 2}
                self.proj_tem.Mode = dct[value]
        except KeyError:
            raise FEIValueError('Input must be \'imaging\' or \'diffraction\'') 

    def getLensProgram(self):
        """The lens program setting (currently EFTEM or Regular). This is the third property to 
           characterize a mode of the projection system.
           1: Regular        The default lens program
           2: EFTEM          Lens program used for EFTEM (energy-filtered TEM)"""
        if USETOM:
            dct = {1: 'regular', 2: 'EFTEM'}
            return dct[self.proj_tom.LensProgram]
        else:
            dct = {1: 'regular', 2: 'EFTEM'}
            return dct[self.proj_tem.LensProgram]

    def setLensProgram(self, value):
        """The lens program setting (currently EFTEM or Regular). This is the third property to 
           characterize a mode of the projection system.
           1: Regular        The default lens program
           2: EFTEM          Lens program used for EFTEM (energy-filtered TEM)"""
        try:
            if USETOM:
                dct = {'regular': 1, 'EFTEM': 2}
                self.proj_tom.LensProgram = dct[value]
            else:
                dct = {'regular': 1, 'EFTEM': 2}
                self.proj_tem.LensProgram = dct[value]
        except KeyError:
            raise FEIValueError('Input must be \'regular\' or \'EFTEM\'') 

    def getImageRotation(self):
        """The rotation of the image or diffraction pattern on the fluorescent screen 
           with respect to the specimen. Units: radians."""
        return self.proj_tem.ImageRotation

    def getDetectorShift(self):
        """Sets the extra shift that projects the image/diffraction pattern onto a detector.
           0: pdsOnAxis       Does not shift the image/diffraction pattern
           1: pdsNearAxis     Shifts the image/diffraction pattern onto a near-axis detector/camera
           2: pdsOffAxis      Shifts the image/diffraction pattern onto an off-axis detector/camera"""
        return self.proj_tem.DetectorShift

    def setDetectorShift(self, value):
        """Sets the extra shift that projects the image/diffraction pattern onto a detector.
           0: pdsOnAxis       Does not shift the image/diffraction pattern
           1: pdsNearAxis     Shifts the image/diffraction pattern onto a near-axis detector/camera
           2: pdsOffAxis      Shifts the image/diffraction pattern onto an off-axis detector/camera"""
        self.proj_tem.DetectorShift = value

    def getDetectorShiftMode(self):
        """This property determines, whether the chosen DetectorShift is changed when the fluorescent screen is moved down.
           0: pdsmAutoIgnore       The 'DetectorShift' is set to zero, when the fluorescent screen moves down. 
                                When it moves up again, what happens depends on what detector TEM thinks is 
                                currently selected. Take care!.
           1: pdsmManual           The detectorshift is applied as it is chosen in the 'DetectorShift'-property
           2: pdsmAlignment        The detector shift is (temporarily) controlled by an active alignment procedure. 
                                Clients cannot set this value. Clients cannot set the 'DetectorShiftMode' to another 
                                value either, if this is the current value. They have to wait until the alignment is finished."""
        return self.proj_tem.DetectorShiftMode

    def setDetectorShiftMode(self, value):
        """This property determines, whether the chosen DetectorShift is changed when the fluorescent screen is moved down.
           0: pdsmAutoIgnore       The 'DetectorShift' is set to zero, when the fluorescent screen moves down. 
                                When it moves up again, what happens depends on what detector TEM thinks is 
                                currently selected. Take care!.
           1: pdsmManual           The detectorshift is applied as it is chosen in the 'DetectorShift'-property
           2: pdsmAlignment        The detector shift is (temporarily) controlled by an active alignment procedure. 
                                Clients cannot set this value. Clients cannot set the 'DetectorShiftMode' to another 
                                value either, if this is the current value. They have to wait until the alignment is finished."""
        self.proj_tem.DetectorShiftMode = value 

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
        """The diffraction pattern shift with respect to the origin that is defined by alignment. Units: degree."""
        return self.proj_tem.DiffractionShift.X * 180 / pi, self.proj_tem.DiffractionShift.Y * 180 / pi

    def setDiffractionShift(self, x, y):
        """Parameter x and y are in degree. The diffraction pattern shift with respect to the origin that is 
           defined by alignment. Units: degree."""
        x = x * pi / 180
        y = y * pi / 180
        self.proj_tem.DiffractionShift.X = x 
        self.proj_tem.DiffractionShift.Y = y

    def getAll(self):
        """Same lens and deflector parameters as jeol to give an overview of the parameters"""
        raise NotImplementedError("This function needs to be reimplemented.")
        print('## lens3')
        print('CL1', self.lens3.GetCL1())  # condenser lens
        print('CL2', self.lens3.GetCL2())  # condenser lens
        print('CL3', self.lens3.GetCL3())  # brightness
        print('CM', self.lens3.GetCM())   # condenser mini lens
        print('FLc', self.lens3.GetFLc())  # ?? -> self.lens3.SetFLc()
        print('FLf', self.lens3.GetFLf())  # ?? -> self.lens3.SetFLf()
        print('FLcomp1', self.lens3.GetFLcomp1())  # ??, no setter
        print('FLcomp2', self.lens3.GetFLcomp2())  # ??, no setter
        print('IL1', self.lens3.GetIL1())  # diffraction focus, use SetDiffFocus in diffraction mode, SetILFocus in image mode
        print('IL2', self.lens3.GetIL2())  # intermediate lens, no setter
        print('IL3', self.lens3.GetIL3())  # intermediate lens, no setter
        print('IL4', self.lens3.GetIL4())  # intermediate lens, no setter
        print('OLc', self.lens3.GetOLc())  # objective focus coarse, SetOLc
        print('OLf', self.lens3.GetOLf())  # objective focus fine, SetOLf
        print('OM', self.lens3.GetOM())   # Objective mini lens
        print('OM2', self.lens3.GetOM2())  # Objective mini lens
        print('OM2Flag', self.lens3.GetOM2Flag())  # Objective mini lens 2 flag ??
        print('PL1', self.lens3.GetPL1())  # projector lens, SetPLFocus
        print('PL2', self.lens3.GetPL2())  # n/a
        print('PL3', self.lens3.GetPL3())  # n/a
        print()
        print('## def3')
        print('CLA1', self.def3.GetCLA1())  # beam shift
        print('CLA2', self.def3.GetCLA2())  # beam tilt
        print('CLs', self.def3.GetCLs())   # condenser lens stigmator
        print('FLA1', self.def3.GetFLA1())
        print('FLA2', self.def3.GetFLA2())
        print('FLs1', self.def3.GetFLs1())
        print('FLs2', self.def3.GetFLs2())
        print('GUNA1', self.def3.GetGUNA1())  # gunshift
        print('GUNA2', self.def3.GetGUNA2())  # guntilt
        print('ILs', self.def3.GetILs())     # intermediate lens stigmator
        print('IS1', self.def3.GetIS1())     # image shift 1
        print('IS2', self.def3.GetIS2())     # image shift 2
        print('OLs', self.def3.GetOLs())     # objective lens stigmator
        print('PLA', self.def3.GetPLA())     # projector lens alignment

    def test_timing(self):
        import time
        t0 = time.perf_counter()
        mode = self.getFunctionMode()
        dt = time.perf_counter() - t0
        print(f'Execution time for getFunctionMode: {dt*1000:.2f}ms')

        funcs = {
            'GunShift': self.getGunShift,
            'GunTilt': self.getGunTilt,
            'BeamShift': self.getBeamShift,
            'BeamTilt': self.getBeamTilt,
            'ImageShift1': self.getImageShift1,
            'ImageShift2': self.getImageShift2,
            'DiffShift': self.getDiffShift,
            'StagePosition': self.getStagePosition,
            'Magnification': self.getMagnification,
            'Brightness': self.getBrightness,
            'SpotSize': self.getSpotSize,
        }
        if mode in ('D', 'LAD'):
            funcs['DiffFocus'] = self.getDiffFocus
        else:
            funcs['ObjFocus'] = self.getDefocus

        for key in funcs.keys():
            t0 = time.perf_counter()
            funcs[key]()
            dt = time.perf_counter() - t0
            print(f'Execution time for {funcs[key].__name__}: {dt*1000:.2f}ms')

        funcs_set = {
            'GunShift': self.setGunShift,
            'GunTilt': self.setGunTilt,
            'BeamShift': self.setBeamShift,
            'BeamTilt': self.setBeamTilt,
            'ImageShift1': self.setImageShift1,
            'ImageShift2': self.setImageShift2,
            'DiffShift': self.setDiffShift,
            'StagePosition': self.setStagePosition,
        }

        for key in funcs_set.keys():
            t0 = time.perf_counter()
            funcs_set[key]()
            dt = time.perf_counter() - t0
            print(f'Execution time for {funcs_set[key].__name__}: {dt*1000:.2f}ms')
            