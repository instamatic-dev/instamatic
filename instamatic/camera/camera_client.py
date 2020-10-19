import atexit
import socket
import subprocess as sp
import time
from functools import wraps

import numpy as np

from instamatic import config
from instamatic.exceptions import exception_list
from instamatic.exceptions import TEMCommunicationError
from instamatic.server.serializer import pickle_dumper as dumper
from instamatic.server.serializer import pickle_loader as loader


if config.settings.cam_use_shared_memory:
    from multiprocessing import shared_memory

HOST = config.settings.cam_server_host
PORT = config.settings.cam_server_port
BUFSIZE = 4096


class ServerError(Exception):
    pass


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])


def start_server_in_subprocess():
    cmd = 'instamatic.camserver.exe'
    p = sp.Popen(cmd, stdout=sp.DEVNULL)
    print(f'Starting CAM server ({HOST}:{PORT} on pid={p.pid})')
    atexit.register(kill_server, p)


class CamClient:
    """Simulates a Camera object and synchronizes calls over a socket server.

    For documentation, see the actual python interface to the camera
    API.
    """

    def __init__(
        self,
        name: str,
        interface: str,
    ):
        super().__init__()

        self.name = name
        self.interface = interface
        self._bufsize = BUFSIZE
        self.streamable = False  # overrides cam settings
        self.verbose = False

        try:
            self.connect()
        except ConnectionRefusedError:
            start_server_in_subprocess()

            for t in range(30):
                try:
                    self.connect()
                except ConnectionRefusedError:
                    time.sleep(1)
                    if t > 3:
                        print('Waiting for server')
                    if t > 30:
                        raise RuntimeError('Cannot establish server connection (timeout)')
                else:
                    break

        self.use_shared_memory = config.settings.cam_use_shared_memory and self.is_local_connection
        print('Use shared memory:', self.use_shared_memory)

        self.buffers = {}
        self.shms = {}

        self._init_dict()
        self._init_attr_dict()

        atexit.register(self.s.close)

        xres, yres = self.getImageDimensions()
        bitdepth = 4
        self._imagebufsize = bitdepth * xres * yres + self._bufsize

    @property
    def is_local_connection(self):
        """Check if the socket connection is a local connection."""
        return self.s.getpeername()[0] == self.s.getsockname()[0]

    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f'Connected to CAM server ({HOST}:{PORT})')

    def __getattr__(self, attr_name):

        if attr_name in self._dct:
            wrapped = self._dct[attr_name]
        elif attr_name in self._attr_dct:
            dct = {'attr_name': attr_name}
            return self._eval_dct(dct)
        else:
            raise AttributeError(f'`{self.__class__.__name__}` object has no attribute `{attr_name}`')

        @wraps(wrapped)
        def wrapper(*args, **kwargs):
            dct = {'attr_name': attr_name,
                   'args': args,
                   'kwargs': kwargs}
            return self._eval_dct(dct)

        return wrapper

    def _eval_dct(self, dct):
        """Takes approximately 0.2-0.3 ms per call if HOST=='localhost'."""
        self.s.send(dumper(dct))

        acquiring_image = dct['attr_name'] == 'getImage'

        if acquiring_image and not self.use_shared_memory:
            response = self.s.recv(self._imagebufsize)
        else:
            response = self.s.recv(self._bufsize)

        if response:
            status, data = loader(response)

        if self.use_shared_memory and acquiring_image:
            data = self.get_data_from_shared_memory(**data)

        if status == 200:
            return data

        elif status == 500:
            error_code, args = data
            raise exception_list.get(error_code, TEMCommunicationError)(*args)

        else:
            raise ConnectionError(f'Unknown status code: {status}')

    def _init_dict(self):
        """Get list of functions and their doc strings from the uninitialized
        class."""
        from instamatic.camera.camera import get_cam
        cam = get_cam(self.interface)

        self._dct = {key: value for key, value in cam.__dict__.items() if not key.startswith('_')}
        self._dct['get_attrs'] = None

    def _init_attr_dict(self):
        """Get list of attrs and their types."""
        self._attr_dct = self.get_attrs()

    def __dir__(self):
        return tuple(self._dct.keys()) + tuple(self._attr_dct.keys())

    def get_data_from_shared_memory(self, name: str, shape: tuple, dtype: str, **kwargs):
        """Grab image data from shared buffer."""
        dtype = getattr(np, dtype)

        # Initialize shared memory object
        if name not in self.shms:
            shm = shared_memory.SharedMemory(name=name)
            self.shms[name] = shm
            if self.verbose:
                print('Read shared memory: `{name}`')

        # Initialize shared memory buffer
        if name not in self.buffers:
            if self.verbose:
                print(f'Connect to buffer: `{name}` | {shape} ({dtype})')
            shm = self.shms[name]
            self.buffers[name] = np.ndarray(shape, dtype=dtype, buffer=shm.buf)

        # Copy data from shared image buffer
        if self.verbose:
            print(f'Retrieve data from buffer `{name}`')

        buffer = self.buffers[name]
        data = buffer[:]

        return data
