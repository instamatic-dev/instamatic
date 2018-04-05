import comtypes.client
import time
import random

import logging
logger = logging.getLogger(__name__);

from instamatic import config
NTRLMAPPING = {
   "GUN1" : 0,
   "GUN2" : 1,
   "CLA1" : 2,
   "CLA2" : 3,
   "SHIFT" : 4,
   "TILT" : 5,
   "ANGLE" : 6,
   "CLS" : 7,
   "IS1" : 8,
   "IS2" : 9,
   "SPOT?" : 10,
   "PLA" : 11,
   "OLS" : 12,
   "ILS" : 13
}

FUNCTION_MODES = {0:'LM',1:'Mi',2:'SA',3:'Mh',4:'LAD',5:'D'}

# constants for Jeol Hex value
ZERO = 32768
MAX = 65535
MIN = 0

class FEIMicroscope_Simu(object):
    """docstring for FEI microscope"""
    def __init__(self, name = "fei_simu"):
        super(FEIMicroscope_Simu, self).__init__()
        
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()
            
        self.tem = comtypes.client.CreateObject("TEMScripting.Instrument.1", comtypes.CLSCTX_ALL)
        self.tecnai = comtypes.client.CreateObject("Tecnai.Instrument", comtypes.CLSCTX_ALL)
        self.tom = comtypes.client.CreateObject("TEM.Instrument.1", comtypes.CLSCTX_ALL)
        
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
        
        self.name = name
        self.FUNCTION_MODES = FUNCTION_MODES

        # self.FunctionMode_value = random.randint(0, 2)
        self.FunctionMode_value = 0

        self.DiffractionFocus_value = random.randint(MIN, MAX)

        self.DiffractionShift_x = random.randint(MIN, MAX)
        self.DiffractionShift_y = random.randint(MIN, MAX)

        self.name = name
        self.MAGNIFICATIONS      = config.microscope.specifications["MAGNIFICATIONS"]
        self.MAGNIFICATION_MODES = config.microscope.specifications["MAGNIFICATION_MODES"]
        self.CAMERALENGTHS       = config.microscope.specifications["CAMERALENGTHS"]

        self.NTRLMAPPING = NTRLMAPPING

        self.ZERO = ZERO
        self.MAX = MAX
        self.MIN = MIN

        # self.Magnification_value = random.choice(self.MAGNIFICATIONS)
        self.Magnification_value = 2500
        self.Magnification_value_diff = 300

        self.beamblank = False

        self.condensorlensstigmator_x = random.randint(MIN, MAX)
        self.condensorlensstigmator_y = random.randint(MIN, MAX)

        self.intermediatelensstigmator_x = random.randint(MIN, MAX)
        self.intermediatelensstigmator_y = random.randint(MIN, MAX)

        self.objectivelensstigmator_x = random.randint(MIN, MAX)
        self.objectivelensstigmator_y = random.randint(MIN, MAX)

        self.spotsize = 1

        self.screenposition_value = 'up'

        self.condensorlens1_value = random.randint(MIN, MAX)
        self.condensorlens2_value = random.randint(MIN, MAX)
        self.condensorminilens_value = random.randint(MIN, MAX)
        self.objectivelensecoarse_value = random.randint(MIN, MAX)
        self.objectivelensefine_value = random.randint(MIN, MAX)
        self.objectiveminilens_value = random.randint(MIN, MAX)
        
    def getHTValue(self):
        return self.tem.GUN.HTValue
    
    def setHTValue(self, htvalue):
        self.tem.GUN.HTValue = htvalue
        
    def getMagnification(self):
        return self.proj.Magnification
    
    def setMagnification(self, value):
        ## Apparently they categorize magnification values into 1,2,3,...
        try:
            self.proj.MagnificationIndex = value
        except ValueError:
            pass
        
        
    def getStagePosition(self):
        return self.stage.Position.X, self.stage.Position.Y, self.stage.Position.Z, self.stage.Position.A, self.stage.Position.B
    
    def getGunShift(self):
        x = self.tem.GUN.Shift.X
        y = self.tem.GUN.Shift.Y
        return x, y 
    
    def setGunShift(self, x, y):
        ## Does not really work in this case
        self.tem.GUN.Shift.X = x
        self.tem.GUN.Shift.Y = y
    
    def getGunTilt(self):
        x = self.tem.GUN.Tilt.X
        y = self.tem.GUN.Tilt.Y
        return x, y
    
    def setGunTilt(self, x, y):
        self.tem.GUN.Tilt.X = x
        self.tem.GUN.Tilt.Y = y
        
    def getBeamShift(self):
        x = self.tom.Illumination.BeamShiftPhysical.X
        y = self.tom.Illumination.BeamShiftPhysical.Y
        return x, y
    
    def setBeamShift(self, x, y):
        self.tom.Illumination.BeamShiftPhysical.X = x
        self.tom.Illumination.BeamShiftPhysical.Y = y
        
    def getBeamTilt(self):
        ## Not sure if beamalignmenttilt.x is the right thing to use
        x = self.tom.Illumination.BeamAlignmentTilt.X
        y = self.tom.Illumination.BeamAlignmentTilt.Y
        return x, y
    
    def setBeamTilt(self, x, y):
        ## Not sure if beamalignmenttilt.x is the right thing to use
        self.tom.Illumination.BeamAlignmentTilt.X = x
        self.tom.Illumination.BeamAlignmentTilt.Y = y

    def getImageShift1(self):
        return self.tom.Projection.ImageBeamShift.X, self.tom.Projection.ImageBeamShift.Y

    def setImageShift1(self, x, y):
        self.tom.Projection.ImageBeamShift.X = x
        self.tom.Projection.ImageBeamShift.Y = y

    ## FEI Does NOT have image shift 2?
    def getImageShift2(self):
        return 0, 0

    def setImageShift2(self, x, y):
        return 0

    def isStageMoving(self):
        return False

    def waitForStage(self, delay=0.1):
        while self.isStageMoving():
            time.sleep(delay)

    def setStageX(self, value):
        self.stage.Position.X = value

    def setStageY(self, value):
        self.stage.Position.Y = value

    def setStageZ(self, value):
        self.stage.Position.Z = value

    def setStageA(self, value):
        self.stage.Position.A = value

    def setStageB(self, value):
        self.stage.Position.B = value
        
    def setStageX_nw(self, value, wait = True):
        self.stage.Position.X = value
        if not wait:
            print("Not waiting for stage movement to be done.")

    def setStageY_nw(self, value, wait = True):
        self.stage.Position.Y = value
        if not wait:
            print("Not waiting for stage movement to be done.")

    def setStageZ_nw(self, value, wait = True):
        self.stage.Position.Z = value
        if not wait:
            print("Not waiting for stage movement to be done.")

    def setStageA_nw(self, value, wait = True):
        self.stage.Position.A = value
        if not wait:
            print("Not waiting for stage movement to be done.")

    def setStageB_nw(self, value, wait = True):
        self.stage.Position.B = value
        if not wait:
            print("Not waiting for stage movement to be done.")

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None):
        if z is not None:
            self.setStageZ(z)
        if a is not None:
            self.setStageA(a)
        if b is not None:
            self.setStageB(b)
        if x is not None:
            self.setStageX(x)
        if y is not None:
            self.setStageY(y)
            
    def setStagePosition_nw(self, x=None, y=None, z=None, a=None, b=None, wait=False):
        if z is not None:
            self.setStageZ_nw(z, wait)
        if a is not None:
            self.setStageA_nw(a, wait)
        if b is not None:
            self.setStageB_nw(b, wait)
        if x is not None:
            self.setStageX_nw(x, wait)
        if y is not None:
            self.setStageY_nw(y, wait)
            
    def stopStageMV(self):
        print("Goniometer stopped moving.")

    def getFunctionMode(self):
        """{1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'}"""
        mode = self.tom.Projection.Submode
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """???"""
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise ValueError("Unrecognized function mode: {}".format(value))
        self.FunctionMode_value = value

    def getDiffFocus(self):
        return self.tom.Projection.Defocus

    def setDiffFocus(self, value):
        """IC1"""
        self.tom.Projection.Defocus = value

    def resetDiffFocus(self):
        ## Will raise Attribute Error
        self.tom.Projection.ResetDefocus()
        
    def getDiffShift(self):
        return self.DiffractionShift_x, self.DiffractionShift_y

    def setDiffShift(self, x, y):
        self.DiffractionShift_x = x
        self.DiffractionShift_y = y

    def releaseConnection(self):
        print("Connection to microscope released")

    def isBeamBlanked(self, value):
        return self.beamblank

    def setBeamBlank(self, mode):
        """True/False or 1/0"""
        self.beamblank = mode

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

    def getScreenPosition(self):
        return self.screenposition_value

    def setScreenPosition(self, value):
        """value = 'up' or 'down'"""
        self.screenposition_value = value

    def getCondensorLens1(self):
        return self.condensorlens1_value

    def getCondensorLens2(self):
        return self.condensorlens2_value

    def getCondensorMiniLens(self):
        return self.condensorminilens_value

    def getObjectiveLenseCoarse(self):
        return self.objectivelensecoarse_value

    def getObjectiveLenseFine(self):
        return self.objectivelensefine_value
    
    def getObjectiveMiniLens(self):
        return self.objectiveminilens_value
    
    def getMagnificationIndex(self):
        try:
            value = self.getMagnification()
            return self.MAGNIFICATIONS.index(value)
        except ValueError:
            pass

    def setMagnificationIndex(self, index):
        value = self.MAGNIFICATIONS[index]
        self.setMagnification(value)
    
    def getBrightness(self):
        return self.tom.Illumination.IlluminatedAreaDiameter

    def setBrightness(self, value):
        self.tom.Illumination.IlluminatedAreaDiameter = value
        
    def getFunctionMode(self):
        """mag1, mag2, lowmag, samag, diff"""
        mode = self.FunctionMode_value
        return FUNCTION_MODES[mode]