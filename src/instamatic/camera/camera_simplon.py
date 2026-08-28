from __future__ import annotations

import atexit
import logging
from io import BytesIO
from typing import Any, Generator, Optional, Tuple

import numpy as np
import requests
import tifffile

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)


class CameraSimplon(CameraBase):
    """Interfaces with Dectris detectors via the SIMPLON REST-like API."""

    streamable = True
    MIN_EXPOSURE = 0.0001
    MAX_EXPOSURE = 60.0
    BAD_EXPOSURE_MSG = 'Requested exposure is out of supported range (>0-1m)'

    def __init__(self, name='dectris') -> None:
        """Initialize camera module, vars, establish connection & cleanup."""
        super().__init__(name)

        self.base_url = getattr(self, 'url', 'http://localhost:8000/')
        self.api_version = getattr(self, 'api_version', '1.8.0')

        self.establish_connection()
        logger.info(f'Camera {self.get_name()} initialized via SIMPLON API')
        atexit.register(self.release_connection)

    def _request_url(self, module: str, *params: str, timeout: int = 0) -> str:
        """Construct the SIMPLON API REST URL from params (and timeout)."""
        base = self.base_url.rstrip('/')
        url = f'{base}/{module}/api/{self.api_version}/' + '/'.join(params)
        url += f'?timeout={int(timeout)}' if timeout else ''
        return url

    def get(self, module: str, *params: str, timeout: int = 0) -> Any:
        """Perform a GET request on a SIMPLON parameter resource."""
        url = self._request_url(module, *params, timeout=timeout)
        r = requests.get(url)
        r.raise_for_status()
        return r.json().get('value')

    def put(self, module: str, *params: str, timeout: int = 0, value=None) -> Any:
        """Perform a PUT request to configure a SIMPLON parameter resource."""
        url = self._request_url(module, *params, timeout=timeout)
        r = requests.put(url, json={} if value is None else {'value': value})
        r.raise_for_status()
        return r.json()

    def establish_connection(self) -> None:
        """Establish connection, initialize detector, apply initial config."""
        logger.info(f'Connecting to SIMPLON detector at {self.base_url}')

        try:
            self.put('detector', 'command', 'initialize')
        except Exception as e:
            logger.warning(f'Initialization failed or already initialized: {e}')

        try:
            self.put('monitor', 'config', 'mode', 'enabled')
            self.put('monitor', 'config', 'buffer_size', value=100)
            self.put('monitor', 'config', 'discard_new', value=False)
        except Exception as e:
            logger.warning(f'Could not configure monitor interface: {e}')

        detector_config = getattr(self, 'detector_config', {})
        for key, value in detector_config.items():
            try:
                self.put('detector', 'config', key, value=value)
                logger.debug(f'Set detector config {key} = {value}')
            except Exception as e:
                logger.error(f'Failed to set detector config {key} = {value}: {e}')

    def release_connection(self) -> None:
        """Release connection, disarm the detector, disable the monitor."""
        try:
            self.put('detector', 'command', 'disarm')
        except Exception:
            pass
        try:
            self.put('monitor', 'config', 'mode', value='disabled')
        except Exception:
            pass
        logger.info(f"Connection to camera '{self.get_name()}' released")

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Acquire a single image with specified exposure time via monitor."""
        return list(self.get_movie(1, exposure=exposure))[0]

    def get_movie(
        self,
        n_frames: int = 1,
        exposure: Optional[float] = None,
        **kwargs: Any,
    ) -> Generator[np.ndarray]:
        """Eagerly configure, lazily yield `n_frames` with `exposure`."""
        e = self.default_exposure if exposure is None else exposure

        if e < self.MIN_EXPOSURE or e > self.MAX_EXPOSURE:
            raise ValueError(f'{self.BAD_EXPOSURE_MSG}: {e}s')
        logger.debug(f'Collecting {n_frames} images with exposure {e} s')

        self.put('detector', 'config', 'count_time', value=e)
        self.put('detector', 'config', 'nimages', value=n_frames)
        self.put('detector', 'config', 'ntrigger', value=1)
        self.put('detector', 'config', 'trigger_mode', value='ints')

        try:
            self.put('monitor', 'command', 'clear')
        except Exception:
            pass

        self.put('detector', 'command', 'arm')
        timeout = int(self.MAX_EXPOSURE)
        url = self._request_url('monitor', 'images', 'next', timeout=timeout)

        def _get_movie_inner(_n: int) -> Generator[np.ndarray]:
            """This data collection is executed lazily i.e. when iterating."""
            self.put('detector', 'command', 'trigger')
            try:
                for _ in range(_n):
                    r = requests.get(url, headers={'Accept': 'image/tiff'})
                    r.raise_for_status()
                    yield tifffile.imread(BytesIO(r.content))
            finally:
                try:
                    self.put('detector', 'command', 'disarm')
                except Exception as exc:
                    logger.error(f'Error disarming detector after movie: {exc}')

        return _get_movie_inner(n_frames)

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        try:
            dim_x = int(self.get('detector', 'config', 'x_pixels_in_detector'))
            dim_y = int(self.get('detector', 'config', 'y_pixels_in_detector'))
        except Exception:
            dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    cam = CameraSimplon()
    print('SIMPLON camera initialized successfully.')
