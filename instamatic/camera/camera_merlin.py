import atexit
import logging
import socket
import time

import numpy as np
from merlin_io import load_mib

from instamatic import config

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

    def __init__(self, name='merlin'):
        """Initialize camera module."""
        super().__init__()

        self.name = name

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

    def getImage(self, exposure=None, binsize=None, **kwargs) -> np.ndarray:
        """Image acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        frames = self.getMovie(n_frames=1, exposure=exposure, binsize=binsize)
        return frames[0]

    def getMovie(self, n_frames, exposure=None, binsize=None, **kwargs):
        """Movie acquisition routine. If the exposure and binsize are not
        given, the default values are read from the config file.

        exposure:
            Exposure time in seconds.
        binsize:
            Which binning to use.
        """
        times = {}
        times['start'] = time.perf_counter()

        if exposure is None:
            exposure = self.default_exposure
        if not binsize:
            binsize = self.default_binsize

        # convert s to ms
        exposure_ms = exposure * 1000

        times['set parameters'] = time.perf_counter()

        # Set continuous mode on
        self.s_cmd.sendall(MPX_CMD('SET', 'CONTINUOUSRW,1'))
        # Set frame time in miliseconds
        self.s_cmd.sendall(MPX_CMD('SET', f'ACQUISITIONTIME,{exposure_ms}'))
        # Set gap time in milliseconds (The number corresponds to sum of frame and gap time)
        self.s_cmd.sendall(MPX_CMD('SET', f'ACQUISITIONPERIOD,{exposure_ms}'))
        # Set number of frames to be acquired
        self.s_cmd.sendall(MPX_CMD('SET', f'NUMFRAMESTOACQUIRE,{n_frames}'))
        # Disable file saving
        self.s_cmd.sendall(MPX_CMD('SET', 'FILEENABLE,0'))
        # Start acquisition
        self.s_cmd.sendall(MPX_CMD('CMD', 'STARTACQUISITION'))

        times['set parameters done'] = time.perf_counter()

        # Needs a delay otherwise we get a crash because the system is not ready yet
        # round-trip time to server is ~28 ms
        min_delay = max(n_frames * exposure - 0.001, 0.3)
        logger.info('Waiting for %s s.', min_delay)
        time.sleep(min_delay)

        times['after delay'] = time.perf_counter()

        data = self.s_data.recv(14)
        start = data.decode()

        header_size = int(start[4:])
        header = self.s_data.recv(header_size)

        times['header received'] = time.perf_counter()

        if (len(header) != header_size):
            raise OSError('Wrong header data received')

        logger.info('Header data received (%s).', header_size)

        frames = []

        times['pre-acquire'] = time.perf_counter()

        for x in range(n_frames):
            # time.sleep(0.2)
            times[f'## Frame {x}'] = time.perf_counter()

            mpx_header = self.s_data.recv(14)
            size = int(mpx_header[4:])

            times[f'    header received {x}'] = time.perf_counter()

            logger.info('Receiving frame %s: %s (%s)', x, size, mpx_header)

            framedata = bytearray()
            trips = 0
            while (len(framedata) != size):
                raw_data = self.s_data.recv(size - len(framedata))
                framedata.extend(raw_data)
                # logger.info('\t(%s) frame %s received %s bytes, total length %s', trips, x, len(raw_data), len(framedata))
                trips += 1

            times[f'    data received {x}'] = time.perf_counter()

            logger.info('\tframe %s received with length %s (trips=%s)', x, len(framedata), trips)
            frames.append(framedata)

            times[f'    done {x}'] = time.perf_counter()

        logger.info('%s frames received.', n_frames)

        # Must skip first byte when loading data to avoid off-by-one error
        data = [load_mib(frame[1:]) for frame in frames]

        times['done'] = time.perf_counter()

        prev = times['start']
        for k, v in times.items():
            print(f'{k:22s} - {v:.3f} - {v-prev:.3f}')
            prev = v

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
        s_cmd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status

        logger.info('Connecting to Merlin on %s:%s', self.host, self.commandport)

        try:
            s_cmd.connect((self.host, self.commandport))

            s_cmd.sendall(MPX_CMD('GET', 'SOFTWAREVERSION'))
            version = s_cmd.recv(1024)
            logger.info(f'Version CMD: {version.decode()}')

            s_cmd.sendall(MPX_CMD('GET', 'DETECTORSTATUS'))
            status = s_cmd.recv(1024)
            logger.info(f'Status CMD: {status.decode()}')

        except ConnectionRefusedError:
            raise RuntimeError(
                f'Could not establish command connection to {self.name}, '
                '(Merlin command port not responding).')
        except OSError:
            raise RuntimeError(
                f'Could not establish command connection to {self.name}, '
                '(Merlin command port already connected).')

        for key, value in self.detector_config.items():
            s_cmd.sendall(MPX_CMD('SET', f'{key},{value}'))

        self.s_cmd = s_cmd

    def establishDataConnection(self) -> None:
        """Establish connection to the dataport of the merlin software."""
        # Create command socket
        s_data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect sockets and probe for the detector status
        try:
            s_data.connect((self.host, self.dataport))
        except ConnectionRefusedError:
            raise RuntimeError(
                f'Could not establish data connection to {self.name}, '
                '(Merlin data port not responding).')

        self.s_data = s_data

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        self.s_cmd.close()

        self.s_data.close()

        name = self.getName()
        msg = f"Connection to camera '{name}' released"
        logger.info(msg)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info('Testing merlin detector')

    cam = CameraMerlin()

    t0 = time.perf_counter()

    n_frames = 50
    frames = cam.getMovie(n_frames, exposure=0.05)

    t1 = time.perf_counter()

    print(f'Total time: {t1-t0:.3f} s - {(t1-t0) / n_frames:.3f} per frame')

    for frame in frames:
        print(frame.shape)

    exit()

    arr = frames[0]

    import numpy as np

    arr = arr.squeeze()
    arr = np.flipud(arr)

    import matplotlib.pyplot as plt
    plt.imshow(arr.squeeze())
    plt.show()
