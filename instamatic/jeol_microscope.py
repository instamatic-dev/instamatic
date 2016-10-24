import logging

import atexit
import comtypes.client
import time
import os

specifications = {
    "feg": {
        "MAGNIFICATIONS": (250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000, 200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000),
        "MAGNIFICATION_MODES": {"mag1": 2000, "lowmag":250}
    },
    "lab6":{
        "MAGNIFICATIONS": (50, 60, 80, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000, 200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000, 2000000),
        "MAGNIFICATION_MODES": {"mag1": 2500, "lowmag":50}
    }
}

FUNCTION_MODES = ('mag1', 'mag2', 'lowmag', 'samag', 'diff')

# constants for Jeol Hex value
ZERO = 32768
MAX = 65535
MIN = 0

class JeolMicroscope(object):
    """docstring for microscope"""
    def __init__(self):
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
        self.def3 = self.tem3.CreateDef3()
        # self.detector3 = self.tem3.CreateDetector3()
        self.eos3 = self.tem3.CreateEOS3()
        # self.feg3 = self.tem3.CreateFEG3()
        # self.filter3 = self.tem3.CreateFilter3()
        self.ht3 = self.tem3.CreateHT3()
        self.lens3 = self.tem3.CreateLens3()
        # self.mds3 = self.tem3.CreateMDS3()
        self.stage3 = self.tem3.CreateStage3()

        # wait for interface to activate
        t = 0
        while True:
            ht, result = self.ht3.GetHTValue()
            if result == 0:
                break
            time.sleep(1)
            t += 1
            print "Waiting for microscope, t = {}s".format(t)
            if t > 30:
                raise RuntimeError("Cannot establish microscope connection (timeout).")

        logging.info("Microscope connection established")
        atexit.register(self.releaseConnection)

        self._x_direction = 0
        self._y_direction = 0

        kind = "lab6" # /feg
        self.MAGNIFICATIONS      = specifications[kind]["MAGNIFICATIONS"]
        self.MAGNIFICATION_MODES = specifications[kind]["MAGNIFICATION_MODES"]

    def __del__(self):
        comtypes.CoUninitialize()

    def getBrightness(self):
        value, result = self.lens3.GetCL3()
        return value

    def setBrightness(self, value):
        self.lens3.setCL3(value)

    def getMagnification(self):
        value, unit_str, label_str, result = self.eos3.GetMagValue()
        return value

    def setMagnification(self, value):
        if value not in self.MAGNIFICATIONS:
            value = min(self.MAGNIFICATIONS, key=lambda x: abs(x-value))
        
        # get best mode for magnification
        for k in sorted(self.MAGNIFICATION_MODES.keys(), key=self.MAGNIFICATION_MODES.get): # sort by values
            v = self.MAGNIFICATION_MODES[k]
            if v <= value:
                new_mode = k

        current_mode = self.getFunctionMode()
        if current_mode != new_mode:
            self.setFunctionMode(new_mode)

        # calculate index
        ## i = 0-24 for lowmag
        ## i = 0-29 for mag1
        selector = self.MAGNIFICATIONS.index(value) - self.MAGNIFICATIONS.index(self.MAGNIFICATION_MODES[new_mode])
                
        # self.eos3.SetMagValue(value)
        self.eos3.SetSelector(selector) 

    def getMagnificationIndex(self):
        value = self.getMagnification()
        return self.MAGNIFICATIONS.index(value)

    def setMagnificationIndex(self, index):
        value = self.MAGNIFICATIONS[index]
        self.setMagnification(value)

    def getGunShift(self):
        x, y, result = self.def3.GetGunA2()
        return x, y

    def setGunShift(self, x, y):
        self.def3.SetGunA2(x, y)

    def getGunTilt(self):
        x, y, result = self.def3.GetGunA1()
        return x, y

    def setGunTilt(self, x, y):
        self.def3.SetGunA1(x, y)

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

    def getStagePosition(self):
        """
        x, y, z in nanometer
        a and b in degrees
        """
        x, y, z, a, b, result = self.stage3.GetPos()
        return x, y, z, a, b

    def isStageMoving(self):
        x, y, z, a, b, result = self.stage3.GetStatus()
        return x or y or z or a or b 

    def waitForStage(self, delay=0.1):
        while self.isStageMoving():
            time.sleep(delay)

    def setStageX(self, value):
        self.stage3.SetX(value)
        self.waitForStage()

    def setStageY(self, value):
        self.stage3.SetY(value)
        self.waitForStage()

    def setStageZ(self, value):
        self.stage3.SetZ(value)
        self.waitForStage()

    def setStageA(self, value):
        self.stage3.SetTiltXAngle(value)
        self.waitForStage()

    def setStageB(self, value):
        self.stage3.SetTiltYAngle(value)
        self.waitForStage()

    def _setStagePosition_backlash(self, x=None, y=None, z=None, a=None, b=None):
        """Backlash errors can be minimized by always approaching the target from the same direction"""
        current_x, current_y, current_z, current_a, current_b = self.getStagePosition()

        xy_limit = 10000
        angle_limit = 1.0
        height_limit = 1000

        do_backlash = False

        if x is not None:
            shift_x = x - current_x
            if shift_x < 0 and abs(shift_x) > xy_limit:
                do_backlash = True
                print " >> Correct backlash in x, approach: {:.1f} -> {:.1f}".format(x-xy_limit, x)
                x = x - xy_limit
        
        if y is not None:
            shift_y = y - current_y
            if shift_y < 0 and abs(shift_y) > xy_limit:
                do_backlash = True
                print " >> Correct backlash in y, approach: {:.1f} -> {:.1f}".format(y-xy_limit, y)
                y = y - xy_limit

        if z is not None:
            shift_z = z - current_z
            if shift_z < 0 and abs(shift_z) > height_limit:
                do_backlash = True
                print " >> Correct backlash in z, approach: {:.1f} -> {:.1f}".format(z-height_limit, z)
                z = z - height_limit
        
        if a is not None:
            shift_a = a - current_a
            if shift_a < 0 and abs(shift_a) > angle_limit:
                do_backlash = True
                print " >> Correct backlash in a, approach: {:.2f} -> {:.2f}".format(a-angle_limit, a)
                a = a - angle_limit
        
        if b is not None:
            shift_b = b - current_b
            if shift_b < 0 and abs(shift_b) > angle_limit:
                do_backlash = True
                print " >> Correct backlash in b, approach: {:.2f} -> {:.2f}".format(b-angle_limit, b)
                b = b - angle_limit

        if do_backlash:
            self.setStagePosition(x, y, z, a, b, backlash=False)

    def forceStageBacklashCorrection(self, x=False, y=False, z=False, a=False, b=False):
        current_x, current_y, current_z, current_a, current_b = self.getStagePosition()

        xy_limit = 10000
        angle_limit = 1.0
        height_limit = 1000

        if x:
            x = current_x - xy_limit
            print " >> Correct backlash in x, approach: {:.1f} -> {:.1f} (force)".format(x, current_x)
        else:
            current_x, x = None, None

        if y:
            y = current_y - xy_limit
            print " >> Correct backlash in y, approach: {:.1f} -> {:.1f} (force)".format(y, current_y)
        else:
            current_y, y = None, None

        if z:
            z = current_z - height_limit
            print " >> Correct backlash in z, approach: {:.1f} -> {:.1f} (force)".format(z, current_z)
        else:
            current_z, z = None, None

        if a:
            a = current_a - angle_limit
            print " >> Correct backlash in a, approach: {:.2f} -> {:.2f} (force)".format(a, current_a)
        else:
            current_a, a = None, None

        if b:
            b = current_b - angle_limit
            print " >> Correct backlash in b, approach: {:.2f} -> {:.2f} (force)".format(b, current_b)
        else:
            current_b, b = None, None

        self.setStagePosition(x, y, z, a, b, backlash=False)
        n = 2 # number of stages
        for i in range(n):
            j = i + 1
            if x:
                x = ((n-j)*x + j*current_x) / n
            if y:
                y = ((n-j)*y + j*current_y) / n
            if z:
                z = ((n-j)*z + j*current_z) / n
            if a:
                a = ((n-j)*a + j*current_a) / n
            if b:
                b = ((n-j)*b + j*current_b) / n

            print " >> Force backlash, stage {}".format(j)
            self.setStagePosition(x, y, z, a, b, backlash=False)

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, backlash=False):
        if backlash:
            self._setStagePosition_backlash(x, y, z, a, b)

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

        nx, ny, nz, na, nb = self.getStagePosition()
        if x is not None and abs(nx - x) > 150:
            print " >> Warning: stage.x -> requested: {:.1f}, got: {:.1f}".format(x, nx) # +- 150 nm
            logging.debug("stage.x -> requested: {:.1f}, got: {:.1f}, backlash: {}".format(x, nx, backlash))
        if y is not None and abs(ny - y) > 150:
            print " >> Warning: stage.y -> requested: {:.1f}, got: {:.1f}".format(y, ny) # +- 150 nm
            logging.debug("stage.y -> requested: {:.1f}, got: {:.1f}, backlash: {}".format(y, ny, backlash))
        if z is not None and abs(nz - z) > 500:
            print " >> Warning: stage.z -> requested: {}, got: {}".format(z, nz) # +- 500 nm
            logging.debug("stage.z -> requested: {}, got: {}, backlash: {}".format(z, nz, backlash))
        if a is not None and abs(na - a) > 0.057:
            print " >> Warning: stage.a -> requested: {}, got: {}".format(a, na) # +- 0.057 degrees
            logging.debug("stage.a -> requested: {}, got: {}, backlash: {}".format(a, na, backlash))
        if b is not None and abs(nb - b) > 0.057:
            print " >> Warning: stage.b -> requested: {}, got: {}".format(b, nb) # +- 0.057 degrees
            logging.debug("stage.b -> requested: {}, got: {}, backlash: {}".format(b, nb, backlash))

    def getFunctionMode(self):
        """mag1, mag2, lowmag, samag, diff"""
        mode, name, result = self.eos3.GetFunctionMode()
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """mag1, mag2, lowmag, samag, diff"""
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise ValueError("Unrecognized function mode: {}".format(value))
        self.eos3.SelectFunctionMode(value)

    def getDiffFocus(self):
        value, result = self.lens3.GetIL1()
        return value

    def setDiffFocus(self, value):
	"""IC1"""
        self.lens3.setDiffFocus(value)

    def getDiffShift(self):
        x, y, result = self.def3.GetPLA()
        return x, y

    def setDiffShift(self, x, y):
        self.def3.SetPLA(x, y)

    def releaseConnection(self):
        comtypes.CoUninitialize()
        print "Connection to microscope released"

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
        """0-based indexing for GetSpotSize, add 1 for consistency"""
        value, result = self.eos3.GetSpotSize()
        return value + 1

    def setSpotSize(self, value):
        self.eos3.SetSpotSize(value - 1)

    def getAll(self):
        print "## lens3"
        print "CL1", self.lens3.GetCL1()
        print "CL2", self.lens3.GetCL2()
        print "CL3", self.lens3.GetCL3()
        print "CM", self.lens3.GetCM()
        print "FLc", self.lens3.GetFLc()
        print "FLcomp1", self.lens3.GetFLcomp1()
        print "FLcomp2", self.lens3.GetFLcomp2()
        print "FLf", self.lens3.GetFLf()
        print "IL1", self.lens3.GetIL1()
        print "IL2", self.lens3.GetIL2()
        print "IL3", self.lens3.GetIL3()
        print "IL4", self.lens3.GetIL4()
        print "OLc", self.lens3.GetOLc()
        print "OLf", self.lens3.GetOLf()
        print "OM", self.lens3.GetOM()
        print "OM2", self.lens3.GetOM2()
        print "OM2Flag", self.lens3.GetOM2Flag()
        print "PL1", self.lens3.GetPL1()
        print "PL2", self.lens3.GetPL2()
        print "PL3", self.lens3.GetPL3()
        print
        print "## def3"
        print "CLA1", self.def3.GetCLA1()
        print "CLA2", self.def3.GetCLA2()
        print "CLs", self.def3.GetCLs()
        print "FLA1", self.def3.GetFLA1()
        print "FLA2", self.def3.GetFLA2()
        print "FLs1", self.def3.GetFLs1()
        print "FLs2", self.def3.GetFLs2()
        print "GUNA1", self.def3.GetGUNA1()
        print "GUNA2", self.def3.GetGUNA2()
        print "ILs", self.def3.GetILs()
        print "IS1", self.def3.GetIS1()
        print "IS2", self.def3.GetIS2()
        print "OLs", self.def3.GetOLs()
        print "PLA", self.def3.GetPLA()


