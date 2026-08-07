from __future__ import annotations

import atexit
import contextlib
import json
import logging
import math
import socket
from io import BytesIO
from math import prod
from threading import Thread
from typing import Iterator, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import numpy as np
import tifffile
from serval_toolkit.camera import Camera as ServalCamera

from instamatic.camera.camera_base import CameraBase

logger = logging.getLogger(__name__)

# Start servers in serval_toolkit:
# 1. `java -jar .\emu\tpx3_emu.jar`
# 2. `java -jar .\server\serv-2.1.3.jar`
# 3. launch `instamatic`


def _local_ip_for(remote_host: str, remote_port: int) -> str:
    """Return the local IP used to reach (remote_host, remote_port)."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
        s.connect((remote_host, remote_port))
        return s.getsockname()[0]


class CameraServal(CameraBase):
    """Interfaces with Serval from ASI."""

    streamable = True
    MIN_EXPOSURE = 0.000001
    MAX_EXPOSURE = 10.0
    BAD_EXPOSURE_MSG = 'Requested exposure exceeds native Serval support (>0-10s)'

    def __init__(self, name='serval') -> None:
        """Initialize camera module."""
        super().__init__(name)

        self.tcp_dest: dict[str, str] = {}  # destination for serial movies
        self.tcp_listener: Optional[socket.socket] = None  # use tcp if not None

        dc = self.detector_config  # noqa: loaded from a camera/file.yaml
        self.dead_time = dc['TriggerPeriod'] - dc['ExposureTime']
        self.movie_bufsize = 2 * 4 * prod(self.dimensions)
        self.null_image = np.zeros(shape=self.dimensions, dtype=np.uint32)

        self.previous_config: dict = {}  # used to revert to default after movie
        self.previous_destination: dict = {}
        self.conn: ServalCamera = self.establish_connection()

        logger.info(f'Camera {self.get_name()} initialized')
        atexit.register(self.release_connection)

    def establish_connection(self) -> ServalCamera:
        """Establish cam connection; "Missing" attrs are read from config."""
        http_url = urlparse(self.url)
        f = dict(bpc_file_path=self.bpc_file_path, dacs_file_path=self.dacs_file_path)

        conn = ServalCamera()
        conn.connect(http_url.geturl())
        conn.set_chip_config_files(**f)
        conn.set_detector_config(**self.detector_config)

        try:
            tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp_listener.settimeout(1.0)
            tcp_listener.bind(('0.0.0.0', 0))
            tcp_listener.listen(1)
            tcp_port = tcp_listener.getsockname()[1]
            local_ip = _local_ip_for(http_url.hostname, tcp_port)
            tcp_base = f'tcp://connect@{local_ip}:{tcp_port}'
            self.tcp_dest = {'Base': tcp_base, 'Format': 'jsonimage', 'Mode': 'count'}
            self.conn, self.tcp_listener = conn, tcp_listener
            _ = list(self.get_movie(n_frames=1, exposure=self.MIN_EXPOSURE))
            logger.info(f'TCP movie streaming ready on {tcp_port=}')
        except OSError as exception:
            try:
                tcp_listener.close()  # noqa: NameError excepted
            except (NameError, OSError):
                pass
            self.tcp_listener = None
            logger.info(f'TCP movie streaming {exception=}, falling back to HTTP')

        http_dest = {'Base': 'http://localhost', 'Format': 'tiff', 'Mode': 'count'}
        conn.destination = {'Image': [http_dest]}
        return conn

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        self.conn.measurement_stop()
        if self.tcp_listener is not None:
            self.tcp_listener.close()
        msg = f"Connection to camera '{self.get_name()}' released"
        logger.info(msg)

    def set_detector_config(self, **kwargs) -> None:
        """Set detector config while infering about missing config params."""
        if 'TriggerMode' not in kwargs:
            tm = 'AUTOTRIGSTART_TIMERSTOP' if self.dead_time else 'CONTINUOUS'
            kwargs['TriggerMode'] = tm
        if 'TriggerPeriod' not in kwargs and 'ExposureTime' in kwargs:
            kwargs['TriggerPeriod'] = kwargs['ExposureTime'] + self.dead_time
        self.conn.set_detector_config(**kwargs)

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Image acquisition interface. If the exposure is not given, the
        default value is read from the config file. Binning is ignored.

        exposure: `float` or `None`
            Exposure time in seconds.
        """
        e: float = self.default_exposure if exposure is None else exposure

        if e < self.MIN_EXPOSURE:
            logger.warning('%s: %g', self.BAD_EXPOSURE_MSG, e)
            return self.null_image

        elif e > self.MAX_EXPOSURE:
            logger.warning('%s: %g', self.BAD_EXPOSURE_MSG, e)
            n = math.ceil(e / self.MAX_EXPOSURE)
            e = (e + self.dead_time) / n - self.dead_time
            images = list(self.get_movie(n_frames=n, exposure=e))
            return self._spliced_sum(images, exposure=e)

        logger.debug(f'Collecting a single image with exposure {exposure} s')
        self.conn.set_detector_config(ExposureTime=e, TriggerPeriod=e + self.dead_time)
        db = self.conn.dashboard
        if db['Measurement'] is None or db['Measurement']['Status'] != 'DA_RECORDING':
            self.conn.measurement_start()
        self.conn.trigger_start()

        response = self.conn.get_request('/measurement/image')
        return tifffile.imread(BytesIO(response.content))

    def _spliced_sum(self, arrays: Sequence[np.ndarray], exposure: float) -> np.ndarray:
        """Sum a series of arrays while applying a dead time correction."""
        array_sum = sum(arrays, np.zeros_like(arrays[0]))
        total_exposure = len(arrays) * exposure + (len(arrays) - 1) * self.dead_time
        live_fraction = len(arrays) * exposure / total_exposure
        return (array_sum / live_fraction).astype(arrays[0].dtype)

    def get_movie(
        self, n_frames: int, exposure: Optional[float] = None, **kwargs
    ) -> Iterator[np.ndarray]:
        """Yield `n_frames` images received via a TCP stream with minimal dead
        time. If the exposure is not given, the default value is read from the
        config file. Binning is ignored. Setup is eager, iteration is delayed.

        n_frames: `int`
            Number of frames to collect
        exposure: `float` or `None`
            Exposure time in seconds.
        """
        logger.debug(f'Collecting {n_frames}-frame movie with {exposure=} s')
        e: float = self.default_exposure if exposure is None else exposure
        self.conn.measurement_stop()

        get_movie = self._get_movie_tcp if self.tcp_listener else self._get_movie_http
        return get_movie(n_frames=n_frames, exposure=e)

    def _get_movie_http(self, n_frames: int, exposure: float) -> Iterator[np.ndarray]:
        """Fallback method, polls frames from HTTP if TCP start-up failed."""
        self.previous_config = self.conn.detector_config
        self.set_detector_config(ExposureTime=exposure, nTriggers=n_frames)
        return self._get_movie_inner(n_frames=n_frames, use_tcp=False)

    def _get_movie_tcp(self, n_frames: int, exposure: float) -> Iterator[np.ndarray]:
        """Fast method, reads frames directly from TCP stream if available."""
        self.previous_config = self.conn.detector_config
        self.previous_destination = self.conn.destination
        self.conn.destination = {'Image': [self.tcp_dest]}
        self.set_detector_config(ExposureTime=exposure, nTriggers=n_frames)
        return self._get_movie_inner(n_frames=n_frames, use_tcp=True)

    def _get_movie_inner(self, n_frames: int, use_tcp: bool) -> Iterator[np.ndarray]:
        """Movie frame iterator, isolated from config for max performance."""
        try:
            Thread(target=self.conn.measurement_start, daemon=True).start()
            if use_tcp:
                try:
                    sock, _ = self.tcp_listener.accept()
                except socket.timeout:
                    raise TimeoutError('Serval failed to connect back within 1s.')
                with sock:
                    bs = self.movie_bufsize
                    yield from ServalMovieDeserializer(sock, n_frames, bs)
            else:
                for _ in range(n_frames):
                    response = self.conn.get_request('/measurement/image')
                    yield tifffile.imread(BytesIO(response.content))
        finally:
            try:
                self.conn.measurement_stop()
            except Exception as ex:
                logger.error(f'Error stopping measurement: {ex}')
            try:
                self.conn.set_detector_config(**self.previous_config)
                if use_tcp:
                    self.conn.destination = self.previous_destination
            except Exception as ex:
                logger.error(f'Error restoring config and destination: {ex}')

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)


class ServalMovieDeserializer(Iterator[np.ndarray]):
    """Deserializes Serval camera TCP byte stream from socket into images."""

    def __init__(self, sock: socket.socket, n_frames: int, bufsize: int) -> None:
        self.sock: socket.socket = sock
        self.buffer = bytearray(bufsize)
        self.view = memoryview(self.buffer)
        self.used: int = 0
        self.i_frame: int = 0
        self.n_frames: int = n_frames
        self.shape: tuple[int, int] = (0, 0)
        self.size: int = 0
        self.dtype: np.dtype = np.dtype(np.uint32)

    def _receive_more(self) -> None:
        """Attempt to receive bytes from the socket into free buffer space."""
        recv_len = self.sock.recv_into(self.view[self.used :])
        if not recv_len:
            raise EOFError
        self.used += recv_len

    def _receive_until(self, token: bytes) -> int:
        """Recv data until `token` is found, return index after the token."""
        while True:
            token_idx = self.buffer.find(token, 0, self.used)
            if token_idx >= 0:
                return token_idx + len(token)
            self._receive_more()

    def _parse_header(self, header_size: int) -> None:
        """Read shape, size, dtype of all images from the 1st frame header."""
        header_str = self.buffer[:header_size].decode('utf-8')
        header_dict = json.loads(header_str)
        bit_depth = header_dict['bitDepth']
        self.shape = header_dict['height'], header_dict['width']
        self.dtype = np.dtype(f'uint{bit_depth}').newbyteorder('>')
        self.size = header_dict.get('dataSize', prod(self.shape) * self.dtype.itemsize)

    def __next__(self) -> np.ndarray:
        """Recv as much data as needed, return next frame from TCP stream."""
        if self.i_frame >= self.n_frames:
            raise StopIteration
        header_end = self._receive_until(b'}') + 1
        if self.i_frame == 0:
            self._parse_header(header_end)
        while self.used < header_end + self.size:
            self._receive_more()
        i, j = header_end, header_end + self.size
        frame = np.frombuffer(self.buffer[i:j], dtype=self.dtype).reshape(self.shape).copy()

        self.buffer[: self.used - j] = self.buffer[j : self.used]
        self.used -= j
        self.i_frame += 1
        return frame


if __name__ == '__main__':
    cam = CameraServal()
    from IPython import embed

    embed()
