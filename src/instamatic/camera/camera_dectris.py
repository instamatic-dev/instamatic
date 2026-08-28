from __future__ import annotations

import atexit
import logging
from io import BytesIO
from typing import Any, Iterator, Optional, Tuple

import numpy as np
import requests
import tifffile

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)


class CameraDectris(CameraBase):
    """Interfaces with Dectris detectors via the SIMPLON REST-like API."""

    streamable = True
    MIN_EXPOSURE = 0.0001
    MAX_EXPOSURE = 3600.0

    def __init__(self, name='dectris') -> None:
        """Initialize camera module, vars, establish connection & cleanup."""
        super().__init__(name)

        # Base URL for the SIMPLON API (e.g., http://10.42.41.10 or http://localhost)
        self.base_url = (
            getattr(self, 'url', None) or f'http://{getattr(self, "host", "localhost")}'
        )
        self.api_version = getattr(self, 'api_version', '1.8.0')

        self.establish_connection()
        logger.info(f'Camera {self.get_name()} initialized via SIMPLON API')
        atexit.register(self.release_connection)

    def _request_url(self, module: str, task: str, endpoint: str = '') -> str:
        """Construct the SIMPLON API REST URL."""
        base = self.base_url.rstrip('/')
        if endpoint:
            return f'{base}/{module}/api/{self.api_version}/{task}/{endpoint}'
        else:
            return f'{base}/{module}/api/{self.api_version}/{task}'

    def get_param(self, module: str, task: str, param: str) -> Any:
        """Perform a GET request on a SIMPLON parameter resource."""
        url = self._request_url(module, task, param)
        r = requests.get(url)
        r.raise_for_status()
        return r.json().get('value')

    def set_param(self, module: str, task: str, param: str, value: Any) -> Any:
        """Perform a PUT request to configure a SIMPLON parameter resource."""
        url = self._request_url(module, task, param)
        r = requests.put(url, json={'value': value})
        r.raise_for_status()
        return r.json()

    def send_command(self, module: str, command: str, data: Optional[dict] = None) -> Any:
        """Send a control command via a PUT request to the SIMPLON API."""
        url = self._request_url(module, 'command', command)
        r = requests.put(url, json=data if data is not None else {})
        r.raise_for_status()
        return r.json() if r.content else None

    def establish_connection(self) -> None:
        """Establish connection, initialize detector, and apply initial
        configuration."""
        logger.info(f'Connecting to Dectris detector at {self.base_url}')

        # 1. Initialize detector (mandatory once after power-up or service restart)
        try:
            self.send_command('detector', 'initialize')
        except Exception as e:
            logger.warning(f'Detector initialization notice or already initialized: {e}')

        # 2. Enable monitor interface for image retrieval
        try:
            self.set_param('monitor', 'config', 'mode', 'enabled')
            self.set_param('monitor', 'config', 'buffer_size', 100)
            self.set_param('monitor', 'config', 'discard_new', False)
        except Exception as e:
            logger.warning(f'Could not configure monitor interface: {e}')

        # 3. Apply detector configuration parameters from object scope / config files
        detector_config = getattr(self, 'detector_config', {})
        for key, value in detector_config.items():
            try:
                self.set_param('detector', 'config', key, value)
                logger.debug(f'Set detector config {key} = {value}')
            except Exception as e:
                logger.error(f'Failed to set detector config {key} = {value}: {e}')

    def release_connection(self) -> None:
        """Release connection, disarm the detector, and disable the monitor."""
        try:
            self.send_command('detector', 'disarm')
        except Exception:
            pass
        try:
            self.set_param('monitor', 'config', 'mode', 'disabled')
        except Exception:
            pass
        logger.info(f"Connection to camera '{self.get_name()}' released")

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Acquire a single image with the specified exposure time."""
        e = self.default_exposure if exposure is None else exposure

        if e < self.MIN_EXPOSURE or e > self.MAX_EXPOSURE:
            raise ValueError(
                f'Requested exposure {e}s is out of supported range ({self.MIN_EXPOSURE}-{self.MAX_EXPOSURE}s)'
            )

        logger.debug(f'Collecting single image with exposure {e} s')

        # Configure acquisition parameters
        self.set_param('detector', 'config', 'count_time', e)
        self.set_param('detector', 'config', 'frame_time', e + 0.001)
        self.set_param('detector', 'config', 'nimages', 1)
        self.set_param('detector', 'config', 'ntrigger', 1)
        self.set_param('detector', 'config', 'trigger_mode', 'ints')

        # Clear monitor buffer
        try:
            self.send_command('monitor', 'clear')
        except Exception:
            pass

        # Arm and trigger acquisition
        self.send_command('detector', 'arm')
        self.send_command('detector', 'trigger')

        # Retrieve image from the monitor interface as TIFF
        url = self._request_url('monitor', 'images', 'next') + '?timeout=5000'
        r = requests.get(url, headers={'Accept': 'image/tiff'})
        r.raise_for_status()
        image = tifffile.imread(BytesIO(r.content))

        # Disarm detector
        try:
            self.send_command('detector', 'disarm')
        except Exception:
            pass

        return image

    def get_movie(
        self, n_frames: int, exposure: Optional[float] = None, **kwargs
    ) -> Iterator[np.ndarray]:
        """Acquire a movie of `n_frames` with the specified exposure time."""
        e = self.default_exposure if exposure is None else exposure

        logger.debug(f'Collecting {n_frames}-frame movie with exposure {e} s')

        self.set_param('detector', 'config', 'count_time', e)
        self.set_param('detector', 'config', 'frame_time', e + 0.001)
        self.set_param('detector', 'config', 'nimages', n_frames)
        self.set_param('detector', 'config', 'ntrigger', 1)
        self.set_param('detector', 'config', 'trigger_mode', 'ints')

        try:
            self.send_command('monitor', 'clear')
        except Exception:
            pass

        self.send_command('detector', 'arm')
        self.send_command('detector', 'trigger')

        try:
            for _ in range(n_frames):
                url = self._request_url('monitor', 'images', 'next') + '?timeout=10000'
                r = requests.get(url, headers={'Accept': 'image/tiff'})
                r.raise_for_status()
                yield tifffile.imread(BytesIO(r.content))
        finally:
            try:
                self.send_command('detector', 'disarm')
            except Exception as ex:
                logger.error(f'Error disarming detector after movie: {ex}')

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        try:
            dim_x = int(self.get_param('detector', 'config', 'x_pixels_in_detector'))
            dim_y = int(self.get_param('detector', 'config', 'y_pixels_in_detector'))
        except Exception:
            dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    cam = CameraDectris()
    print('Dectris camera initialized successfully.')
