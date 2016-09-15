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
        for k in sorted(MAGNIFICATION_MODES.keys()):
            if k <= value:
                new_mode = MAGNIFICATION_MODES[k]

        current_mode = self.getFunctionMode()
        if current_mode != new_mode:
            self.setFunctionMode(new_mode)
        
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
        pass

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None):
        if x:
            self.StagePosition_x = x
        if y:
            self.StagePosition_y = y
        if z:
            self.StagePosition_z = z
        if a:
            self.StagePosition_a = a
        if b:
            self.StagePosition_b = b

    def getFunctionMode(self):
        return FUNCTION_MODES[self.FunctionMode_value]

    def setFunctionMode(self, value):
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise ValueError("Unrecognized function mode: {}".format(value))
        self.FunctionMode_value = value

    def getDiffractionFocus(self): #IC1
        return self.DiffractionFocus_value

    def setDiffractionFocus(self, value): #IC1
        self.DiffractionFocus_value = value

    def getDiffractionShift(self):
        return self.DiffractionShift_x, self.DiffractionShift_y

    def setDiffractionShift(self, x, y):
        self.DiffractionShift_x = x
        self.DiffractionShift_y = y
