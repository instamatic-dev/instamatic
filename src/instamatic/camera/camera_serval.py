from __future__ import annotations

import atexit
import contextlib
import logging
import math
import socket
from io import BytesIO
from math import prod
from threading import Thread
from typing import Iterator, Optional, Sequence, Tuple
from urllib.parse import urlparse

import numpy as np
import tifffile
from serval_toolkit.camera import Camera as ServalCamera
from typing_extensions import TypeAlias

from instamatic.camera.camera_base import CameraBase
from instamatic.camera.serval_movie_deserializer import ServalMovieDeserializer

logger = logging.getLogger(__name__)

# Start servers in serval_toolkit:
# 1. `java -jar .\emu\tpx3_emu.jar`
# 2. `java -jar .\server\serv-2.1.3.jar`
# 3. launch `instamatic`


# By default, movies are requested image-by-image client-side which can be slow.
# Setting this var or using `camera.yaml` equivalent causes movies to be streamed
# by server via TCP which is faster, but may require tweaking firewall settings.
STREAM_MOVIES_VIA_TCP: bool = False

Movie: TypeAlias = Iterator[np.ndarray]


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
        """Initialize camera module, vars, establish connection & cleanup."""
        super().__init__(name)

        self.tcp_dest: dict[str, str] = {}  # used if STREAM_MOVIES_VIA_TCP=True
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
        http_dest = {'Base': 'http://localhost', 'Format': 'tiff', 'Mode': 'count'}
        f = dict(bpc_file_path=self.bpc_file_path, dacs_file_path=self.dacs_file_path)

        conn = ServalCamera()
        conn.connect(http_url.geturl())
        conn.set_chip_config_files(**f)
        conn.set_detector_config(**self.detector_config)
        conn.destination = {'Image': [http_dest]}

        if getattr(self, 'stream_movies_via_tcp') or STREAM_MOVIES_VIA_TCP:
            self.tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_listener.settimeout(1.0)
            self.tcp_listener.bind(('0.0.0.0', 0))
            self.tcp_listener.listen(1)
            tcp_port = self.tcp_listener.getsockname()[1]
            local_ip = _local_ip_for(http_url.hostname or 'localhost', tcp_port)
            tcp_base = f'tcp://connect@{local_ip}:{tcp_port}'
            self.tcp_dest = {'Base': tcp_base, 'Format': 'jsonimage', 'Mode': 'count'}

        return conn

    def release_connection(self) -> None:
        """Release the connection to the camera (HTTP & TCP if applicable)."""
        self.conn.measurement_stop()
        if self.tcp_listener is not None:
            self.tcp_listener.close()
        logger.info(f"Connection to camera '{self.get_name()}' released")

    def set_detector_config(self, **kwargs) -> None:
        """Set detector config while inferring about missing config params."""
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

    def get_movie(self, n_frames: int, exposure: Optional[float] = None, **_) -> Movie:
        """Yield `n_frames` images received via HTTP (convenient) or TCP
        (fast); If the exposure is None, the default is read from the config.
        Binning is ignored. Setup is eager, start is delayed until iteration.

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

    def _get_movie_http(self, n_frames: int, exposure: float) -> Movie:
        """Convenient method: poll frames via HTTP using the client socket."""
        self.previous_config = self.conn.detector_config
        self.set_detector_config(ExposureTime=exposure, nTriggers=n_frames)
        return self._get_movie_inner(n_frames=n_frames)

    def _get_movie_tcp(self, n_frames: int, exposure: float) -> Movie:
        """Fast: stream frames directly via TCP if STREAM_MOVIES_VIA_TCP."""
        self.previous_config = self.conn.detector_config
        self.previous_destination = self.conn.destination
        self.conn.destination = {'Image': [self.tcp_dest]}
        self.set_detector_config(ExposureTime=exposure, nTriggers=n_frames)
        return self._get_movie_inner(n_frames=n_frames)

    def _get_movie_inner(self, n_frames: int) -> Movie:
        """Frame generator; Separate method because `yield` keyword makes this
        code execution delayed; In other words, setup runs when `get_movie` is
        called, but this method only when returned iterator is iterated."""
        try:
            if self.tcp_listener:
                Thread(target=self.conn.measurement_start, daemon=True).start()
                self.tcp_listener.settimeout(5.0)
                sock, _ = self.tcp_listener.accept()
                sock.settimeout(1.1 * self.MAX_EXPOSURE)
                with sock:
                    yield from ServalMovieDeserializer(sock, n_frames, self.movie_bufsize)
            else:
                self.conn.measurement_start()
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
                if self.tcp_listener:
                    self.conn.destination = self.previous_destination
            except Exception as ex:
                logger.error(f'Error restoring config and destination: {ex}')

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()
        return int(dim_x / binning), int(dim_y / binning)


if __name__ == '__main__':
    cam = CameraServal()
    from IPython import embed

    embed()
