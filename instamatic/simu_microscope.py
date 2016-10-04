from jeol_microscope import ZERO, MIN, MAX, MAGNIFICATIONS, MAGNIFICATION_MODES, FUNCTION_MODES


class SimuMicroscope(object):
    """docstring for microscope"""
    def __init__(self):
        super(SimuMicroscope, self).__init__()
        import random
        
        self.Brightness_value = random.randint(MIN, MAX)

        self.Magnification_value = random.choice(MAGNIFICATIONS)

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

        self.FunctionMode_value = random.randint(0, 2)

        self.DiffractionFocus_value = random.randint(MIN, MAX)

        self.DiffractionShift_x = random.randint(MIN, MAX)
        self.DiffractionShift_y = random.randint(MIN, MAX)

    def getBrightness(self):
        return self.Brightness_value

    def setBrightness(self, value):
        self.Brightness_value = value

    def getMagnification(self):
        return self.Magnification_value

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
                
        self.Magnification_value = value

    def getMagnificationIndex(self):
        value = self.getMagnification()
        return MAGNIFICATIONS.index(value)

    def setMagnificationIndex(self, index):
        value = MAGNIFICATIONS[index]
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

    def getDiffFocus(self): #IC1
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