from __future__ import annotations

import atexit
import socket
import subprocess as sp
import time
from functools import wraps

from pywinauto import Application

from instamatic import config
from instamatic.exceptions import TEMCommunicationError, exception_list
from instamatic.server.serializer import dumper, loader

GONIOTOOL_EXE = 'C:\\JEOL\\TOOL\\GonioTool.exe'
DEFAULT_SPEED = 12

HOST = config.settings.goniotool_server_host
PORT = config.settings.goniotool_server_port
BUFSIZE = 1024


class ServerError(Exception):
    pass


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])


def start_server_in_subprocess():
    cmd = 'instamatic.goniotool.exe'
    p = sp.Popen(cmd, stdout=sp.DEVNULL)
    print(f'Starting GonioTool server ({HOST}:{PORT} on pid={p.pid})')
    atexit.register(kill_server, p)


class GonioToolClient:
    """Simulates a GonioToolWrapper object and synchronizes calls over a socket
    server.

    For documentation, see the actual python interface to the
    GonioToolWrapper API.
    """

    def __init__(self, name='GonioTool'):
        super().__init__()

        self.name = name
        self._bufsize = BUFSIZE

        try:
            self.connect()
        except ConnectionRefusedError as e:
            try:
                start_server_in_subprocess()
            except FileNotFoundError:
                raise e

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

        self._init_dict()

        atexit.register(self.s.close)

    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f'Connected to GonioTool server ({HOST}:{PORT})')

    def __getattr__(self, func_name):
        try:
            wrapped = self._dct[func_name]
        except KeyError as e:
            raise AttributeError(
                f'`{self.__class__.__name__}` object has no attribute `{func_name}`'
            ) from e

        @wraps(wrapped)
        def wrapper(*args, **kwargs):
            dct = {'func_name': func_name, 'args': args, 'kwargs': kwargs}
            return self._eval_dct(dct)

        return wrapper

    def _eval_dct(self, dct):
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

    def _init_dict(self):
        gtw = GonioToolWrapper

        self._dct = {
            key: value for key, value in gtw.__dict__.items() if not key.startswith('_')
        }

    def __dir__(self):
        return self._dct.keys()


class GonioToolWrapper:
    """Interfaces with Goniotool to automate setting the rotation speed on a
    JEOL microscope by adjusting the stepping frequency of the motor. The
    values can be set from 1 to 12, where 12 is maximum speed and 1 is the
    slowest. The speed is linear up the maximum speed, where 1 is approximately
    50 degrees/minute.

    barrier: threading.Barrier
        Synchronization primitive to synch with parent process
    """

    def __init__(self, barrier=None):
        super().__init__()

        self.app = Application().start(GONIOTOOL_EXE)
        input(
            'Enter password and press <ENTER> to continue...'
        )  # delay for password, TODO: automate
        self.startup()

        if barrier:
            barrier.wait()

    def startup(self):
        """Initialize and start up the GonioTool interface."""
        self.f1rate = self.app.TMainForm['f1/rate']

        self.f1 = self.app.TMainForm.f1
        self.rb_cmd = self.f1.CMDRadioButton
        self.rb_tkb = self.f1.TKBRadioButton
        self.set_button = self.f1.SetButton
        self.get_button = self.f1.GetButton

        self.click_get_button()
        self.click_cmd()

        self.edit = self.app.TMainForm.f1.Edit7

    def closedown(self):
        """Set default speed and close the program."""
        self.set_rate(DEFAULT_SPEED)
        self.click_tkb()
        time.sleep(1)
        self.app.kill()

    def list_f1rate(self):
        """List GUI control identifiers for `f1/rate` tab."""
        self.f1rate.print_control_identifiers()

    def list_f1(self):
        """List GUI control identifiers for `f1` box."""
        self.f1.print_control_identifiers()

    def click_get_button(self):
        """Click GET button."""
        self.get_button.click()

    def click_set_button(self):
        """Click SET button."""
        self.set_button.click()

    def click_tkb(self):
        """Select TKB radio button."""
        self.rb_tkb.click()

    def click_cmd(self):
        """Select CMD radio button."""
        self.rb_cmd.click()

    def set_rate(self, speed: int):
        """Set rate value for TX."""
        assert isinstance(speed, int), (
            f'Variable `speed` must be of type `int`, is `{type(speed)}`'
        )
        assert 0 < speed <= 12, 'Variable `speed` must have a value of 1 to 12.'

        s = self.edit.select()
        s.set_text(speed)
        self.click_set_button()

    def get_rate(self) -> int:
        """Get current rate value for TX."""
        s = self.edit.select()
        val = s.text_block()
        return int(val)


if __name__ == '__main__':
    gt = GonioToolWrapper()

    from IPython import embed

    embed()
