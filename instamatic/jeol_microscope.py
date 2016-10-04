import logging

import atexit
import comtypes.client
import time
import os

MAGNIFICATIONS = [
 50,
 60,
 80,
 100,
 150,
 200,
 300,
 400,
 500,
 600,
 800,
 1000,
 1200,
 1500,
 2000,
 2500,
 3000,
 4000,
 5000,
 6000,
 8000,
 10000,
 12000,
 15000,
 20000,
 25000,
 30000,
 40000,
 50000,
 60000,
 80000,
 100000,
 120000,
 150000,
 200000,
 250000,
 300000,
 400000,
 500000,
 600000,
 800000,
 1000000,
 1200000,
 1500000,
 2000000]

MAGNIFICATION_MODES = {"mag1": 2500, "lowmag":50}

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
        if value not in MAGNIFICATIONS:
            value = min(MAGNIFICATIONS.keys(), key=lambda x: abs(x-value))
        
        # get best mode for magnification
        for k in sorted(MAGNIFICATION_MODES.keys(), key=MAGNIFICATION_MODES.get): # sort by values
            v = MAGNIFICATION_MODES[k]
            if v <= value:
                new_mode = k

        current_mode = self.getFunctionMode()
        if current_mode != new_mode:
            self.setFunctionMode(new_mode)

        # calculate index
        ## i = 0-24 for lowmag
        ## i = 0-29 for mag1
        selector = MAGNIFICATIONS.index(value) - MAGNIFICATIONS.index(MAGNIFICATION_MODES[new_mode])
                
        # self.eos3.SetMagValue(value)
        self.eos3.SetSelector(selector) 

    def getMagnificationIndex(self):
        value = self.getMagnification()
        return MAGNIFICATIONS.index(value)

    def setMagnificationIndex(self, index):
        value = MAGNIFICATIONS[index]
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
        self.def3.SetCLA1(x, y)

    def getBeamTilt(self):
        x, y, result = self.def3.GetCLA2()
        return x, y

    def setBeamTilt(self, x, y):
        self.def3.SetCLA2(x, y)

    def getImageShift(self):
        x, y, result = self.def3.GetIS1()
        return x,y 

    def setImageShift(self, x, y):
        self.def3.GetIS1(x, y)

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
                x = xy_limit + x
                print " >> Correct backlash in x, approach: {} -> {}".format(x, x-xy_limit)
        
        if y is not None:
            shift_y = y - current_y
            if shift_y < 0 and abs(shift_y) > xy_limit:
                do_backlash = True
                y = xy_limit + y
                print " >> Correct backlash in x, approach: {} -> {}".format(y, y-xy_limit)

        if z is not None:
            shift_z = z - current_z
            if shift_z < 0 and abs(shift_z) > height_limit:
                do_backlash = True
                z = height_limit + z
                print " >> Correct backlash in z, approach: {} -> {}".format(z, z-height_limit)
        
        if a is not None:
            shift_a = a - current_a
            if shift_a < 0 and abs(shift_a) > angle_limit:
                do_backlash = True
                a = angle_limit + a
                print " >> Correct backlash in a, approach: {} -> {}".format(a, a-angle_limit)
        
        if b is not None:
            shift_b = b - current_b
            if shift_b < 0 and abs(shift_b) > angle_limit:
                do_backlash = True
                b = angle_limit + b
                print " >> Correct backlash in b, approach: {} -> {}".format(b, b-angle_limit)

        if do_backlash:
            self.setStagePosition(x, y, z, a, b, backlash=False)

    def forceStageBacklashCorrection(self, x=False, y=False, z=False, a=False, b=False):
        current_x, current_y, current_z, current_a, current_b = self.getStagePosition()

        xy_limit = 10000
        angle_limit = 1.0
        height_limit = 1000

        if x:
            x = xy_limit + current_x
            print " >> Correct backlash in x, approach: {} -> {} (force)".format(x, current_x)
        else:
            current_x, x = None, None

        if y:
            y = xy_limit + current_y
            print " >> Correct backlash in x, approach: {} -> {} (force)".format(y, current_y)
        else:
            current_y, y = None, None

        if z:
            z = height_limit + current_z
            print " >> Correct backlash in z, approach: {} -> {} (force)".format(z, current_z)
        else:
            current_z, z = None, None

        if a:
            a = angle_limit + current_a
            print " >> Correct backlash in a, approach: {} -> {} (force)".format(a, current_a)
        else:
            current_a, a = None, None

        if b:
            b = angle_limit + current_b
            print " >> Correct backlash in b, approach: {} -> {} (force)".format(b, current_b)
        else:
            current_b, b = None, None

        self.setStagePosition(x, y, z, a, b, backlash=False)
        self.setStagePosition(current_x, current_y, current_z, current_a, current_b, backlash=False)

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, backlash=True):
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