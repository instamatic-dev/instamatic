"""Camera module for connecting with the Merlin EM detector.

The module communicates over TCP/IP with the camera.

Example usage:

```
# initialize
cam = CameraMerlin()

# get values
cam.merlin_get('DETECTORSTATUS')

# set continuous read/write mode
cam.merlin_set('CONTINUOUSRW', 1)
cam.merlin_set('COUNTERDEPTH', 12)

# acquire single frame (uses soft trigger)
frame = cam.get_image(exposure=0.1)

# acquire multiple frames with gapless acquisition
frames = cam.get_movie(n_frames=10, exposure=0.1)
```
"""

from __future__ import annotations

import atexit
import logging
import socket
import time
from typing import Any, List, Tuple

import numpy as np

from instamatic import config
from instamatic.camera.camera_base import CameraBase

try:
    from .merlin_io import load_mib
except ImportError:
    from merlin_io import load_mib

logger = logging.getLogger(__name__)

# socket.settimeout(5)  # seconds
socket.setdefaulttimeout(5)  # seconds


def MPX_CMD(type_cmd: str = 'GET', cmd: str = 'DETECTORSTATUS') -> bytes:
    """Generate TCP command bytes for Merlin software.

    Default value 'GET,DETECTORSTATUS' probes for
    the current status of the detector.

    Parameters
    ----------
    type_cmd : str, optional
        Type of the command
    cmd : str, optional
        Command to execute

    Returns
    -------
    bytes
        Command code in bytes format
    """
    length = len(cmd)
    # tmp = 'MPX,00000000' + str(length+5) + ',' + type_cmd + ',' + cmd
    tmp = f'MPX,00000000{length + 5},{type_cmd},{cmd}'
    logger.debug(tmp)
    return tmp.encode()


class CameraMerlin(CameraBase):
    """Camera interface for the Quantum Detectors Merlin camera."""

    START_SIZE = 14
    MAX_NUMFRAMESTOACQUIRE = 42_949_672_950
    streamable = True

    def __init__(self, name='merlin'):
        """Initialize camera module."""
        super().__init__(name)

        self._state = {}

        self._soft_trigger_mode = False
        self._soft_trigger_exposure = None

        self.establish_connection()
        self.establish_data_connection()

        msg = f'Camera {self.get_name()} initialized'
        logger.info(msg)

        atexit.register(self.release_connection)

    def receive_data(self, *, nbytes: int) -> bytearray:
        """Safely receive from the socket until `n_bytes` of data are
        received."""
        data = bytearray()
        n = 0
        t0 = time.perf_counter()
        while len(data) != nbytes:
            data.extend(self.s_data.recv(nbytes - len(data)))
            n += 1
        t1 = time.perf_counter()
        logger.info('Received %d bytes in %d steps (%f s)', len(data), n, t1 - t0)
        return data

    def merlin_set(self, key: str, value: Any):
        """Set state on Merlin parameter through command socket.

        Parameters
        ----------
        key : str
            Name of parameter
        value : Any
            Value to set
        """
        if self._state.get(key) == value:
            return

        self.s_cmd.sendall(MPX_CMD('SET', f'{key},{value}'))
        response = self.s_cmd.recv(1024).decode()
        logger.debug(response)
        *_, status = response.rsplit(',', 1)
        if status == '2':
            logger.warning('Merlin did not understand: %s' % response)
        else:
            self._state[key] = value
            logger.debug('Remembering state for %s value %s', key, value)

    def merlin_get(self, key: str) -> str:
        """Get state of Merlin parameter through command socket.

        Parameters
        ----------
        key : str
            Name of parameter

        Returns
        -------
        value : str
        """
        self.s_cmd.sendall(MPX_CMD('GET', key))
        response = self.s_cmd.recv(1024).decode()
        logger.debug(response)
        _, value, status = response.rsplit(',', 2)
        if status == '2':
            logger.warning('Merlin did not understand: %s' % response)
        return value

    def merlin_cmd(self, key: str):
        """Send Merlin command through command socket.

        Parameters
        ----------
        key : str
            Name of the command

        Raises
        ------
        ValueError
            If the command failed
        """
        self.s_cmd.sendall(MPX_CMD('CMD', key))
        response = self.s_cmd.recv(1024).decode()
        logger.debug(response)
        _, status = response.rsplit(',', 1)
        if status == '2':
            raise ValueError('Merlin did not understand: {response}')

    def setup_soft_trigger(self, exposure: float = None):
        """Set up for repeated acquisition using soft trigger, and start
        acquisition."""
        if exposure is None:
            exposure = self.default_exposure

        # convert s to ms
        exposure_ms = exposure * 1000

        if self._soft_trigger_mode:
            self.teardown_soft_trigger()

        self._soft_trigger_mode = True
        self._soft_trigger_exposure = exposure

        self.merlin_set('ACQUISITIONTIME', exposure_ms)
        self.merlin_set('ACQUISITIONPERIOD', exposure_ms)

        self._frame_number = 0

        # Set NUMFRAMESTOACQUIRE to maximum
        # Merlin collects up to this number of frames with a single SOFTTRIGGER acquisition
        self.merlin_set('NUMFRAMESTOACQUIRE', self.MAX_NUMFRAMESTOACQUIRE)

        self.merlin_set('TRIGGERSTART', 5)
        self.merlin_set('NUMFRAMESPERTRIGGER', 1)
        self.merlin_cmd('STARTACQUISITION')

        start = self.receive_data(nbytes=self.START_SIZE)

        header_size = int(start[4:])
        header = self.receive_data(nbytes=header_size)

        self._frame_length = None

    def teardown_soft_trigger(self):
        """Stop soft trigger acquisition."""
        self.merlin_cmd('STOPACQUISITION')
        self._soft_trigger_mode = False
        self._soft_trigger_exposure = None

    def get_image(self, exposure: float = None, **kwargs) -> np.ndarray:
        """Image acquisition routine. If the exposure is not given, the default
        value is read from the config file.

        Parameters
        ----------
        exposure : float, optional
            Exposure time in seconds.

        Returns
        -------
        data : np.ndarray
        """
        if not exposure:
            exposure = self.default_exposure

        if not self._soft_trigger_mode:
            logger.info('Set up soft trigger with exposure %s s', exposure)
            self.setup_soft_trigger(exposure=exposure)
        elif exposure != self._soft_trigger_exposure:
            logger.info('Change exposure to %s s', exposure)
            self.setup_soft_trigger(exposure=exposure)
        elif self._frame_number == self.MAX_NUMFRAMESTOACQUIRE:
            logger.debug(
                (
                    'Maximum frame number reached for this acquisition, '
                    'resetting soft trigger.'
                )
                % self.MAX_NUMFRAMESTOACQUIRE
            )
            self.setup_soft_trigger(exposure=exposure)

        self.merlin_cmd('SOFTTRIGGER')

        if not self._frame_length:
            mpx_header = self.receive_data(nbytes=self.START_SIZE)
            size = int(mpx_header[4:])

            logger.info('Received header: %s (%s)', size, mpx_header)

            framedata = self.receive_data(nbytes=size)
            skip = 0

            self._frame_length = self.START_SIZE + size
        else:
            framedata = self.receive_data(nbytes=self._frame_length)
            skip = self.START_SIZE

        self._frame_number += 1

        # Must skip first byte when loading data to avoid off-by-one error
        data = load_mib(framedata, skip=1 + skip).squeeze()

        # data[self._frame_number % 512] = 10000

        return data

    def get_movie(self, n_frames: int, exposure: float = None, **kwargs) -> List[np.ndarray]:
        """Gapless movie acquisition routine. If the exposure is not given, the
        default value is read from the config file.

        Parameters
        ----------
        n_frames : int
            Number of frames to collect
        exposure : float, optional
            Exposure time in seconds.

        Returns
        -------
        List[np.ndarray]
            List of image data
        """
        if self._soft_trigger_mode:
            self.teardown_soft_trigger()

        if exposure is None:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        # convert s to ms
        exposure_ms = exposure * 1000

        self.merlin_set('TRIGGERSTART', 0)
        self.merlin_set('ACQUISITIONTIME', exposure_ms)
        self.merlin_set('ACQUISITIONPERIOD', exposure_ms)
        self.merlin_set('NUMFRAMESTOACQUIRE', n_frames)

        # Start acquisition
        self.s_cmd.sendall(MPX_CMD('CMD', 'STARTACQUISITION'))

        start = self.receive_data(nbytes=self.START_SIZE)

        header_size = int(start[4:])

        header = self.receive_data(nbytes=header_size)

        logger.debug('Header data received (%s).', header_size)

        frames = []
        full_framesize = 0

        for x in range(n_frames):
            if not full_framesize:
                mpx_header = self.receive_data(nbytes=self.START_SIZE)
                size = int(mpx_header[4:])

                framedata = self.receive_data(nbytes=size)
                logger.info('Received frame %s: %s (%s)', x, size, mpx_header)

                full_framesize = self.START_SIZE + size
            else:
                framedata = self.receive_data(nbytes=full_framesize)[self.START_SIZE :]

            frames.append(framedata)

        logger.info('%s frames received.', n_frames)

        # Must skip first byte when loading data to avoid off-by-one error
        data = [load_mib(frame, skip=1).squeeze() for frame in frames]

        return data

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        binning = self.get_binning()
        dim_x, dim_y = self.get_camera_dimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    def establish_connection(self) -> None:
        """Establish connection to command port of the merlin software."""
        # Create command socket
        self.s_cmd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status

        logger.info('Connecting to Merlin on %s:%s', self.host, self.commandport)

        try:
            self.s_cmd.connect((self.host, self.commandport))

        except ConnectionRefusedError as e:
            raise ConnectionRefusedError(
                f'Could not establish command connection to {self.name}. '
                'The Merlin command port is not responding.'
            ) from e
        except OSError as e:
            raise OSError(
                f'Could not establish command connection to {self.name} ({e.args[0]}).'
                'Did you start the Merlin software? Is the IP correct? Is the Merlin command port already connected?).'
            ) from e

        version = self.merlin_get(key='SOFTWAREVERSION')
        logger.info('Merlin version: %s', version)

        status = self.merlin_get(key='DETECTORSTATUS')
        logger.info('Merlin status: %s', status)

        for key, value in self.detector_config.items():
            self.merlin_set(key, value)

    def establish_data_connection(self) -> None:
        """Establish connection to the dataport of the merlin software."""
        # Create command socket
        s_data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status
        try:
            s_data.connect((self.host, self.dataport))
        except ConnectionRefusedError as e:
            raise ConnectionRefusedError(
                f'Could not establish data connection to {self.name} ({e.args[0]}). '
                'The Merlin data port is not responding.'
            ) from e

        self.s_data = s_data

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        if self._soft_trigger_mode:
            logger.info('Stopping acquisition')
            self.teardown_soft_trigger()

        self.s_cmd.close()

        self.s_data.close()

        name = self.get_name()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


def test_movie(cam):
    print('\n\nMovie acquisition\n---\n')

    n_frames = 50
    exposure = 0.01

    t0 = time.perf_counter()

    frames = cam.get_movie(n_frames, exposure=exposure)

    t1 = time.perf_counter()

    avg_frametime = (t1 - t0) / n_frames
    overhead = avg_frametime - exposure

    print(f'\nExposure: {exposure}, frames: {n_frames}')
    print(
        f'\nTotal time: {t1 - t0:.3f} s - acq. time: {avg_frametime:.3f} s - overhead: {overhead:.3f}'
    )

    for frame in frames:
        assert frame.shape == (512, 512)


def test_single_frame(cam):
    print('\n\nSingle frame acquisition\n---\n')

    n_frames = 100
    exposure = 0.01

    t0 = time.perf_counter()

    for i in range(n_frames):
        frame = cam.get_image()
        assert frame.shape == (512, 512)

    t1 = time.perf_counter()

    avg_frametime = (t1 - t0) / n_frames
    overhead = avg_frametime - exposure

    print(f'\nExposure: {exposure}, frames: {n_frames}')
    print(
        f'Total time: {t1 - t0:.3f} s - acq. time: {avg_frametime:.3f} s - overhead: {overhead:.3f}'
    )


def test_plot_single_image(cam):
    arr = cam.get_image(exposure=0.1)

    import numpy as np

    arr = arr.squeeze()
    arr = np.flipud(arr)

    import matplotlib.pyplot as plt

    plt.imshow(arr.squeeze())
    plt.show()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info('Testing merlin detector')

    cam = CameraMerlin()

    test_movie(cam)

    test_single_frame(cam)

    test_movie(cam)

    # test_plot_single_image(cam)

    # Overhead on movie acquisition: < 1ms
    # Overhead single image acquisition: ~ 3-4 ms
