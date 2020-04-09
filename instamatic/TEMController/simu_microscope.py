import random
import time
from typing import Tuple

from instamatic import config
from instamatic.exceptions import TEMValueError


NTRLMAPPING = {
    'GUN1': 0,
    'GUN2': 1,
    'CLA1': 2,
    'CLA2': 3,
    'SHIFT': 4,
    'TILT': 5,
    'ANGLE': 6,
    'CLS': 7,
    'IS1': 8,
    'IS2': 9,
    'SPOT': 10,
    'PLA': 11,
    'OLS': 12,
    'ILS': 13,
}

FUNCTION_MODES = ('mag1', 'mag2', 'lowmag', 'samag', 'diff')

# constants for Jeol Hex value
ZERO = 32768
MAX = 65535
MIN = 0


class SimuMicroscope:
    """Simulates a microscope connection.

    Has the same variables as the real JEOL/FEI equivalents, but does
    not make any function calls. The initial lens/deflector/stage values
    are randomized based on the config file loaded.
    """

    def __init__(self, name: str = 'simulate'):
        super().__init__()

        self.CurrentDensity_value = 100_000.0

        self.Brightness_value = random.randint(MIN, MAX)

        self.GunShift_x = random.randint(MIN, MAX)
        self.GunShift_y = random.randint(MIN, MAX)

        self.GunTilt_x = random.randint(MIN, MAX)
        self.GunTilt_y = random.randint(MIN, MAX)

        self.BeamShift_x = random.randint(MIN, MAX)
        self.BeamShift_y = random.randint(MIN, MAX)

        self.BeamTilt_x = random.randint(MIN, MAX)
        self.BeamTilt_y = random.randint(MIN, MAX)

        self.ImageShift1_x = random.randint(MIN, MAX)
        self.ImageShift1_y = random.randint(MIN, MAX)

        self.ImageShift2_x = random.randint(MIN, MAX)
        self.ImageShift2_y = random.randint(MIN, MAX)

        # self.FunctionMode_value = random.randint(0, 2)
        self.FunctionMode_value = 0

        self.DiffractionFocus_value = random.randint(MIN, MAX)
        self.IntermediateLens1_value = random.randint(MIN, MAX)

        self.DiffractionShift_x = random.randint(MIN, MAX)
        self.DiffractionShift_y = random.randint(MIN, MAX)

        self.name = name

        self.FUNCTION_MODES = FUNCTION_MODES
        self.NTRLMAPPING = NTRLMAPPING

        self.ZERO = ZERO
        self.MAX = MAX
        self.MIN = MIN

        self._HT = 200_000  # V

        # self.Magnification_value = random.choice(self.MAGNIFICATIONS)
        self.Magnification_value = config.microscope.ranges['mag1'][10]
        self.Magnification_value_diff = config.microscope.ranges['diff'][3]

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

        self._StagePosition_x = random.randint(-100000, 100000)
        self._StagePosition_y = random.randint(-100000, 100000)
        self._StagePosition_z = random.randint(-10000, 10000)
        self._StagePosition_a = 0.0  # random.randint(-40, 40)
        self._StagePosition_b = 0.0  # random.randint(-40, 40)

        self._stage_dict = {}
        for key in ('a', 'b', 'x', 'y', 'z'):
            if key in ('a', 'b'):
                speed = 20.0  # degree / sec
                current = random.randint(-40, 40)
            elif key in ('x', 'y'):
                speed = 1_000_000.0  # nm / sec
                current = random.randint(-100000, 100000)
            elif key == 'z':
                speed = 100_000.0  # nm / sec
                current = random.randint(-10000, 10000)

            self._stage_dict[key] = {
                'current': current,
                'is_moving': False,
                'speed': speed,
                'speed_setting': 12,
                'direction': +1,
                'start': 0.0,
                'end': 0.0,
                't0': 0.0,
            }

        self.goniotool_available = config.settings.use_goniotool
        if self.goniotool_available:
            from instamatic.goniotool import GonioToolClient
            try:
                self.goniotool = GonioToolClient()
            except Exception as e:
                print('GonioToolClient:', e)
                print('Could not connect to GonioToolServer, goniotool unavailable!')
                self.goniotool_available = False
                config.settings.use_goniotool = False

    def is_goniotool_available(self):
        """Return goniotool status."""
        return self.goniotool_available

    def _set_instant_stage_movement(self):
        """Eliminate stage movement delays for testing."""
        for key in ('a', 'b', 'x', 'y', 'z'):
            self._stage_dict[key]['speed'] = 2**32

    def _StagePositionSetter(self, var: str, val: float) -> None:
        """General stage position setter, models stage movement speed."""
        d = self._stage_dict[var]
        current = d['current']
        direction = +1 if (val > current) else -1

        d['is_moving'] = True
        d['start'] = current
        d['end'] = val
        d['t0'] = time.perf_counter()
        d['direction'] = direction

    def _StagePositionGetter(self, var: str) -> float:
        """General stage position getter, models stage movement speed."""
        d = self._stage_dict[var]
        is_moving = d['is_moving']
        if is_moving:
            dt = time.perf_counter() - d['t0']
            direction = d['direction']
            speed = d['speed']
            start = d['start']
            end = d['end']
            val = start + direction * dt * speed

            if abs(val - start) > abs(end - start):
                d['current'] = end
                d['is_moving'] = False
                ret = end
            else:
                ret = val
        else:
            ret = d['current']

        return ret

    @property
    def StagePosition_a(self):
        return self._StagePositionGetter('a')

    @StagePosition_a.setter
    def StagePosition_a(self, value):
        self._StagePositionSetter('a', value)

    @property
    def StagePosition_b(self):
        return self._StagePositionGetter('b')

    @StagePosition_b.setter
    def StagePosition_b(self, value):
        self._StagePositionSetter('b', value)

    @property
    def StagePosition_x(self):
        return self._StagePositionGetter('x')

    @StagePosition_x.setter
    def StagePosition_x(self, value):
        self._StagePositionSetter('x', value)

    @property
    def StagePosition_y(self):
        return self._StagePositionGetter('y')

    @StagePosition_y.setter
    def StagePosition_y(self, value):
        self._StagePositionSetter('y', value)

    @property
    def StagePosition_z(self):
        return self._StagePositionGetter('z')

    @StagePosition_z.setter
    def StagePosition_z(self, value):
        self._StagePositionSetter('z', value)

    @property
    def _is_moving(self) -> bool:
        return any(self._stage_dict[key]['is_moving'] for key in self._stage_dict.keys())

    def getHTValue(self) -> float:
        return self._HT

    def getCurrentDensity(self) -> float:
        rand_val = (random.random() - 0.5) * 10000
        return self.CurrentDensity_value + rand_val

    def getBrightness(self) -> int:
        return self.Brightness_value

    def setBrightness(self, value: int):
        self.Brightness_value = value

    def getMagnification(self) -> int:
        if self.getFunctionMode() == 'diff':
            return self.Magnification_value_diff
        else:
            return self.Magnification_value

    def setNeutral(self, *args):
        """Neutralize given deflectors."""
        pass

    def setMagnification(self, value: int):
        current_mode = self.getFunctionMode()

        try:
            selector = config.microscope.ranges[current_mode].index(value)
        except ValueError:
            raise TEMValueError(f'No such camera length or magnification: {value}') from None

        if current_mode == 'diff':
            self.Magnification_value_diff = value
        else:
            self.Magnification_value = value

    def getMagnificationIndex(self) -> int:
        value = self.getMagnification()
        current_mode = self.getFunctionMode()

        selector = config.microscope.ranges[current_mode].index(value)

        return selector

    def getMagnificationAbsoluteIndex(self) -> int:
        index = self.getMagnificationIndex()
        mode = self.getFunctionMode()

        if mode in ('mag1', 'samag'):
            n_lowmag = len(config.microscope.ranges['lowmag'])
            index += n_lowmag

        return index

    def setMagnificationIndex(self, index: int):
        current_mode = self.getFunctionMode()

        if index < 0:
            raise TEMValueError(f'Cannot lower magnification (index={index})')

        try:
            value = config.microscope.ranges[current_mode][index]
        except IndexError:
            raise TEMValueError(f'No such camera length or magnification index: {index}') from None

        self.setMagnification(value)

    def increaseMagnificationIndex(self) -> int:
        idx = self.getMagnificationIndex
        self.setMagnificationIndex(idx + 1)
        return 1

    def decreaseMagnificationIndex(self) -> int:
        idx = self.getMagnificationIndex
        self.setMagnificationIndex(idx - 1)
        return 1

    def getMagnificationRanges(self) -> dict:
        mag_ranges = {}
        for i, mode in enumerate(self.FUNCTION_MODES):
            try:
                mag_ranges[mode] = config.microscope.ranges[mode]
            except KeyError:
                pass

        return mag_ranges

    def getGunShift(self) -> Tuple[int, int]:
        return self.GunShift_x, self.GunShift_y

    def setGunShift(self, x: int, y: int):
        self.GunShift_x = x
        self.GunShift_y = y

    def getGunTilt(self) -> Tuple[int, int]:
        return self.GunTilt_x, self.GunTilt_y

    def setGunTilt(self, x: int, y: int):
        self.GunTilt_x = x
        self.GunTilt_y = y

    def getBeamShift(self) -> Tuple[int, int]:
        return self.BeamShift_x, self.BeamShift_y

    def setBeamShift(self, x: int, y: int):
        self.BeamShift_x = x
        self.BeamShift_y = y

    def getBeamTilt(self) -> Tuple[int, int]:
        return self.BeamTilt_x, self.BeamTilt_y

    def setBeamTilt(self, x: int, y: int):
        self.BeamTilt_x = x
        self.BeamTilt_y = y

    def getImageShift1(self) -> Tuple[int, int]:
        return self.ImageShift1_x, self.ImageShift1_y

    def setImageShift1(self, x: int, y: int):
        self.ImageShift1_x = x
        self.ImageShift1_y = y

    def getImageShift2(self):
        return self.ImageShift2_x, self.ImageShift2_y

    def setImageShift2(self, x: int, y: int):
        self.ImageShift2_x = x
        self.ImageShift2_y = y

    def getStagePosition(self) -> Tuple[int, int, int, int, int]:
        return self.StagePosition_x, self.StagePosition_y, self.StagePosition_z, self.StagePosition_a, self.StagePosition_b

    def isStageMoving(self) -> bool:
        self.getStagePosition()  # trigger update of self._is_moving
        # print(res, self._is_moving)
        return self._is_moving

    def waitForStage(self, delay: float = 0.1):
        while self.isStageMoving():
            time.sleep(delay)

    def setStageX(self, value: int, wait: bool = True):
        self.StagePosition_x = value
        if wait:
            self.waitForStage()

    def setStageY(self, value: int, wait: bool = True):
        self.StagePosition_y = value
        if wait:
            self.waitForStage()

    def setStageZ(self, value: int, wait: bool = True):
        self.StagePosition_z = value
        if wait:
            self.waitForStage()

    def setStageA(self, value: int, wait: bool = True):
        self.StagePosition_a = value
        if wait:
            self.waitForStage()

    def setStageB(self, value: int, wait: bool = True):
        self.StagePosition_b = value
        if wait:
            self.waitForStage()

    def setStageXY(self, x: int, y: int, wait: bool = True):
        self.StagePosition_x = x
        self.StagePosition_y = y
        if wait:
            self.waitForStage()

    def stopStage(self):
        pass

    def setStagePosition(self, x: int = None, y: int = None, z: int = None, a: int = None, b: int = None, speed: float = -1, wait: bool = True):
        if z is not None:
            self.setStageZ(z, wait=wait)
        if a is not None:
            self.setStageA(a, wait=wait)
        if b is not None:
            self.setStageB(b, wait=wait)

        if (x is not None) and (y is not None):
            self.setStageXY(x=x, y=y, wait=wait)
        else:
            if x is not None:
                self.setStageX(x, wait=wait)
            if y is not None:
                self.setStageY(y, wait=wait)

    def getRotationSpeed(self) -> int:
        return self._stage_dict['a']['speed_setting']

    def setRotationSpeed(self, value: int):
        self._stage_dict['a']['speed_setting'] = value
        self._stage_dict['a']['speed'] = 10.0 * (value / 12)

    def getFunctionMode(self) -> str:
        """mag1, mag2, lowmag, samag, diff."""
        mode = self.FunctionMode_value
        return FUNCTION_MODES[mode]

    def setFunctionMode(self, value: int):
        """mag1, mag2, lowmag, samag, diff."""
        if isinstance(value, str):
            try:
                value = FUNCTION_MODES.index(value)
            except ValueError:
                raise TEMValueError(f'Unrecognized function mode: {value}')
        self.FunctionMode_value = value

    def getDiffFocus(self, confirm_mode: bool = True) -> int:
        if not self.getFunctionMode() == 'diff':
            raise TEMValueError("Must be in 'diff' mode to get DiffFocus")
        return self.DiffractionFocus_value

    def setDiffFocus(self, value: int, confirm_mode: bool = True):
        """IL1."""
        if not self.getFunctionMode() == 'diff':
            raise TEMValueError("Must be in 'diff' mode to set DiffFocus")
        self.DiffractionFocus_value = value

    def setIntermediateLens1(self, value: int):
        """IL1."""
        self.IntermediateLens1_value = value

    def getIntermediateLens1(self):
        """IL1."""
        return self.IntermediateLens1_value

    def getDiffShift(self) -> Tuple[int, int]:
        return self.DiffractionShift_x, self.DiffractionShift_y

    def setDiffShift(self, x: int, y: int):
        self.DiffractionShift_x = x
        self.DiffractionShift_y = y

    def releaseConnection(self):
        print('Connection to microscope released')

    def isBeamBlanked(self) -> bool:
        return self.beamblank

    def setBeamBlank(self, mode: bool):
        """True/False or 1/0."""
        self.beamblank = mode

    def getCondensorLensStigmator(self) -> Tuple[int, int]:
        return self.condensorlensstigmator_x, self.condensorlensstigmator_y

    def setCondensorLensStigmator(self, x: int, y: int):
        self.condensorlensstigmator_x = x
        self.condensorlensstigmator_y = y

    def getIntermediateLensStigmator(self) -> Tuple[int, int]:
        return self.intermediatelensstigmator_x, self.intermediatelensstigmator_y

    def setIntermediateLensStigmator(self, x: int, y: int):
        self.intermediatelensstigmator_x = x
        self.intermediatelensstigmator_y = y

    def getObjectiveLensStigmator(self) -> Tuple[int, int]:
        return self.objectivelensstigmator_x, self.objectivelensstigmatir_y

    def setObjectiveLensStigmator(self, x: int, y: int):
        self.objectivelensstigmator_x = x
        self.objectivelensstigmator_y = y

    def getSpotSize(self) -> int:
        """0-based indexing for GetSpotSize, add 1 for consistency."""
        return self.spotsize

    def getScreenPosition(self) -> str:
        return self.screenposition_value

    def setScreenPosition(self, value: int):
        """value = 'up' or 'down'"""
        if value not in ('up', 'down'):
            raise TEMValueError(f'No such screen position: `{value}`.')
        self.screenposition_value = value

    def setSpotSize(self, value: int):
        self.spotsize = value

    def getCondensorLens1(self) -> int:
        return self.condensorlens1_value

    def getCondensorLens2(self) -> int:
        return self.condensorlens2_value

    def getCondensorMiniLens(self) -> int:
        return self.condensorminilens_value

    def getObjectiveLenseCoarse(self) -> int:
        return self.objectivelensecoarse_value

    def getObjectiveLenseFine(self) -> int:
        return self.objectivelensefine_value

    def getObjectiveMiniLens(self) -> int:
        return self.objectiveminilens_value
