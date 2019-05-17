import comtypes.client
import atexit
import time
import random
import threading
from numpy import pi

import logging
logger = logging.getLogger(__name__)

from instamatic import config

"""
speed table (deg/s):
1.00: 21.14
0.90: 19.61
0.80: 18.34
0.70: 16.90
0.60: 14.85
0.50: 12.69
0.40: 10.62
0.30: 8.20
0.20: 5.66
0.10: 2.91
0.05: 1.48
0.04: 1.18
0.03: 0.888
0.02: 0.593
0.01: 0.297
"""

FUNCTION_MODES = {0:'LM', 1:'Mi', 2:'SA', 3:'Mh', 4:'LAD', 5:'D'}

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
    10 :380,
    11 :470,
    12 :600,
    13 :760,
    14 :950,
    15 :1200,
    16 :1550,
    17 :3400,
    18 :4400,
    19 :5600,
    20 :7200,
    21 :8800,
    22 :11500,
    23 :14500,
    24 :18500,
    25 :24000,
    26 :30000,
    27 :38000,
    28 :49000,
    29 :61000,
    30 :77000,
    31 :100000,
    32 :130000,
    33 :165000,
    34 :215000,
    35 :265000,
    36 :340000,
    37 :430000,
    38 :550000,
    39 :700000,
    40 :890000,
    41 :1150000,
    42 :1250000,
    43 :960000,
    44 :750000,
    45 :600000,
    46 :470000,
    47 :360000,
    48 :285000,
    49 :225000,
    50 :175000,
    51 :145000,
    52 :115000,
    53 :89000,
    54 :66000,
    55 :52000,
    56 :41000,
    57 :32000,
    58 :26000,
    59 :21000,
    60 :8300,
    61 :6200,
    62 :3100 }

CameraLengthMapping = {
    1:  34,
    2:  42,
    3:  53,
    4:  68,
    5:  90,
    6:  115,
    7:  140,
    8:  175,
    9:  215,
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

class FEIMicroscope(object):
    """docstring for FEI microscope"""
    def __init__(self, name = "fei"):
        super(FEIMicroscope, self).__init__()
        
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()
            
        print("FEI Themis Z initializing...")
        ## tem interfaces the GUN, stage obj etc but does not communicate with the Instrument objects
        self.tem = comtypes.client.CreateObject("TEMScripting.Instrument.1", comtypes.CLSCTX_ALL)
        ## tecnai does similar things as tem; the difference is not clear for now
        self.tecnai = comtypes.client.CreateObject("Tecnai.Instrument", comtypes.CLSCTX_ALL)
        ## tom interfaces the Instrument, Projection objects
        self.tom = comtypes.client.CreateObject("TEM.Instrument.1", comtypes.CLSCTX_ALL)
        
        ### TEM Status constants
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
                print("Waiting for microscope, t = {}s".format(t))
            if t > 30:
                raise RuntimeError("Cannot establish microscope connection (timeout).")

        logger.info("Microscope connection established")
        atexit.register(self.releaseConnection)

        self.name = name
        self.FUNCTION_MODES = FUNCTION_MODES

        self.FunctionMode_value = 0

        for mode in self.FUNCTION_MODES.values():
            attrname = f"range_{mode}"
            try:
                rng = getattr(config.microscope, attrname)
            except AttributeError:
                print(f"Warning: No magnfication ranges were found for mode `{mode}` in the config file")
            else:
                setattr(self, attrname, rng)
        
        self.goniostopped = self.stage.Status
        
        input("Please select the type of sample stage before moving on.\nPress <ENTER> to continue...")

        # self.Magnification_value = random.choice(self.MAGNIFICATIONS)
        #self.Magnification_value = 2500
        #self.Magnification_value_diff = 300

    def getHTValue(self):
        return self.tem.GUN.HTValue
    
    def setHTValue(self, htvalue):
        self.tem.GUN.HTValue = htvalue
        
    def getMagnification(self):
        if self.tom.Projection.Mode != 1:
            ind = self.proj.MagnificationIndex
            return MagnificationMapping[ind]
        else:
            ind = self.proj.CameraLengthIndex
            return CameraLengthMapping[ind]
    
    def setMagnification(self, value):
        """value has to be the index"""
        if self.tom.Projection.Mode != 1:
            ind = [key for key, v in MagnificationMapping.items() if v == value][0]
            try:
                self.proj.MagnificationIndex = ind
            except ValueError:
                pass
        else:
            ind = [key for key, v in CameraLengthMapping.items() if v == value][0]
            self.tom.Projection.CameraLengthIndex = ind
        
    def setStageSpeed(self, value):
        """Value be 0 - 1"""
        if value > 1 or value < 0:
            raise ValueError(f"setStageSpeed value must be between 0 and 1. Input: {value}")

        self.tom.Stage.Speed = value
        
    def getStageSpeed(self):
        return self.tom.Stage.Speed
        
    def getStagePosition(self):
        """return numbers in microns, angles in degs."""
        return self.stage.Position.X * 1e6, self.stage.Position.Y * 1e6, self.stage.Position.Z * 1e6, self.stage.Position.A / pi * 180, self.stage.Position.B / pi * 180
    
    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, wait = True, speed = 1):
        """x, y, z in the system are in unit of meters, angles in radians"""
        pos = self.stage.Position
        axis = 0
        
        if speed > 1 or speed < 0:
            raise ValueError(f"setStageSpeed value must be between 0 and 1. Input: {value}")
        
        self.tom.Stage.Speed = speed
        goniospeed = self.tom.Stage.Speed
        
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
        """x y can only be float numbers between -1 and 1"""
        gs = self.tem.GUN.Shift
        if abs(x) > 1 or abs(y) > 1:
            raise ValueError(f"GunShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}")
        
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
            raise ValueError(f"GunTilt x/y must be a floating number between -1 an 1. Input: x={x}, y={y}")
        
        if x is not None:
            gt.X = x
        if y is not None:
            gt.Y = y
            
        self.tecnai.Gun.Tilt = gt
        
    def getBeamAlignShift(self):
        """Align Shift"""
        x = self.tom.Illumination.BeamAlignShift.X
        y = self.tom.Illumination.BeamAlignShift.Y
        return x, y
    
    def setBeamAlignShift(self, x, y):
        """Align Shift"""
        bs = self.tom.Illumination.BeamAlignShift
        if abs(x) > 1 or abs(y) > 1:
            raise ValueError(f"BeamAlignShift x/y must be a floating number between -1 an 1. Input: x={x}, y={y}")
            
        if x is not None:
            bs.X = x
        if y is not None:
            bs.Y = y
        self.tom.Illumination.BeamAlignShift = bs
        
    def getBeamTilt(self):
        """rotation center in FEI"""
        x = self.tom.Illumination.BeamAlignmentTilt.X
        y = self.tom.Illumination.BeamAlignmentTilt.Y
        return x, y
    
    def setBeamTilt(self, x, y):
        """rotation center in FEI"""
        bt = self.tom.Illumination.BeamAlignmentTilt
        
        if x is not None:
            if abs(x) > 1:
                raise ValueError(f"BeamTilt x must be a floating number between -1 an 1. Input: x={x}")
            bt.X = x
        if y is not None:
            if abs(y) > 1:
               raise ValueError(f"BeamTilt y must be a floating number between -1 an 1. Input: y={y}")
            bt.Y = y
        self.tom.Illumination.BeamAlignmentTilt = bt

    def getImageShift1(self):
        """User image shift"""
        return self.tom.Projection.ImageShift.X, self.tom.Projection.ImageShift.Y

    def setImageShift1(self, x, y):
        is1 = self.tom.Projection.ImageShift
        if abs(x) > 1 or abs(y) > 1:
            raise ValueError(f"ImageShift1 x/y must be a floating number between -1 an 1. Input: x={x}, y={y}")
            
        if x is not None:
            is1.X = x
        if y is not None:
            is1.Y = y
        
        self.tom.Projection.ImageShift = is1

    def getImageShift2(self):
        return 0, 0

    def setImageShift2(self, x, y):
        return 0

    def isStageMoving(self):
        if self.stage.Status == 0:
            return False
        else:
            return True
    
    def stopStage(self):
        #self.stage.Status = self.goniostopped
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
                raise ValueError(f"Unrecognized function mode: {value}")
        self.FunctionMode_value = value
    
    def getHolderType(self):
        return self.stage.Holder
        
    """What is the relationship between defocus and focus?? Both are changing the defoc value"""
    def getDiffFocus(self):
        return self.tom.Projection.Defocus

    def setDiffFocus(self, value):
        """defocus value in unit m"""
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
             raise ValueError("aperture must be specified as 'C1' or 'C2'.")
         
    def getBeamShift(self):
        return self.tom.Illumination.BeamShift.X, self.tom.Illumination.BeamShift.Y
    
    def setBeamShift(self, x, y):
        us = self.tom.Illumination.BeamShift
        if x > 0 or y > 0 or x < -1 or y < -1:
            raise ValueError(f"BeamShift x/y must be a floating number between -1 an 0. Input: x={x}, y={y}")
            return
        
        if x is not None:
            us.X = x
            
        if y is not None:
            us.Y = y
        
        self.tom.Illumination.BeamShift = us
        
    def getDarkFieldTilt(self):
        return self.tom.Illumination.DarkfieldTilt.X, self.tom.Illumination.DarkfieldTilt.Y
    
    def setDarkFieldTilt(self, x, y):
        """does not set"""
        return 0
    
    def getScreenCurrent(self):
        """return screen current in nA"""
        return self.tom.Screen.Current * 1e9
    
    def isfocusscreenin(self):
        return self.tom.Screen.IsFocusScreenIn
    
    def getDiffShift(self):
        """To be tested"""
        if self.proj.Mode != 1:
            return (0, 0)
        
        return self.proj.DiffractionShift.X,self.proj.DiffractionShift.Y
        
    def setDiffShift(self, x, y):
        """To be tested"""
        ds = self.proj.DiffractionShift
        if x > 1 or y > 1 or x < -1 or y < -1:
            print("Invalid PLA setting: can only be float numbers between -1 and 0.")
            return
        
        if x is not None:
            ds.X = x
            
        if y is not None:
            ds.Y = y
        
        self.proj.DiffractionShift = ds

    def releaseConnection(self):
        comtypes.CoUninitialize()
        logger.info("Connection to microscope released")
        print("Connection to microscope released")

    def isBeamBlanked(self):
        """to be tested"""
        return self.tem.Illumination.BeamBlanked

    def setBeamBlank(self, value):
        self.tem.Illumination.BeamBlanked = value
    
    def setBeamUnblank(self):
        self.tem.Illumination.BeamBlanked = 0

    def getCondensorLensStigmator(self):
        return self.tom.Illumination.CondenserStigmator.X, self.tom.Illumination.CondenserStigmator.Y

    def setCondensorLensStigmator(self, x, y):
        self.tom.Illumination.CondenserStigmator.X = x
        self.tom.Illumination.CondenserStigmator.Y = y
        
    def getIntermediateLensStigmator(self):
        """diffraction stigmator"""
        return self.tom.Illumination.DiffractionStigmator.X, self.tom.Illumination.DiffractionStigmator.Y

    def setIntermediateLensStigmator(self, x, y):
        self.tom.Illumination.DiffractionStigmator.X = x
        self.tom.Illumination.DiffractionStigmator.Y = y

    def getObjectiveLensStigmator(self):
        return self.tom.Illumination.ObjectiveStigmator.X, self.tom.Illumination.ObjectiveStigmator.Y

    def setObjectiveLensStigmator(self, x, y):
        self.tom.Illumination.ObjectiveStigmator.X = x
        self.tom.Illumination.ObjectiveStigmator.Y = y

    def getSpotSize(self):
        """0-based indexing for GetSpotSize, add 1 for consistency"""
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

    def setMagnificationIndex(self, index):
        if self.tom.Projection.Mode != 1:
            self.proj.MagnificationIndex = index
        else:
            self.proj.CameraLengthIndex = index
    
    def getBrightness(self):
        """return diameter in microns"""
        return self.tom.Illumination.IlluminatedAreaDiameter * 1e6

    def setBrightness(self, value):
        self.tom.Illumination.IlluminatedAreaDiameter = value
        
    def getFunctionMode(self):
        """{0:'LM',1:'Mi',2:'SA',3:'Mh',4:'LAD',5:'D'}"""
        mode = self.tom.Projection.Mode
        if mode == 0:
            return "LM"
        elif mode == 1:
            return "LAD"
        else:
            return "Unknown"
        
    def setFunctionMode(self, m):
        if m == "diff":
            self.tom.Projection.Mode = 1
            print("Set to diffraction.")
        elif m == "mag1":
            self.tom.Projection.Mode = 0
            print("Set to imaging.")
            
