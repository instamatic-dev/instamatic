import logging
from pathlib import Path
import ctypes

from instamatic import config
from instamatic.exceptions import HolderControllerError, HolderCommunicationError

class XNanoValueError(ValueError):
    pass

logger = logging.getLogger(__name__)

class XNanoHolder:
    """Python bindings to the XNano holder using the COM interface."""

    def __init__(self, name='xnano'):
        libdrc = Path(__file__).parent
        libpath = libdrc / 'holderCommand.dll'

        print('XNano holder initializing...')
        self.ip = config.holder.IP_Address
        self.lib = ctypes.cdll.LoadLibrary(str(libpath))

        self.lib.holderSend.argtypes = (ctypes.c_char_p, ctypes.POINTER(ctypes.c_byte), ctypes.c_int)
        self.lib.holderSend.restype = ctypes.c_int

        self.lib.getDistance.restype = ctypes.c_double

        self.lib.holderMove.argtypes = (ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_int)

        self.lib.holderFine.argtypes = (ctypes.c_int, ctypes.c_int)

        self.lib.holderRotateTo.argtypes = (ctypes.c_double, ctypes.c_int)

        self.lib.holderGotoX.argtypes = (ctypes.c_double,)

        self.lib.getCompCoef.argtypes = (ctypes.POINTER(ctypes.c_double),)

        self.lib.setCompCoef.argtypes = (ctypes.c_int, ctypes.c_double)

        t = 0
        while True:
            res = self.send("Hello World")
            if res == 0:
                break
            elif res == 1:
                raise HolderCommunicationError('Network initialization failed.')
            elif res == 2:
                raise HolderCommunicationError('UDP network interface initialization failed.')
            time.sleep(1)
            t += 1
            if t > 3:
                print(f'Waiting for the holder, t = {t}s')
            if t > 10:
                raise HolderCommunicationError('Cannot establish the connection to the holder (timeout).')

    def send(self, data):
        ip = bytes(self.ip, "ansi")
        n = 1
        if isinstance(data, int):
            DATA = ctypes.c_byte * 1
            send_data = DATA()
            send_data[0] = data
        if isinstance(data, str):
            n = len(data)
            DATA = ctypes.c_byte * n
            send_data = DATA()
            for i in range(n):
                send_data[i] = ord(data[i])

        return self.lib.holderSend(ip, send_data, n)

    def getHolderId(self):
        return self.lib.getHolderId()

    def getDistance(self):
        return self.lib.getDistance()

    def holderMove(self, axis, pulses, speed_hz, amp_raw):
        self.lib.holderMove(axis, pulse, speed_hz, amp_raw)

    def holderStop(self):
        self.lib.holderStop()

    def holderFine(self, axis, position):
        self.lib.holderFine(axis, position)

    def holderRotateTo(self, targetAngle, amp_raw):
        self.lib.holderRotateTo(ctypes.c_double(targetAngle), amp_raw)

    def holderGotoX(self, target):
        self.lib.holderGotoX(ctypes.c_double(target))

    def compCoefLength(self):
        self.lib.compCoefLength()

    def getCompCoef(self):
        TABLE = ctypes.c_double *24
        table = TABLE()
        
        self.lib.getCompCoef(table)

        return list(table)

    def setCompCoef(self, table):
        if isinstance(table) != list:
            raise XNanoValueError('Input parameter must be a list.')
        else:
            if len(table) != 24:
                raise XNanoValueError('Input parameter list must have 24 elements.')
        
        for i in range(24):
            self.lib.setCompCoef(i, ctypes.c_double(table[i]))
