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
        self.conn, self.tcp_listener = self.establish_connection()
        dc = self.detector_config  # noqa: loaded from a camera/file.yaml
        self.dead_time = dc['TriggerPeriod'] - dc['ExposureTime']
        self.movie_bufsize = 2 * 4 * prod(self.dimensions)
        self.null_image = np.zeros(shape=self.dimensions, dtype=np.int32)

        logger.info(f'Camera {self.get_name()} initialized')
        atexit.register(self.release_connection)

    def establish_connection(self) -> tuple[ServalCamera, socket.socket]:
        """Establish connection to the camera."""

        http_url = urlparse(self.url)  # noqa - loaded from a camera/file.yaml
        tcp_port = (http_url.port or 8080) + 1
        local_ip = _local_ip_for(http_url.hostname, tcp_port)
        tcp_base = f'tcp://connect@{local_ip}:{tcp_port}'
        http_dest = {'Base': 'http://localhost', 'Format': 'tiff', 'Mode': 'count'}
        self.tcp_dest = {'Base': tcp_base, 'Format': 'jsonimage', 'Mode': 'count'}

        f = dict(bpc_file_path=self.bpc_file_path, dacs_file_path=self.dacs_file_path)
        conn = ServalCamera()
        conn.connect(http_url.geturl())
        print(http_url.geturl())
        print(self.url)
        conn.set_chip_config_files(**f)
        conn.set_detector_config(**self.detector_config)

        # tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # tcp_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # tcp_listener.settimeout(5.0)
        # tcp_listener.bind(('0.0.0.0', tcp_port))
        # tcp_listener.listen(1)

        conn.destination = {'Image': [http_dest]}
        return conn, None # tcp_listener

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        self.conn.measurement_stop()
        # self.tcp_listener.close()
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
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            return self.null_image

        elif e > self.MAX_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            n = math.ceil(e / self.MAX_EXPOSURE)
            e = (e + self.dead_time) / n - self.dead_time
            images = list(self.get_movie(n_frames=n, exposure=e))
            return self._spliced_sum(images, exposure=e)

        logger.debug(f'Collecting a single image with exposure {exposure} s')
        print('Setting detector config')
        self.conn.set_detector_config(ExposureTime=e, TriggerPeriod=e+self.dead_time)
        print(f'Set detector config to: {self.conn.get_request('/detector/config').json()}')
        db = self.conn.dashboard
        if db['Measurement'] is None or db['Measurement']['Status'] != 'DA_RECORDING':
            print(f'Starting measurement')
            self.conn.measurement_start()
        print(f'Started measurement, getting request')
        self.conn.trigger_start()
        print(f'Started trigger, getting request')

        response = self.conn.get_request('/measurement/image')
        print(f'Got response: {response}')
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
        config file. Binning is ignored.

        n_frames: `int`
            Number of frames to collect
        exposure: `float` or `None`
            Exposure time in seconds.
        """
        logger.debug(f'Collecting {n_frames}-frame movie with {exposure=} s via TCP')
        e: float = self.default_exposure if exposure is None else exposure

        self.conn.measurement_stop()
        previous_config = self.conn.detector_config
        previous_destination = self.conn.destination
        self.conn.destination = {'Image': [self.tcp_dest]}
        self.set_detector_config(ExposureTime=e, nTriggers=n_frames)

        def _get_movie_inner() -> Iterator[np.ndarray]:  # this runs on next():
            try:
                Thread(target=self.conn.measurement_start, daemon=True).start()
                try:
                    sock, _ = self.tcp_listener.accept()
                except socket.timeout:
                    raise TimeoutError('Serval failed to connect back within 5 seconds.')
                with sock:
                    bs = self.movie_bufsize
                    yield from ServalMovieDeserializer(sock, n_frames, bs)

            finally:
                try:
                    self.conn.measurement_stop()
                except Exception as ex:
                    logger.error(f'Error stopping measurement: {ex}')
                try:
                    self.conn.destination = previous_destination
                    self.conn.set_detector_config(**previous_config)
                except Exception as ex:
                    logger.error(f'Error restoring config: {ex}')

        return _get_movie_inner()

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
