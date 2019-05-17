import comtypes.client
import atexit
import time
import random

import logging
logger = logging.getLogger(__name__)

from instamatic import config

FUNCTION_MODES = {0:'LM',1:'Mi',2:'SA',3:'Mh',4:'LAD',5:'D'}


class FEISimuMicroscope(object):
    """docstring for FEI microscope"""
    def __init__(self, name = "fei_simu"):
        super(FEISimuMicroscope, self).__init__()
        
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()
            
        print("BETA version of the FEI microscope interface for MMK/SU, can only be tested on MMK/bwang computer in room C564, MMK, SU")
        ## tem interfaces the GUN, stage obj etc but does not communicate with the Instrument objects
        self.tem = comtypes.client.CreateObject("TEMScripting.Instrument.1", comtypes.CLSCTX_ALL)
        ## tecnai does similar things as tem; the difference is not clear for now
        self.tecnai = comtypes.client.CreateObject("Tecnai.Instrument", comtypes.CLSCTX_ALL)
        ## tom interfaces the Instrument, Projection objects
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
        atexit.register(self.releaseConnection)

        self.name = name
        self.FUNCTION_MODES = FUNCTION_MODES

        self.FunctionMode_value = 0

        self.DiffractionFocus_value = random.randint(MIN, MAX)

        self.DiffractionShift_x = random.randint(MIN, MAX)
        self.DiffractionShift_y = random.randint(MIN, MAX)

        for mode in self.FUNCTION_MODES:
            attrname = f"range_{mode}"
            try:
                rng = getattr(config.microscope, attrname)
            except AttributeError:
                print(f"Warning: No magnfication ranges were found for mode `{mode}` in the config file")
            else:
                setattr(self, attrname, rng)

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
        """{1:'LM',2:'Mi',3:'SA',4:'Mh',5:'LAD',6:'D'}"""
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
        comtypes.CoUninitialize()
        logger.info("Connection to microscope released")
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
        ## TO BE CHECKED: does FEI tem have a screenposition object??
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
        ## returned value is the DIAMETER of the illuminated area
        return self.tom.Illumination.IlluminatedAreaDiameter

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
