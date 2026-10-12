from __future__ import annotations

import atexit
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from json.decoder import JSONDecodeError
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

        te_name = 'simplon-trigger'
        self._te = ThreadPoolExecutor(max_workers=1, thread_name_prefix=te_name)
        atexit.register(self.release_connection)

    def _request_url(self, module: str, *params: str, timeout: int = 0) -> str:
        """Construct the SIMPLON API REST URL from params (and timeout)."""
        base = self.base_url.rstrip('/')
        url = f'{base}/{module}/api/{self.api_version}/' + '/'.join(params)
        url += f'?timeout={int(timeout)}' if timeout else ''
        return url

    def _wait4idle(self, timeout=5.0):
        """Wait until the camera is idle, or raise if timeout reached."""
        t0 = time.time()
        while self.get('detector', 'status', 'state') != 'idle':
            if time.time() - t0 > timeout:
                m = 'Detector not idle - another client may be controlling it'
                raise RuntimeError(m)
            time.sleep(0.1)

    def get(self, module: str, *params: str, timeout: int = 0) -> Any:
        """Perform a GET request on a SIMPLON parameter resource."""
        url = self._request_url(module, *params, timeout=timeout)
        r = requests.get(url)
        r.raise_for_status()
        return r.json().get('value')

    def put(self, module: str, *params: str, timeout: int = 0, value=None) -> dict:
        """Perform a PUT request to configure a SIMPLON parameter resource."""
        url = self._request_url(module, *params, timeout=timeout)
        r = requests.put(url, json={} if value is None else {'value': value})
        r.raise_for_status()
        try:
            return r.json()
        except JSONDecodeError:
            return {}

    def establish_connection(self) -> None:
        """Establish connection, initialize detector, apply initial config."""
        logger.info(f'Connecting to SIMPLON detector at {self.base_url}')

        try:
            self.put('detector', 'command', 'initialize')
        except Exception as e:
            logger.warning(f'Initialization failed or already initialized: {e}')

        self.put('monitor', 'config', 'mode', value='enabled')
        self.put('monitor', 'config', 'buffer_size', value=100)
        self.put('monitor', 'config', 'discard_new', value=False)
        self.put('detector', 'config', 'trigger_mode', value='ints')

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
        self._te.shutdown(wait=False)
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

        self._wait4idle()
        self.put('detector', 'config', 'count_time', value=e)
        self.put('detector', 'config', 'nimages', value=n_frames)

        try:
            self.put('monitor', 'command', 'clear')
        except Exception:
            pass

        self.put('detector', 'command', 'arm')
        timeout = int(1000 * (e * 2 + 1))  # s -> ms
        url = self._request_url('monitor', 'images', 'next', timeout=timeout)

        def _get_movie_inner(_n: int) -> Generator[np.ndarray]:
            """This data collection is executed lazily i.e. when iterating."""
            t_future = self._te.submit(self.put, 'detector', 'command', 'trigger')
            try:
                for i in range(_n):
                    r = requests.get(url, headers={'Accept': 'image/tiff'})
                    if r.status_code == 408:
                        msg = f'No frame {i}/{_n} received within {timeout}ms'
                        raise TimeoutError(msg)
                    r.raise_for_status()
                    yield tifffile.imread(BytesIO(r.content))
                t_future.result()  # propagate any late exception, join thread
            except Exception:
                try:
                    self.put('detector', 'command', 'abort')
                except Exception as exc:
                    logger.error(f'Error aborting after failed movie: {exc}')
                if not t_future.done():
                    try:
                        t_future.result(timeout=_n * timeout / 1000)
                    except Exception as exc:
                        logger.warning(f'Trigger did not return after abort: {exc}')
                raise

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
