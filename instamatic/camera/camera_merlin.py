import atexit
import logging
import socket
import time
from typing import Any

import numpy as np

from instamatic import config

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
    tmp = f'MPX,00000000{length+5},{type_cmd},{cmd}'
    logger.debug(tmp)
    return tmp.encode()


class CameraMerlin:
    """Camera interface for the Quantum Detectors Merlin camera."""
    START_SIZE = 14

    def __init__(self, name='merlin'):
        """Initialize camera module."""
        super().__init__()

        self.name = name
        self._state = {}

        self._soft_trigger_mode = False
        self._soft_trigger_exposure = None

        self.load_defaults()

        self.establishConnection()
        self.establishDataConnection()

        msg = f'Camera {self.getName()} initialized'
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.streamable = True

        self.__dict__.update(config.camera.mapping)

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

    def merlin_get(self, key: str):
        self.s_cmd.sendall(MPX_CMD('GET', key))
        response = self.s_cmd.recv(1024).decode()
        logger.debug(response)
        _, value, status = response.rsplit(',', 2)
        if status == '2':
            logger.warning('Merlin did not understand: %s' % response)
        return value

    def merlin_cmd(self, key: str):
        self.s_cmd.sendall(MPX_CMD('CMD', key))
        response = self.s_cmd.recv(1024).decode()
        logger.debug(response)
        _, status = response.rsplit(',', 1)
        if status == '2':
            raise ValueError('Merlin did not understand: {response}')

    def setup_soft_trigger(self, exposure=None):
        if exposure is None:
            exposure = self.default_exposure

        # convert s to ms
        exposure_ms = exposure * 1000

        if self._soft_trigger_mode:
            self.teardown_soft_trigger()

        self._soft_trigger_mode = True
        self._soft_trigger_exposure = exposure

        self.merlin_set('CONTINUOUSRW', 1)
        self.merlin_set('ACQUISITIONTIME', exposure_ms)
        self.merlin_set('ACQUISITIONPERIOD', exposure_ms)
        self.merlin_set('FILEENABLE', 0)

        self._frame_number = 0

        # Set NUMFRAMESTOACQUIRE to a large number
        # Merlin will only collect this number of frames with SOFTTRIGGER
        self.merlin_set('NUMFRAMESTOACQUIRE', 10_000)

        self.merlin_set('TRIGGERSTART', '5')
        self.merlin_set('NUMFRAMESPERTRIGGER', '1')
        self.merlin_cmd('STARTACQUISITION')

        start = self.receive_data(nbytes=self.START_SIZE)

        header_size = int(start[4:])
        header = self.receive_data(nbytes=header_size)

        self._frame_length = None

    def teardown_soft_trigger(self):
        self.merlin_cmd('STOPACQUISITION')
        self._soft_trigger_mode = False
        self._soft_trigger_exposure = None

    def getImage(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        if not exposure:
            exposure = self.default_exposure

        if not self._soft_trigger_mode:
            logger.info('Set up soft trigger with exposure %s s', exposure)
            self.setup_soft_trigger(exposure=exposure)
        elif exposure != self._soft_trigger_exposure:
            logger.info('Change exposure to %s s', exposure)
            self.teardown_soft_trigger()
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

    def getMovie(self, n_frames, exposure=None, binsize=None, **kwargs):
        """Movie acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        if self._soft_trigger_mode:
            self.teardown_soft_trigger()

        if exposure is None:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        # convert s to ms
        exposure_ms = exposure * 1000

        self.merlin_set('CONTINUOUSRW', 1)
        self.merlin_set('TRIGGERSTART', 0)
        self.merlin_set('ACQUISITIONTIME', exposure_ms)
        self.merlin_set('ACQUISITIONPERIOD', exposure_ms)
        self.merlin_set('NUMFRAMESTOACQUIRE', n_frames)
        self.merlin_set('FILEENABLE', 0)

        # experimental
        self.merlin_set('RUNHEADLESS', 0)

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
                framedata = self.receive_data(nbytes=full_framesize)[self.START_SIZE:]

            frames.append(framedata)

        logger.info('%s frames received.', n_frames)

        # Must skip first byte when loading data to avoid off-by-one error
        data = [load_mib(frame, skip=1).squeeze() for frame in frames]

        return data

    def isCameraInfoAvailable(self) -> bool:
        """Check if the camera is available."""
        return True

    def getImageDimensions(self) -> (int, int):
        """Get the binned dimensions reported by the camera."""
        binning = self.getBinning()
        dim_x, dim_y = self.getCameraDimensions()

        dim_x = int(dim_x / binning)
        dim_y = int(dim_y / binning)

        return dim_x, dim_y

    def getCameraDimensions(self) -> (int, int):
        """Get the dimensions reported by the camera."""
        return self.dimensions

    def getName(self) -> str:
        """Get the name reported by the camera."""
        return self.name

    def establishConnection(self) -> None:
        """Establish connection to command port of the merlin software."""
        # Create command socket
        self.s_cmd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status

        logger.info('Connecting to Merlin on %s:%s', self.host, self.commandport)

        try:
            self.s_cmd.connect((self.host, self.commandport))

        except ConnectionRefusedError as e:
            raise RuntimeError(
                f'Could not establish command connection to {self.name}, '
                '(Merlin command port not responding).') from e
        except OSError as e:
            raise RuntimeError(
                f'Could not establish command connection to {self.name}, '
                '(Merlin command port already connected).') from e

        version = self.merlin_get(key='SOFTWAREVERSION')
        logger.info('Merlin version: %s', version)

        status = self.merlin_get(key='DETECTORSTATUS')
        logger.info('Merlin status: %s', status)

        for key, value in self.detector_config.items():
            self.merlin_set(key, value)

    def establishDataConnection(self) -> None:
        """Establish connection to the dataport of the merlin software."""
        # Create command socket
        s_data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status
        try:
            s_data.connect((self.host, self.dataport))
        except ConnectionRefusedError as e:
            raise RuntimeError(
                f'Could not establish data connection to {self.name}, '
                '(Merlin data port not responding).') from e

        self.s_data = s_data

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        if self._soft_trigger_mode:
            logger.info('Stopping acquisition')
            self.teardown_soft_trigger()

        self.s_cmd.close()

        self.s_data.close()

        name = self.getName()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


def test_movie(cam):
    print('\n\nMovie acquisition\n---\n')

    n_frames = 50
    exposure = 0.01

    t0 = time.perf_counter()

    frames = cam.getMovie(n_frames, exposure=exposure)

    t1 = time.perf_counter()

    avg_frametime = (t1 - t0) / n_frames
    overhead = avg_frametime - exposure

    print(f'\nExposure: {exposure}, frames: {n_frames}')
    print(f'\nTotal time: {t1-t0:.3f} s - acq. time: {avg_frametime:.3f} s - overhead: {overhead:.3f}')

    for frame in frames:
        assert frame.shape == (512, 512)


def test_single_frame(cam):
    print('\n\nSingle frame acquisition\n---\n')

    n_frames = 100
    exposure = 0.01

    t0 = time.perf_counter()

    for i in range(n_frames):
        frame = cam.getImage()
        assert frame.shape == (512, 512)

    t1 = time.perf_counter()

    avg_frametime = (t1 - t0) / n_frames
    overhead = avg_frametime - exposure

    print(f'\nExposure: {exposure}, frames: {n_frames}')
    print(f'Total time: {t1-t0:.3f} s - acq. time: {avg_frametime:.3f} s - overhead: {overhead:.3f}')


def test_plot_single_image(cam):
    arr = cam.getImage(exposure=0.1)

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

    # TODO
    # - How to manage soft trigger mode best?
    # - set large n_frames for getImage
    # - track current frame number and refresh when n_frames gets hit
    # - track when in SOFTTRIGGER mode
    # - seamlessly switch to soft trigger / internal
    #   trigger when calling getMovie / getImage
