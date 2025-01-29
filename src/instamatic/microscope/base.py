from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple


class MicroscopeBase(ABC):
    @abstractmethod
    def getBeamShift(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getBeamTilt(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getBrightness(self) -> int:
        pass

    @abstractmethod
    def getCondensorLensStigmator(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getCurrentDensity(self) -> float:
        pass

    @abstractmethod
    def getDiffFocus(self, confirm_mode: bool) -> int:
        pass

    @abstractmethod
    def getDiffShift(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getFunctionMode(self) -> str:
        pass

    @abstractmethod
    def getGunShift(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getGunTilt(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getHTValue(self) -> float:
        pass

    @abstractmethod
    def getImageShift1(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getImageShift2(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getIntermediateLensStigmator(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getMagnification(self) -> int:
        pass

    @abstractmethod
    def getMagnificationAbsoluteIndex(self) -> int:
        pass

    @abstractmethod
    def getMagnificationIndex(self) -> int:
        pass

    @abstractmethod
    def getMagnificationRanges(self) -> dict:
        pass

    @abstractmethod
    def getObjectiveLensStigmator(self) -> Tuple[int, int]:
        pass

    @abstractmethod
    def getScreenPosition(self) -> str:
        pass

    @abstractmethod
    def getSpotSize(self) -> int:
        pass

    @abstractmethod
    def getStagePosition(self) -> Tuple[int, int, int, int, int]:
        pass

    @abstractmethod
    def isBeamBlanked(self) -> bool:
        pass

    @abstractmethod
    def isStageMoving(self) -> bool:
        pass

    @abstractmethod
    def release_connection(self) -> None:
        pass

    @abstractmethod
    def setBeamBlank(self, mode: bool) -> None:
        pass

    @abstractmethod
    def setBeamShift(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setBeamTilt(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setBrightness(self, value: int) -> None:
        pass

    @abstractmethod
    def setCondensorLensStigmator(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setDiffFocus(self, value: int, confirm_mode: bool) -> None:
        pass

    @abstractmethod
    def setDiffShift(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setFunctionMode(self, value: int) -> None:
        pass

    @abstractmethod
    def setGunShift(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setGunTilt(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setImageShift1(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setImageShift2(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setIntermediateLensStigmator(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setMagnification(self, value: int) -> None:
        pass

    @abstractmethod
    def setMagnificationIndex(self, index: int) -> None:
        pass

    @abstractmethod
    def setObjectiveLensStigmator(self, x: int, y: int) -> None:
        pass

    @abstractmethod
    def setScreenPosition(self, value: str) -> None:
        pass

    @abstractmethod
    def setSpotSize(self, value: int) -> None:
        pass

    @abstractmethod
    def setStagePosition(self, x: int, y: int, z: int, a: int, b: int, wait: bool) -> None:
        pass

    @abstractmethod
    def stopStage(self) -> None:
        pass
