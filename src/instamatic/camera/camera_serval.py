from __future__ import annotations

import atexit
import contextlib
import json
import logging
import math
import socket
import threading
from io import BytesIO
from itertools import batched
from math import prod
from typing import Generator, Iterator, List, Optional, Sequence, Tuple, Union
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

Ignore = object()  # sentinel object: informs `_get_images` to get a single image


class CameraServal(CameraBase):
    """Interfaces with Serval from ASI."""

    streamable = True
    MIN_EXPOSURE = 0.000001
    MAX_EXPOSURE = 10.0
    BAD_EXPOSURE_MSG = 'Requested exposure exceeds native Serval support (>0-10s)'

    def __init__(self, name='serval'):
        """Initialize camera module."""
        super().__init__(name)
        self.establish_connection()
        self.dead_time = (
            self.detector_config['TriggerPeriod'] - self.detector_config['ExposureTime']
        )
        self.movie_bufsize = 2 * 4 * prod(self.dimensions)
        logger.info(f'Camera {self.get_name()} initialized')
        atexit.register(self.release_connection)

    @staticmethod
    def _local_ip_for(remote_host: str, remote_port: int) -> str:
        """Return the local IP used to reach (remote_host, remote_port)."""
        # UDP "connect" does not send packets, but lets the OS choose interface/IP.
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
            s.connect((remote_host, remote_port))
            return s.getsockname()[0]

    def get_image(self, exposure: Optional[float] = None, **kwargs) -> np.ndarray:
        """Image acquisition interface. If the exposure is not given, the
        default value is read from the config file. Binning is ignored.

        exposure: `float` or `None`
            Exposure time in seconds.
        """
        return self._get_images(n_frames=Ignore, exposure=exposure, **kwargs)

    def _get_images(
        self,
        n_frames: Union[int, Ignore],
        exposure: Optional[float] = None,
        **kwargs,
    ) -> Union[np.ndarray, List[np.ndarray]]:
        """General media acquisition dispatcher for other protected methods."""
        n: int = 1 if n_frames is Ignore else n_frames
        e: float = self.default_exposure if exposure is None else exposure

        if n_frames == 0:  # single image is communicated via n_frames = Ignore
            return []

        elif e < self.MIN_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            if n_frames is Ignore:
                return self._get_image_null(exposure=e, **kwargs)
            return [self._get_image_null(exposure=e, **kwargs) for _ in range(n)]

        elif e > self.MAX_EXPOSURE:
            logger.warning('%s: %d', self.BAD_EXPOSURE_MSG, e)
            n1 = math.ceil(e / self.MAX_EXPOSURE)
            e = (e + self.dead_time) / n1 - self.dead_time
            images = self._get_image_stack(n_frames=n * n1, exposure=e, **kwargs)
            if n_frames is Ignore:
                return self._spliced_sum(images, exposure=e)
            return [self._spliced_sum(i, exposure=e) for i in batched(images, n1)]

        else:  # if exposure is within limits
            if n_frames is Ignore:
                return self._get_image_single(exposure=e, **kwargs)
            return self._get_image_stack(n_frames=n, exposure=e, **kwargs)

    def _spliced_sum(self, arrays: Sequence[np.ndarray], exposure: float) -> np.ndarray:
        """Sum a series of arrays while applying a dead time correction."""
        array_sum = sum(arrays, np.zeros_like(arrays[0]))
        total_exposure = len(arrays) * exposure + (len(arrays) - 1) * self.dead_time
        live_fraction = len(arrays) * exposure / total_exposure
        return (array_sum / live_fraction).astype(arrays[0].dtype)

    def _get_image_null(self, **_) -> np.ndarray:
        logger.debug('Creating a synthetic image with zero counts')
        return np.zeros(shape=self.get_image_dimensions(), dtype=np.int32)

    def _get_image_single(self, exposure: float, **_) -> np.ndarray:
        """Request a single frame in the mode in a trigger collection mode."""
        logger.debug(f'Collecting a single image with exposure {exposure} s')
        self.conn.set_detector_config(
            ExposureTime=exposure,
            TriggerPeriod=exposure + self.dead_time,
        )
        db = self.conn.dashboard
        if db['Measurement'] is None or db['Measurement']['Status'] != 'DA_RECORDING':
            self.conn.measurement_start()
        self.conn.trigger_start()
        response = self.conn.get_request('/measurement/image')
        return tifffile.imread(BytesIO(response.content))

    def _get_image_stack(self, n_frames: int, exposure: float, **_) -> list[np.ndarray]:
        """Get a series of images in a mode with minimal dead time."""
        return list(self.get_movie(n_frames=n_frames, exposure=exposure))

    def get_movie(
        self, n_frames: int, exposure: Optional[float] = None, **kwargs
    ) -> Generator[np.ndarray, None, None]:
        """Yield `n_frames` images received via a TCP stream with minimal dead
        time. If the exposure is not given, the default value is read from the
        config file. Binning is ignored.

        n_frames: `int`
            Number of frames to collect
        exposure: `float` or `None`
            Exposure time in seconds.
        """
        logger.debug(f'Collecting {n_frames}-frame movie with exposure {exposure} s via TCP')
        mode: str = 'AUTOTRIGSTART_TIMERSTOP' if self.dead_time else 'CONTINUOUS'
        exposure: float = self.default_exposure if exposure is None else exposure

        http_url = urlparse(self.conn.url)
        tcp_port = (http_url.port or 8080) + 1
        local_ip = self._local_ip_for(http_url.hostname, tcp_port)
        tcp_base = f'tcp://connect@{local_ip}:{tcp_port}'
        tcp_dest = {'Base': tcp_base, 'Format': 'jsonimage', 'Mode': 'count'}

        self.conn.measurement_stop()
        previous_config = self.conn.detector_config
        previous_destination = self.conn.destination

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(5.0)
        try:
            listener.bind(('0.0.0.0', tcp_port))
            listener.listen(1)
            self.conn.destination = {
                'Image': [
                    tcp_dest,
                ]
            }
            self.conn.set_detector_config(
                TriggerMode=mode,
                ExposureTime=exposure,
                TriggerPeriod=exposure + self.dead_time,
                nTriggers=n_frames,
            )
            threading.Thread(target=self.conn.measurement_start, daemon=True).start()
            try:
                sock, addr = listener.accept()
            except socket.timeout:
                raise TimeoutError('Serval failed to connect back within 5 seconds.')
            with sock:
                yield from ServalMovieDeserializer(sock, n_frames, self.movie_bufsize)

        finally:
            listener.close()
            try:
                self.conn.measurement_stop()
            except Exception as e:
                logger.error(f'Error stopping measurement: {e}')
            try:
                self.conn.destination = previous_destination
                self.conn.set_detector_config(**previous_config)
            except Exception as e:
                logger.error(f'Error restoring config: {e}')

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)

    def establish_connection(self) -> None:
        """Establish connection to the camera."""
        self.conn = ServalCamera()
        self.conn.connect(self.url)
        self.conn.set_chip_config_files(
            bpc_file_path=self.bpc_file_path, dacs_file_path=self.dacs_file_path
        )
        self.conn.set_detector_config(**self.detector_config)

        img_dest = {'Base': 'http://localhost', 'Format': 'tiff', 'Mode': 'count'}
        self.conn.destination = {'Image': [img_dest]}

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        self.conn.measurement_stop()
        name = self.get_name()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


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
        self.dtype: np.dtype = np.uint32

    def _recv_more(self) -> None:
        if not (n := self.sock.recv_into(self.view[self.used :])):
            raise EOFError
        self.used += n

    def _read_until(self, token: bytes) -> int:
        while True:
            idx = self.buffer.find(token, 0, self.used)
            if idx >= 0:
                return idx + len(token)
            self._recv_more()

    def read_image_shape_from_header(self, header_size: int) -> None:
        """Read shape, size, dtype of all images from the first header."""
        header_str = self.buffer[:header_size].decode('utf-8')
        header_dict = json.loads(header_str)
        d = header_dict['bitDepth'] // 8
        self.shape = (header_dict['height'], header_dict['width'])
        self.size = header_dict.get('dataSize', prod(self.shape) * d)
        self.dtype = np.uint32 if d > 2 else np.uint16 if d > 1 else np.uint8

    def __next__(self) -> np.ndarray:
        """Recv as much data as needed and use it to yield next frame ASAP."""
        if self.i_frame >= self.n_frames:
            raise StopIteration
        header_end = self._read_until(b'}')
        if self.i_frame == 0:
            self.read_image_shape_from_header(header_end)
        while self.used < header_end + self.size:
            self._recv_more()
        i, j = header_end, header_end + self.size
        frame = np.frombuffer(self.buffer[i:j], dtype=self.dtype).reshape(self.shape).copy()

        # Decode Serval-packed 32-bit jsonimage payload into the physical 24-bit count:
        # observed packing (byte lanes): [b0, b1, b2, b3] with b1 unused/zero,
        # count = b0 | (b3<<8) | (b2<<16). Contact Daniel Tchon, tchon@fzu.cz, for details.
        if np.any((frame & np.uint32(0x0000FF00)) != 0):  # potentially check harder
            logger.debug('Unexpected nonzero byte1 in Serval packed uint32 payload.')
        if frame.dtype == np.uint32:
            bytes02 = frame & np.uint32(0x00FF00FF)
            bytes3 = frame & np.uint32(0xFF000000)
            frame = bytes02 | (bytes3 >> np.uint32(16))

        self.buffer[: self.used - j] = self.buffer[j : self.used]
        self.used -= j
        self.i_frame += 1
        return frame


if __name__ == '__main__':
    cam = CameraServal()
    from IPython import embed

    embed()
