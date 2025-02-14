from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np

from instamatic import config


class CameraBase(ABC):
    # Set manually
    name: str
    streamable: bool

    # Set by `load_defaults`
    camera_rotation_vs_stage_xy: float
    default_binsize: int
    default_exposure: float
    dimensions: Tuple[int, int]
    interface: str
    possible_binsizes: List[int]
    stretch_amplitude: float
    stretch_azimuth: float

    @abstractmethod
    def __init__(self, name: str):
        self.name = name
        self.load_defaults()

    @abstractmethod
    def establish_connection(self):
        pass

    @abstractmethod
    def release_connection(self):
        pass

    @abstractmethod
    def get_image(
        self,
        exposure: Optional[float] = None,
        binsize: Optional[int] = None,
        **kwargs,
    ) -> np.ndarray:
        pass

    def get_movie(
        self,
        n_frames: int,
        exposure: Optional[float] = None,
        binsize: Optional[int] = None,
        **kwargs,
    ) -> List[np.ndarray]:
        """Basic implementation, subclasses should override with appropriate
        optimization."""
        return [
            self.get_image(exposure=exposure, binsize=binsize, **kwargs)
            for _ in range(n_frames)
        ]

    def __enter__(self) -> CameraBase:
        self.establish_connection()
        return self

    def __exit__(self, kind, value, traceback) -> None:
        self.release_connection()

    def get_binning(self) -> int:
        return self.default_binsize

    def get_camera_dimensions(self) -> Tuple[int, int]:
        return self.dimensions

    def get_name(self) -> str:
        return self.name

    def load_defaults(self) -> None:
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)
        for key, val in config.camera.mapping.items():
            setattr(self, key, val)
