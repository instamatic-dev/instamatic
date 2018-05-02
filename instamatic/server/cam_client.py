import socket
import pickle
import time
import atexit
from functools import partial
import subprocess as sp
from itertools import chain
from instamatic import config

# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.host
PORT = config.cfg.port
BUFSIZE = 4096


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID',  str(p.pid)])


def start_server_in_subprocess():
   cmd = "instamatic.camserver.exe"
   p = sp.Popen(cmd, stdout=sp.DEVNULL)
   print(f"Starting CAM server ({HOST}:{PORT} on pid={p.pid})")
   atexit.register(kill_server, p)


def recvall(sock, bufsize, nbufs):
    data = b''
    for i in range(nbufs):
        part = sock.recv(bufsize)
        data += part
    return data


class ServerCam(object):
    """
    Simulates a Microscope object and synchronizes calls over a socket server.
    For documentation, see the actual python interface to the microscope API.
    """
    def __init__(self, name):
        super().__init__()
        
        self.name = name

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

        atexit.register(self.s.close)

        self.bufsize = BUFSIZE
        xres, yres = self.getDimensions()
        bitdepth = 4
        self.imagebufsize = bitdepth*xres*yres + self.bufsize
    
    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f"Connected to server ({HOST}:{PORT})")

    def __getattr__(self, func_name):
        return partial(self._func, func_name)

    def _func(self, func_name, *args, **kwargs):
        dct = {"func_name": func_name,
               "args": args,
               "kwargs": kwargs}

        return self._eval_dct(dct)

    def _eval_dct(self, dct):
        """Takes approximately 0.2-0.3 ms per call if HOST=='localhost'"""
        # t0 = time.clock()

        self.s.send(pickle.dumps(dct))

        if dct["func_name"] == "getImage":
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


if __name__ == '__main__':
    ## Usage: 
    ##    First run tem_server.py (or `instamatic.temserver.exe`)
    ##    Second, run tem_client.py

    cam = ServerCam("simulate")

    from IPython import embed
    embed()

    import sys
    sys.exit()