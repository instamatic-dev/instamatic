from __future__ import print_function
from instamatic import config

import atexit
import comtypes.client
import time
import os

import logging
logger = logging.getLogger(__name__)

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

FUNCTION_MODES = ('mag1', 'mag2', 'lowmag', 'samag', 'diff')

# constants for Jeol Hex value
ZERO = 32768
MAX = 65535
MIN = 0

## get the direction of movement
# ctrl.tem.stage3.GetDirection()
# >>> (0, 1, 0, 0, 1, 0)

## control piezo stage
# ctrl.tem.stage3.SelDrvMode(1) -> on
# ctrl.tem.stage3.SelDrvMode(0) -> off
## when selected, do we have precise control over the stage position?
## Piezo stage seems to operate on a different level than standard XY

class JeolMicroscope(object):
    """docstring for microscope"""
    def __init__(self, name="jeol"):
        super(JeolMicroscope, self).__init__()
        
        # initial COM in multithread mode if not initialized otherwise
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()

        # get the JEOL COM library and create the TEM3 object
        temext = comtypes.client.GetModule(('{CE70FCE4-26D9-4BAB-9626-EC88DB7F6A0A}', 3, 0))
        self.tem3 = comtypes.client.CreateObject(temext.TEM3, comtypes.CLSCTX_ALL)
        
        # initialize each interface from the TEM3 object
        # self.apt3 = self.tem3.CreateApt3()
        # self.camera3 = self.tem3.CreateCamera3()
        # self.detector3 = self.tem3.CreateDetector3()
        # self.feg3 = self.tem3.CreateFEG3()
        # self.filter3 = self.tem3.CreateFilter3()
        # self.mds3 = self.tem3.CreateMDS3()
        self.screen2 = self.tem3.CreateScreen2()
        self.def3 = self.tem3.CreateDef3()
        self.eos3 = self.tem3.CreateEOS3()
        self.ht3 = self.tem3.CreateHT3()
        self.lens3 = self.tem3.CreateLens3()
        self.stage3 = self.tem3.CreateStage3()

        ## faster stage readout using gonio2
        # self.gonio2.GetPosition() -> get stage position, 78 ms
        # self.stage3.GetPos() -> 277 ms
        self.gonio2 = self.tem3.CreateGonio2()

        # wait for interface to activate
        t = 0
        while True:
            ht, result = self.ht3.GetHTValue()
            if result == 0:
                break
            time.sleep(1)
            t += 1
            if t > 3:
                print("Waiting for microscope, t = {}s".format(t))
            if t > 30:
                raise RuntimeError("Cannot establish microscope connection (timeout).")

        logger.info("Microscope connection established")
        atexit.register(self.releaseConnection)

        self._x_direction = 0
        self._y_direction = 0

        self.name = name
        self.MAGNIFICATIONS      = config.microscope.specifications["MAGNIFICATIONS"]
        self.MAGNIFICATION_MODES = config.microscope.specifications["MAGNIFICATION_MODES"]
        self.CAMERALENGTHS       = config.microscope.specifications["CAMERALENGTHS"]

        self.FUNCTION_MODES = FUNCTION_MODES
        self.NTRLMAPPING = NTRLMAPPING

        self.ZERO = ZERO
        self.MAX = MAX
        self.MIN = MIN

        self.VERIFY_STAGE_POSITION = False

    def __del__(self):
        comtypes.CoUninitialize()

    def setNeutral(self, *args):
        """Neutralize given deflectors"""
        for arg in args:
            if isinstance(arg, str):
                arg = self.NTRLMAPPING[arg]
            self.def3.setNTRL(arg)

    def getBrightness(self):
        value, result = self.lens3.GetCL3()
        return value

    def setBrightness(self, value):
        self.lens3.setCL3(value)

    def getMagnification(self):
        value, unit_str, label_str, result = self.eos3.GetMagValue()
        return value

    def setMagnification(self, value):
        current_mode = self.getFunctionMode()
        
        if current_mode == "diff":
            if value not in self.CAMERALENGTHS:
                value = min(self.CAMERALENGTHS, key=lambda x: abs(x-value))
            selector = self.CAMERALENGTHS.index(value)
            self.eos3.SetSelector(selector) 
        else:
            if value not in self.MAGNIFICATIONS:
                value = min(self.MAGNIFICATIONS, key=lambda x: abs(x-value))
            
            # get best mode for magnification
            for k in sorted(self.MAGNIFICATION_MODES.keys(), key=self.MAGNIFICATION_MODES.get): # sort by values
                v = self.MAGNIFICATION_MODES[k]
                if v <= value:
                    new_mode = k
    
            if current_mode != new_mode:
                self.setFunctionMode(new_mode)
    
            # calculate index
            selector = self.MAGNIFICATIONS.index(value) - self.MAGNIFICATIONS.index(self.MAGNIFICATION_MODES[new_mode])
                    
            # self.eos3.SetMagValue(value)
            self.eos3.SetSelector(selector) 

    def getMagnificationIndex(self):
        value = self.getMagnification()
        current_mode = self.getFunctionMode()
        try:
            if current_mode == "diff":
                return self.CAMERALENGTHS.index(value)
            else:
                return self.MAGNIFICATIONS.index(value)
        except Exception:
            raise ValueError("getMagnificationIndex - invalid magnification: {}".format(value)) 

    def setMagnificationIndex(self, index):
        current_mode = self.getFunctionMode()
        
        if current_mode == "diff":
            value = self.CAMERALENGTHS[index]
        else:
            value = self.MAGNIFICATIONS[index]

        self.setMagnification(value)

    def getGunShift(self):
        x, y, result = self.def3.GetGunA1()
        return x, y

    def setGunShift(self, x, y):
        self.def3.SetGunA1(x, y)

    def getGunTilt(self):
        x, y, result = self.def3.GetGunA2()
        return x, y

    def setGunTilt(self, x, y):
        self.def3.SetGunA2(x, y)

    def getBeamShift(self):
        x, y, result = self.def3.GetCLA1()
        return x, y

    def setBeamShift(self, x, y):
        self.def3.SetCLA1(int(x), int(y))

    def getBeamTilt(self):
        x, y, result = self.def3.GetCLA2()
        return x, y

    def setBeamTilt(self, x, y):
        self.def3.SetCLA2(x, y)

    def getImageShift(self):
        x, y, result = self.def3.GetIS1()
        return x,y 

    def setImageShift(self, x, y):
        self.def3.SetIS1(x, y)

    def getImageShift2(self):
        x, y, result = self.def3.GetIS2()
        return x,y 

    def setImageShift2(self, x, y):
        self.def3.SetIS2(x, y)

    def getStagePosition(self):
        """
        x, y, z in nanometer
        a and b in degrees
        """
        x, y, z, a, b, result = self.gonio2.GetPosition()
        return x, y, z, a, b

    def isStageMoving(self):
        x, y, z, a, b, result = self.gonio2.GetStatus()
        return x or y or z or a or b 

    def waitForStage(self, delay=0):
        while self.isStageMoving():
            if delay > 0:
                time.sleep(delay)

    def setStageX(self, value, wait=True):
        self.stage3.SetX(value)
        if wait:
            self.waitForStage()

    def setStageY(self, value, wait=True):
        # self.gonio2.SetRotationAngle(value)  ## not tested, is this an alternative call?
        self.stage3.SetY(value)
        if wait:
            self.waitForStage()

    def setStageZ(self, value, wait=True):
        self.stage3.SetZ(value)
        if wait:
            self.waitForStage()

    def setStageA(self, value, wait=True):
        # self.gonio2.SetTiltXAngle(value)  ## alternative call
        self.stage3.SetTiltXAngle(value)
        if wait:
            self.waitForStage()

    def setStageB(self, value, wait=True):
        self.stage3.SetTiltYAngle(value)
        if wait:
            self.waitForStage()

    def setStageXY(self, x, y, wait=True):
        self.gonio2.SetPosition(x, y)  ## combined call is faster than to separate calls
        if wait:
            self.waitForStage()

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None):
        if z is not None:
            self.setStageZ(z)
        if a is not None:
            self.setStageA(a)
        if b is not None:
            self.setStageB(b)

        if (x is not None) and (y is not None):
            self.setStageXY(x=x, y=y)
        else:
            if x is not None:
                self.setStageX(x)     
            if y is not None:
                self.setStageY(y)

        if self.VERIFY_STAGE_POSITION:
            nx, ny, nz, na, nb = self.getStagePosition()
            if x is not None and abs(nx - x) > 150:
                logger.warning("stage.x -> requested: {:.1f}, got: {:.1f}".format(x, nx))
            if y is not None and abs(ny - y) > 150:
                logger.warning("stage.y -> requested: {:.1f}, got: {:.1f}".format(y, ny))
            if z is not None and abs(nz - z) > 500:
                logger.warning("stage.z -> requested: {}, got: {}".format(z, nz))
            if a is not None and abs(na - a) > 0.057:
                logger.warning("stage.a -> requested: {}, got: {}".format(a, na))
            if b is not None and abs(nb - b) > 0.057:
                logger.warning("stage.b -> requested: {}, got: {}".format(b, nb))

    def getFunctionMode(self):
        """mag1, mag2, lowmag, samag, diff"""
        mode, name, result = self.eos3.GetFunctionMode()
        return self.FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """mag1, mag2, lowmag, samag, diff"""
        if isinstance(value, str):
            try:
                value = self.FUNCTION_MODES.index(value)
            except ValueError:
                raise ValueError("Unrecognized function mode: {}".format(value))
        self.eos3.SelectFunctionMode(value)

    def getDiffFocus(self):
        if not self.getFunctionMode() == "diff":
            raise ValueError("Must be in 'diff' mode to get DiffFocus")
        value, result = self.lens3.GetIL1()
        return value

    def setDiffFocus(self, value):
        """IL1"""
        if not self.getFunctionMode() == "diff":
            raise ValueError("Must be in 'diff' mode to get DiffFocus")
        self.lens3.setDiffFocus(value)

    def getDiffShift(self):
        x, y, result = self.def3.GetPLA()
        return x, y

    def setDiffShift(self, x, y):
        self.def3.SetPLA(x, y)

    def releaseConnection(self):
        comtypes.CoUninitialize()
        logger.info("Connection to microscope released")

    def isBeamBlanked(self, value):
        value, result = self.def3.GetBeamBlank()
        return bool(value)

    def setBeamBlank(self, mode):
        """True/False or 1/0"""
        self.def3.SetBeamBlank(mode)

    def getCondensorLensStigmator(self):
        x, y, result = self.def3.getCLs()
        return x, y

    def setCondensorLensStigmator(self, x, y):
        self.def3.SetCLs(x, y)
        
    def getIntermediateLensStigmator(self):
        x, y, result = self.def3.GetILs()
        return x, y

    def setIntermediateLensStigmator(self, x, y):
        self.def3.SetILs(x, y)

    def getObjectiveLensStigmator(self):
        x, y, result = self.def3.GetOLs()
        return x, y

    def setObjectiveLensStigmator(self, x, y):
        self.def3.SetOLs(x, y)

    def getSpotSize(self):
        """0-based indexing for GetSpotSize, add 1 to be consistent with JEOL software"""
        value, result = self.eos3.GetSpotSize()
        return value + 1

    def setSpotSize(self, value):
        self.eos3.selectSpotSize(value - 1)

    def getScreenPosition(self):
        value = self.screen2.GetAngle()[0]
        UP, DOWN = 2, 0
        if value == UP:
            return 'up'
        elif value == DOWN:
            return 'down'
        else:
            return value

    def setScreenPosition(self, value):
        """value = 'up' or 'down'"""
        UP, DOWN = 2, 0
        if value == 'up':
            self.screen2.SelectAngle(UP)
        elif value == 'down':
            self.screen2.SelectAngle(DOWN)
        else:
            raise ValueError("No such screen position:", value, "(must be 'up'/'down')")

    def getAll(self):
        print("## lens3")
        print("CL1", self.lens3.GetCL1())
        print("CL2", self.lens3.GetCL2())
        print("CL3", self.lens3.GetCL3())
        print("CM", self.lens3.GetCM())
        print("FLc", self.lens3.GetFLc())
        print("FLcomp1", self.lens3.GetFLcomp1())
        print("FLcomp2", self.lens3.GetFLcomp2())
        print("FLf", self.lens3.GetFLf())
        print("IL1", self.lens3.GetIL1())
        print("IL2", self.lens3.GetIL2())
        print("IL3", self.lens3.GetIL3())
        print("IL4", self.lens3.GetIL4())
        print("OLc", self.lens3.GetOLc())
        print("OLf", self.lens3.GetOLf())
        print("OM", self.lens3.GetOM())
        print("OM2", self.lens3.GetOM2())
        print("OM2Flag", self.lens3.GetOM2Flag())
        print("PL1", self.lens3.GetPL1())
        print("PL2", self.lens3.GetPL2())
        print("PL3", self.lens3.GetPL3())
        print()
        print("## def3")
        print("CLA1", self.def3.GetCLA1())
        print("CLA2", self.def3.GetCLA2())
        print("CLs", self.def3.GetCLs())
        print("FLA1", self.def3.GetFLA1())
        print("FLA2", self.def3.GetFLA2())
        print("FLs1", self.def3.GetFLs1())
        print("FLs2", self.def3.GetFLs2())
        print("GUNA1", self.def3.GetGUNA1())
        print("GUNA2", self.def3.GetGUNA2())
        print("ILs", self.def3.GetILs())
        print("IS1", self.def3.GetIS1())
        print("IS2", self.def3.GetIS2())
        print("OLs", self.def3.GetOLs())
        print("PLA", self.def3.GetPLA())


