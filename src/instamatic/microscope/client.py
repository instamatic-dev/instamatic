from __future__ import annotations

import atexit
import datetime
import socket
import subprocess as sp
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict

from instamatic import config
from instamatic.exceptions import TEMCommunicationError, exception_list
from instamatic.server.serializer import dumper, loader

HOST = config.settings.tem_server_host
PORT = config.settings.tem_server_port
BUFSIZE = 1024


class ServerError(Exception):
    pass


def kill_server(p: sp.Popen) -> None:
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])


def start_server_in_subprocess() -> None:
    cmd = 'instamatic.temserver.exe'
    p = sp.Popen(cmd, stdout=sp.DEVNULL)
    print(f'Starting TEM server ({HOST}:{PORT} on pid={p.pid})')
    atexit.register(kill_server, p)


class MicroscopeClient:
    """A proxy class for individual `Microscope` interface classes. Simulates a
    `Microscope` object and synchronizes calls over a socket server. On
    `__init__`, stores attributes of interfaced `Microscope` in `_dct`; On
    `__getattr__`, wraps and returns an attribute of interfaced `Microscope`.
    Thus, it is a surrogate for any `Microscope` class with a fitting
    interface.

    For documentation of individual methods, see the actual python
    interface to the used microscope API.
    """

    def __init__(self, *, interface: str) -> None:
        super().__init__()

        self.interface = interface
        self.name = interface
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
                        print('Waiting for server')
                    if t > 30:
                        raise TEMCommunicationError(
                            'Cannot establish server connection (timeout)'
                        )
                else:
                    break

        self._init_dict()
        self.check_goniotool()

        atexit.register(self.s.close)

    def connect(self) -> None:
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f'Connected to TEM server ({HOST}:{PORT})')

    def __getattr__(self, func_name: str) -> Callable:
        wrapped = self._dct.get(func_name, None)

        @wraps(wrapped)
        def wrapper(*args, **kwargs):
            dct = {'func_name': func_name, 'args': args, 'kwargs': kwargs}
            return self._eval_dct(dct)

        return wrapper

    def _eval_dct(self, dct: Dict[str, Any]) -> Any:
        """Takes approximately 0.2-0.3 ms per call if HOST=='localhost'."""
        self.s.send(dumper(dct))

        response = self.s.recv(self._bufsize)

        if response:
            status, data = loader(response)
        else:
            raise RuntimeError(f'Received empty response when evaluating {dct=}')

        if status == 200:
            return data

        elif status == 500:
            error_code, args = data
            raise exception_list.get(error_code, TEMCommunicationError)(*args)

        else:
            raise ConnectionError(f'Unknown status code: {status}')

    def _init_dict(self) -> None:
        """Get list of functions and their doc strings from the uninitialized
        class."""
        from instamatic.microscope import get_microscope_class

        tem = get_microscope_class(interface=self.interface)

        self._dct = {
            key: value for key, value in tem.__dict__.items() if not key.startswith('_')
        }
        self._dct['get_attrs'] = None

    def _init_attr_dict(self):
        """Get list of attrs and their types."""
        self._attr_dct = self.get_attrs()

    def __dir__(self) -> list:
        return list(self._dct.keys())

    def check_goniotool(self) -> None:
        """Check whether goniotool is available and update the config as
        necessary."""
        if config.settings.use_goniotool:
            config.settings.use_goniotool = self.is_goniotool_available()


class TraceVariable:
    """Simple class to trace a variable over time.

    Usage:
        t = TraceVariable(ctrl.stage.get, verbose=True)
        t.start()
        t.stage.set(x=0, y=0, wait=False)
        ...
        values = t.stop()
    """

    def __init__(
        self,
        func,
        interval: float = 1.0,
        name: str = 'variable',
        verbose: bool = False,
    ):
        super().__init__()
        self.name = name
        self.func = func
        self.interval = interval
        self.verbose = verbose

        self._traced = []

    def start(self):
        print(f'Trace started: {self.name}')
        self.update()

    def stop(self):
        self._timer.cancel()

        print(f'Trace canceled: {self.name}')

        return self._traced

    def update(self):
        ret = self.func()

        now = datetime.datetime.now().strftime('%H:%M:%S.%f')

        if self.verbose:
            print(f'{now} | Trace {self.name}: {ret}')

        self._traced.append((now, ret))

        self._timer = threading.Timer(self.interval, self.update)
        self._timer.start()
