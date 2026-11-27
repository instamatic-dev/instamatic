"""DECTRIS SIMPLON API: needs requests, pyzmq, cbor2, dectris-compression."""

from __future__ import annotations

import atexit
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from json.decoder import JSONDecodeError
from threading import Lock
from typing import Any, Generator, Optional, Union
from urllib.parse import urlparse

import cbor2
import numpy as np
import requests
import zmq
from dectris.compression import decompress

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)


@dataclass
class _AcquisitionState:
    """Isolates state of image acquisition for optimized arm/trigger use."""

    socket: Optional[zmq.Socket] = None
    armed: bool = False  # armed, "end" message not yet received
    exposure: Optional[float] = None
    triggers_left: int = 0
    lock: Lock = field(default_factory=Lock)

    def can_reuse_trigger(self, exposure: float) -> bool:
        return bool(self.armed and self.exposure == exposure and self.triggers_left)


class _Decoder:
    """Use CBOR to decode DECTRIS Simplon stream V2 msg; Based on an example:

    https://github.com/dectris/documentation/blob/main/stream_v2/examples/client.py.
    """

    _TYPED_ARRAY_DTYPES = {
        64: 'u1', 65: '>u2', 66: '>u4', 67: '>u8',
        68: 'u1', 69: '<u2', 70: '<u4', 71: '<u8',
        72: 'i1', 73: '>i2', 74: '>i4', 75: '>i8',
        77: '<i2', 78: '<i4', 79: '<i8',
        80: '>f2', 81: '>f4', 82: '>f8',
        84: '<f2', 85: '<f4', 86: '<f8',
    }  # fmt: skip

    @staticmethod
    def _decode_multi_dim_array(tag: cbor2.CBORTag, column_major: bool) -> np.ndarray:
        dimensions, contents = tag.value
        if isinstance(contents, list):
            array = np.empty((len(contents),), dtype=object)
            array[:] = contents
        elif isinstance(contents, (np.ndarray, np.generic)):
            array = contents
        else:
            raise cbor2.CBORDecodeError('expected array or typed array')
        return array.reshape(dimensions, order='F' if column_major else 'C')

    @staticmethod
    def _decode_typed_array(tag: cbor2.CBORTag, dtype: str) -> np.ndarray:
        if not isinstance(tag.value, bytes):
            raise cbor2.CBORDecodeError('expected byte string in typed array')
        return np.frombuffer(tag.value, dtype=dtype)

    @staticmethod
    def _decode_dectris_compression(tag: cbor2.CBORTag) -> np.ndarray:
        algorithm, elem_size, encoded = tag.value
        return decompress(encoded, algorithm, elem_size=elem_size)

    @staticmethod
    def tag_hook(tag: cbor2.CBORTag, *_) -> Union[cbor2.CBORTag, np.ndarray]:
        if tag.tag == 40:
            return _Decoder._decode_multi_dim_array(tag, column_major=False)
        if tag.tag == 1040:
            return _Decoder._decode_multi_dim_array(tag, column_major=True)
        if tag.tag == 56500:
            return _Decoder._decode_dectris_compression(tag)
        dtype = _Decoder._TYPED_ARRAY_DTYPES.get(tag.tag)
        return _Decoder._decode_typed_array(tag, dtype) if dtype else tag


class CameraSimplon(CameraBase):
    """Interfaces with Dectris detectors via the SIMPLON REST-like API.

    Commands and settings go through HTTP (SIMPLON API). Images are received
    through the Stream V2 interface (ZeroMQ + CBOR), with internal triggers.

    - `get_image`: the detector is armed once with `nimages=1` and a large
      `ntrigger`; as long as the exposure does not change, each call only sends
      one trigger. A change of exposure cancels the series and arms a new one.
    - `get_movie`: armed with `nimages=n_frames`, `ntrigger=1`; one trigger
      starts back-to-back acquisition and the frames are yielded as they arrive.
    """

    streamable = True
    MIN_EXPOSURE = 0.001
    MAX_EXPOSURE = 60.0
    BAD_EXPOSURE_MSG = 'Requested exposure is out of supported range (1ms-1min)'

    MAX_N_TRIGGERS = 2**16
    DEFAULT_STREAM_PORT = 31001
    STREAM_TIMEOUT = 5.0  # s, extra wait for a message on top of the exposure

    def __init__(self, name: str = 'simplon') -> None:
        """Initialize camera module, vars, establish connection & cleanup."""
        super().__init__(name)

        self.base_url = getattr(self, 'url', 'http://localhost:8000/')
        self.api_version = getattr(self, 'api_version', '1.8.0')

        host = urlparse(self.base_url).hostname or 'localhost'
        port = getattr(self, 'stream_port', self.DEFAULT_STREAM_PORT)
        self.stream_url = getattr(self, 'stream_url', f'tcp://{host}:{port}')

        self.acq = _AcquisitionState()
        te_name = 'simplon-trigger'
        self._te = ThreadPoolExecutor(max_workers=1, thread_name_prefix=te_name)

        self.establish_connection()
        logger.info(f'Camera {self.get_name()} initialized via SIMPLON API')

        atexit.register(self.release_connection)

    def _request_url(self, module: str, *params: str) -> str:
        """Construct the SIMPLON API REST URL from params."""
        base = self.base_url.rstrip('/')
        return f'{base}/{module}/api/{self.api_version}/' + '/'.join(params)

    def _wait4idle(self, timeout: float = 5.0) -> None:
        """Wait until the camera is idle, or raise if timeout (s) reached."""
        t0 = time.time()
        while self.get('detector', 'status', 'state') != 'idle':
            if time.time() - t0 > timeout:
                m = 'Detector not idle - another client may be controlling it'
                raise RuntimeError(m)
            time.sleep(0.1)

    def get(self, module: str, *params: str, timeout: Optional[float] = None) -> Any:
        """Perform a GET request on a SIMPLON parameter resource."""
        url = self._request_url(module, *params)
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json().get('value')

    def put(
        self, module: str, *params: str, value: Any = None, timeout: Optional[float] = None
    ) -> dict[str, Any]:
        """Perform a PUT request to configure a SIMPLON parameter resource."""
        url = self._request_url(module, *params)
        json = {} if value is None else {'value': value}
        r = requests.put(url, json=json, timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except JSONDecodeError:
            return {}

    def establish_connection(self) -> None:
        """Initialize detector, apply config, and connect to stream."""
        logger.info(f'Connecting to SIMPLON detector at {self.base_url}')

        self.acq.socket = zmq.Context.instance().socket(zmq.PULL)
        self.acq.socket.setsockopt(zmq.RCVHWM, 0)  # queue instead of dropping
        self.acq.socket.connect(self.stream_url)
        logger.info(f'Listening to stream at {self.stream_url}')

        try:
            state = self.get('detector', 'status', 'state')
        except Exception as e:
            logger.warning(f'Could not read detector state: {e}')
            state = 'na'

        if state in ('na', 'error'):  # after power-up / service restart only
            try:
                self.put('detector', 'command', 'initialize', timeout=300)
            except Exception as e:
                logger.warning(f'Initialization failed: {e}')

        self.put('stream', 'config', 'mode', value='enabled')
        self.put('stream', 'config', 'format', value='cbor')
        self.put('detector', 'config', 'trigger_mode', value='ints')

        detector_config = getattr(self, 'detector_config', {})
        for key, value in detector_config.items():
            try:
                self.put('detector', 'config', key, value=value)
                logger.debug(f'Set detector config {key} = {value}')
            except Exception as e:
                logger.error(f'Failed to set detector config {key} = {value}: {e}')

    def release_connection(self) -> None:
        """Release connection, stop any series, disable the stream."""
        try:
            self._stop_series()
        except Exception:
            pass
        try:
            self.put('stream', 'config', 'mode', value='disabled')
        except Exception:
            pass
        if self.acq.socket is not None:
            self.acq.socket.close(linger=0)
            self.acq.socket = None
        self._te.shutdown(wait=False)
        logger.info(f"Connection to camera '{self.get_name()}' released")

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STREAM HELPERS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _recv(self, timeout: float) -> dict[str, Any]:
        """Receive & decode the next stream message or raise TimeoutError."""
        if not self.acq.socket.poll(int(timeout * 1000)):
            raise TimeoutError(f'No stream message received within {timeout:.1f} s')
        return cbor2.loads(self.acq.socket.recv(), tag_hook=_Decoder.tag_hook)

    def _read_image(self, timeout: float) -> tuple[np.ndarray, int]:
        """Return (image, image_id) of the next image msg in the stream."""
        while True:  # may receive 'start' (ignored)
            message = self._recv(timeout)
            mtype = message['type']
            if mtype == 'image':
                image = next(iter(message['data'].values()))
                return image, message['image_id']
            if mtype == 'end':
                self.acq.armed = False
                raise RuntimeError('Stream series ended before the expected image')

    def _drain_until_end(self, timeout: float = 5.0) -> None:
        """Discard stream messages until the 'end' message of the series."""
        try:
            while self._recv(timeout)['type'] != 'end':
                pass
        except TimeoutError:
            logger.warning("No 'end' message received from stream while closing series")
        self.acq.armed = False

    def _stop_series(self, abort: bool = False, pending: Optional[Future] = None) -> None:
        """Stop the current series (if any) and flush its stream messages."""
        command = 'abort' if abort else 'disarm'
        if self.acq.armed:
            try:
                self.put('detector', 'command', command, timeout=30)
            except Exception as exc:
                logger.debug(f'{command} failed ({exc}), trying abort')
                try:
                    self.put('detector', 'command', 'abort', timeout=30)
                except Exception as exc:
                    logger.error(f'Error aborting series: {exc}')
            if pending is not None:
                try:
                    pending.result(timeout=30)
                except Exception as exc:
                    logger.warning(f'Trigger did not return after {command}: {exc}')
            self._drain_until_end()

        self.acq.armed = False
        self.acq.exposure = None
        self.acq.triggers_left = 0

    def _check_exposure(self, e: float) -> None:
        if e < self.MIN_EXPOSURE or e > self.MAX_EXPOSURE:
            raise ValueError(f'{self.BAD_EXPOSURE_MSG}: {e}s')

    def _arm(self, exposure: float, n_images: int, n_trigger: int) -> None:
        """Configure and arm the detector; previous series must be stopped."""
        self._wait4idle()
        self.put('detector', 'config', 'count_time', value=exposure)
        self.put('detector', 'config', 'frame_time', value=exposure)
        self.put('detector', 'config', 'nimages', value=n_images)
        self.put('detector', 'config', 'ntrigger', value=n_trigger)
        self.put('detector', 'command', 'arm', timeout=60)
        self.acq.armed = True

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~ HIGH-LEVEL INTERFACE ~~~~~~~~~~~~~~~~~~~~~~~~~~

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Acquire a single image with specified exposure time via stream.

        The detector stays armed for `MAX_N_TRIGGERS` (one image each).
        If called again with the same exposure, only a trigger is sent.
        Otherwise, the running series is cancelled and a new one is
        armed.
        """
        e = self.default_exposure if exposure is None else exposure
        self._check_exposure(e)

        self.acq.lock.acquire()
        try:
            if not self.acq.can_reuse_trigger(exposure=e):
                logger.debug(f'Arming for single images with exposure {e} s')
                self._stop_series()
                self._arm(e, n_images=1, n_trigger=self.MAX_N_TRIGGERS)
                self.acq.exposure = e
                self.acq.triggers_left = self.MAX_N_TRIGGERS

            self.put('detector', 'command', 'trigger', timeout=e + 30)
            self.acq.triggers_left -= 1
            image, _ = self._read_image(timeout=e + self.STREAM_TIMEOUT)
        except Exception:
            try:
                self._stop_series(abort=True)
            except Exception as exc:
                logger.error(f'Error stopping series after failed get_image: {exc}')
            raise
        finally:
            self.acq.lock.release()

        return image

    def get_movie(
        self,
        n_frames: int = 1,
        exposure: Optional[float] = None,
        **kwargs: Any,
    ) -> Generator[np.ndarray]:
        """Eagerly configure, lazily yield `n_frames` with `exposure`."""
        e = self.default_exposure if exposure is None else exposure
        self._check_exposure(e)
        logger.debug(f'Collecting {n_frames} images with exposure {e} s')

        self._stop_series()
        self._arm(e, n_images=n_frames, n_trigger=1)
        self.acq.triggers_left = 0

        def _get_movie_inner(_n: int) -> Generator[np.ndarray]:
            """Data collection is executed lazily, only when iterating."""
            timeout = e + self.STREAM_TIMEOUT
            kw = ('detector', 'command', 'trigger')
            self.acq.lock.acquire()
            completed = False
            t_future: Future = self._te.submit(self.put, *kw, timeout=_n * e + 30)
            try:
                for i in range(_n):
                    image, image_id = self._read_image(timeout)
                    if image_id != i:
                        msg = f'Frame {i}/{_n} expected, received image_id {image_id}'
                        raise RuntimeError(msg)
                    yield image
                t_future.result()  # propagate any late exception, join thread
                self._drain_until_end()  # consume the 'end' message
                completed = True
            finally:
                if not completed:  # error or generator closed early
                    self._stop_series(abort=True, pending=t_future)
                self.acq.lock.release()

        return _get_movie_inner(n_frames)

    def get_image_dimensions(self) -> tuple[int, int]:
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
