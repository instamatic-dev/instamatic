import socket
import pickle
import time
import atexit
from functools import wraps
import subprocess as sp
from instamatic import config

# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.cam_server_host
PORT = config.cfg.cam_server_port
BUFSIZE = 4096


class ServerError(Exception):
    pass


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID',  str(p.pid)])


def start_server_in_subprocess():
   cmd = "instamatic.camserver.exe"
   p = sp.Popen(cmd, stdout=sp.DEVNULL)
   print(f"Starting CAM server ({HOST}:{PORT} on pid={p.pid})")
   atexit.register(kill_server, p)


class ServerCam(object):
    """
    Simulates a Camera object and synchronizes calls over a socket server.
    For documentation, see the actual python interface to the camera API.
    """
    def __init__(self, name):
        super().__init__()
        
        self.name = name
        self.bufsize = BUFSIZE
        self.streamable = False  # overrides cam settings

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
                        print("Waiting for server")
                    if t > 30:
                        raise RuntimeError("Cannot establish server connection (timeout)")
                else:
                    break

        self._init_dict()
        self._init_attr_dict()

        atexit.register(self.s.close)

        xres, yres = self.getDimensions()
        bitdepth = 4
        self.imagebufsize = bitdepth*xres*yres + self.bufsize
    
    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f"Connected to CAM server ({HOST}:{PORT})")

    def __getattr__(self, attr_name):

        if attr_name in self._dct:
            wrapped = self._dct[attr_name]
        elif attr_name in self._attr_dct:
            dct = {"attr_name": attr_name}
            return self._eval_dct(dct)
        else:
            raise AttributeError(f"`{self.__class__.__name__}` object has no attribute `{attr_name}`")

        @wraps(wrapped)
        def wrapper(*args, **kwargs):
            dct = {"attr_name": attr_name,
               "args": args,
               "kwargs": kwargs}
            return self._eval_dct(dct)

        return wrapper

    def _eval_dct(self, dct):
        """Takes approximately 0.2-0.3 ms per call if HOST=='localhost'"""
        # t0 = time.perf_counter()

        self.s.send(pickle.dumps(dct))

        if dct["attr_name"] == "getImage":
            # approximately 2-3 ms for the interface
            response = self.s.recv(self.imagebufsize)
        else:
            response = self.s.recv(self.bufsize)

        if response:
            status, data = pickle.loads(response)

        if status == 200:
            return data

        elif status == 500:
            raise data

        else:
            raise ConnectionError(f"Unknown status code: {status}")

    def _init_dict(self):
        """Get list of functions and their doc strings from the uninitialized class"""
        from instamatic.camera.camera import get_cam
        cam = get_cam(self.name)

        self._dct = {key:value for key, value in  cam.__dict__.items() if not key.startswith("_")}
        self._dct["get_attrs"] = None

    def _init_attr_dict(self):
        """Get list of attrs and their types"""
        self._attr_dct = self.get_attrs()

    def __dir__(self):
        return tuple(self._dct.keys()) + tuple(self._attr_dct.keys())
