import socket
import pickle
import time
import atexit
from functools import partial
import subprocess as sp
from itertools import chain
from instamatic import config

from collections import defaultdict

import datetime
import threading


# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.tem_server_host
PORT = config.cfg.tem_server_port
BUFSIZE = 1024


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID',  str(p.pid)])


def start_server_in_subprocess():
   cmd = "instamatic.temserver.exe"
   p = sp.Popen(cmd, stdout=sp.DEVNULL)
   print(f"Starting TEM server ({HOST}:{PORT} on pid={p.pid})")
   atexit.register(kill_server, p)


class ServerMicroscope(object):
    """
    Simulates a Microscope object and synchronizes calls over a socket server.
    For documentation, see the actual python interface to the microscope API.
    """
    def __init__(self, name):
        super().__init__()
        
        self.name = name
        self._bufsize = BUFSIZE

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
    
    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f"Connected to TEM server ({HOST}:{PORT})")

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

        response = self.s.recv(self._bufsize)
        if response:
            status, data = pickle.loads(response)

        if status == 200:
            return data

        elif status == 500:
            raise data

        else:
            raise ConnectionError(f"Unknown status code: {status}")


class TraceVariable(object):
    """docstring for Tracer"""
    def __init__(self, func, interval=1.0, name="variable", verbose=False):
        super().__init__()
        self.name = name
        self.func = func
        self.interval = interval
        self.verbose = verbose

        self._traced = []

    def start(self):
        print(f"Trace started: {self.name}")
        self.update()

    def stop(self):
        self._timer.cancel()

        print(f"Trace canceled: {self.name}")

        return self._traced

    def update(self):
        ret = self.func()
        
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")
    
        if self.verbose:
            print(f"{now} | Trace {self.name}: {ret}")
    
        self._traced.append((now, ret))
        
        self._timer = threading.Timer(self.interval, self.update)
        self._timer.start()
