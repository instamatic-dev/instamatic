from config import specifications

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


class SimuMicroscope(object):
    """docstring for microscope"""
    def __init__(self, model="lab6"):
        super(SimuMicroscope, self).__init__()
        import random
        
        self.Brightness_value = random.randint(MIN, MAX)

        self.GunShift_x = random.randint(MIN, MAX)
        self.GunShift_y = random.randint(MIN, MAX)

        self.GunTilt_x = random.randint(MIN, MAX)
        self.GunTilt_y = random.randint(MIN, MAX)

        self.BeamShift_x = random.randint(MIN, MAX)
        self.BeamShift_y = random.randint(MIN, MAX)

        self.BeamTilt_x = random.randint(MIN, MAX)
        self.BeamTilt_y = random.randint(MIN, MAX)

        self.ImageShift_x = random.randint(MIN, MAX)
        self.ImageShift_y = random.randint(MIN, MAX)

        self.StagePosition_x = random.randint(MIN, MAX)
        self.StagePosition_y = random.randint(MIN, MAX)
        self.StagePosition_z = random.randint(MIN, MAX)
        self.StagePosition_a = random.randint(MIN, MAX)
        self.StagePosition_b = random.randint(MIN, MAX)

        # self.FunctionMode_value = random.randint(0, 2)
        self.FunctionMode_value = 0

        self.DiffractionFocus_value = random.randint(MIN, MAX)

        self.DiffractionShift_x = random.randint(MIN, MAX)
        self.DiffractionShift_y = random.randint(MIN, MAX)

        self.model = model
        self.MAGNIFICATIONS      = specifications["MAGNIFICATIONS"]
        self.MAGNIFICATION_MODES = specifications["MAGNIFICATION_MODES"]
        self.CAMERALENGTHS       = specifications["CAMERALENGTHS"]

        self.FUNCTION_MODES = FUNCTION_MODES
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


    def getBrightness(self):
        return self.Brightness_value

    def setBrightness(self, value):
        self.Brightness_value = value

    def getMagnification(self):
        if self.getFunctionMode() == "diff":
            return self.Magnification_value_diff
        else:
            return self.Magnification_value

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
                
        if self.getFunctionMode() == "diff":
            self.Magnification_value_diff = value
        else:
            self.Magnification_value = value

    def getMagnificationIndex(self):
        value = self.getMagnification()
        return self.MAGNIFICATIONS.index(value)

    def setMagnificationIndex(self, index):
        value = self.MAGNIFICATIONS[index]
        self.setMagnification(value)

    def getGunShift(self):
        return self.GunShift_x, self.GunShift_y

    def setGunShift(self, x, y):
        self.GunShift_x = x
        self.GunShift_y = y
    
    def getGunTilt(self):
        return self.GunTilt_x, self.GunTilt_y 
    
    def setGunTilt(self, x, y):
        self.GunTilt_x = x
        self.GunTilt_y = y

    def getBeamShift(self):
        return self.BeamShift_x, self.BeamShift_y

    def setBeamShift(self, x, y):
        self.BeamShift_x = x
        self.BeamShift_y = y

    def getBeamTilt(self):
        return self.BeamTilt_x, self.BeamTilt_y
    
    def setBeamTilt(self, x, y):
        self.BeamTilt_x = x
        self.BeamTilt_y = y

    def getImageShift(self):
        return self.ImageShift_x, self.ImageShift_y

    def setImageShift(self, x, y):
        self.ImageShift_x = x
        self.ImageShift_y = y

    def getStagePosition(self):
        return self.StagePosition_x, self.StagePosition_y, self.StagePosition_z, self.StagePosition_a, self.StagePosition_b

    def isStageMoving(self):
        return False

    def waitForStage(self, delay=0.1):
        while self.isStageMoving():
            time.sleep(delay)

    def setStageX(self, value):
        self.StagePosition_x = value

    def setStageY(self, value):
        self.StagePosition_y = value

    def setStageZ(self, value):
        self.StagePosition_z = value

    def setStageA(self, value):
        self.StagePosition_a = value

    def setStageB(self, value):
        self.StagePosition_b = value
        
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

    def getFunctionMode(self):
        """mag1, mag2, lowmag, samag, diff"""
        mode = self.FunctionMode_value
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value):
        """mag1, mag2, lowmag, samag, diff"""
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise ValueError("Unrecognized function mode: {}".format(value))
        self.FunctionMode_value = value

    def getDiffFocus(self):
        return self.DiffractionFocus_value

    def setDiffFocus(self, value):
        """IC1"""
        self.DiffractionFocus_value = value

    def getDiffShift(self):
        return self.DiffractionShift_x, self.DiffractionShift_y

    def setDiffShift(self, x, y):
        self.DiffractionShift_x = x
        self.DiffractionShift_y = y

    def releaseConnection(self):
        print "Connection to microscope released"

    def isBeamBlanked(self, value):
        return self.beamblank

    def setBeamBlank(self, mode):
        """True/False or 1/0"""
        self.beamblank = mode

    def getCondensorLensStigmator(self):
        return self.condensorlensstigmator_x, self.condensorlensstigmator_y

    def setCondensorLensStigmator(self, x, y):
        self.condensorlensstigmator_x = x
        self.condensorlensstigmator_y = y
        
    def getIntermediateLensStigmator(self):
        return self.intermediatelensstigmator_x, self.intermediatelensstigmator_y

    def setIntermediateLensStigmator(self, x, y):
        self.intermediatelensstigmator_x = x
        self.intermediatelensstigmator_y = y

    def getObjectiveLensStigmator(self):
        return self.objectivelensstigmator_x, self.objectivelensstigmatir_y

    def setObjectiveLensStigmator(self, x, y):
        self.objectivelensstigmator_x = x
        self.objectivelensstigmator_y = y

    def getSpotSize(self):
        """0-based indexing for GetSpotSize, add 1 for consistency"""
        return self.spotsize

    def setSpotSize(self, value):
        self.spotsize = value


