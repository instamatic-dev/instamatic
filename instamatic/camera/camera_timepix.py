import os, sys
import ctypes
from ctypes import *
from pathlib import Path

import numpy as np

import time
import traceback
import atexit

from instamatic import config

from instamatic.utils import high_precision_timers
high_precision_timers.enable()

# SoPhy > File > Medipix/Timepix control > Save parametrized settings
# Save updated config for timepix camera
CONFIG_PYTIMEPIX = "tpx"


class LockingError(RuntimeError):
    pass


def arrangeData(raw, out=None):
    """10000 loops, best of 3: 81.3 s per loop"""
    s  = 256*256
    q1 = raw[0  :s  ].reshape(256, 256)
    q2 = raw[s  :2*s].reshape(256, 256)
    q3 = raw[2*s:3*s][::-1].reshape(256, 256)
    q4 = raw[3*s:4*s][::-1].reshape(256, 256)

    if out is None:
        out = np.empty((516, 516), dtype=raw.dtype)
    out[0:256, 0:256] = q1
    out[0:256, 260:516] = q2
    out[260:516, 0:256] = q4
    out[260:516, 260:516] = q3

    return out


def correctCross(raw, factor=2.15):
    """100000 loops, best of 3: 18 us per loop"""
    raw[255:258] = raw[255] / factor
    raw[:,255:258] = raw[:,255:256] / factor

    raw[258:261] = raw[260] / factor
    raw[:,258:261] = raw[:,260:261] / factor


class CameraTPX(object):
    def __init__(self):
        libdrc = Path(__file__).parent

        self.lockfile = libdrc / "timepix.lockfile"
        self.acquire_lock()
        
        libpath = libdrc / "EMCameraObj.dll"
        curdir = Path.cwd()

        os.chdir(libdrc)
        self.lib = ctypes.cdll.LoadLibrary(str(libpath))
        os.chdir(curdir)
        
        # self.lib.EMCameraObj_readHwDacs.argtypes = [c_char]
        self.lib.EMCameraObj_Connect.restype = c_bool
        self.lib.EMCameraObj_Disconnect.restype = c_bool
        self.lib.EMCameraObj_timerExpired.restype = c_bool

        self.obj = self.lib.EMCameraObj_new()
        atexit.register(self.disconnect)
        self.is_connected = None

        self.name = self.getName()
        self.load_defaults()

    def acquire_lock(self):
        try:
            os.rename(self.lockfile, self.lockfile)
            # WinError 32 if file is open by the same/another process
        except PermissionError:
            raise LockingError(f"Cannot establish lock to {self.lockfile} because it is used by another process")
        else:
            self._lock = open(self.lockfile)

        atexit.register(self.release_lock)

    def release_lock(self):
        self._lock.close()

    def init(self):
        self.lib.EMCameraObj_Init(self.obj)

    def uninit(self):
        """Doesn't do anything"""
        self.lib.EMCameraObj_UnInit(self.obj)

    def connect(self, hwId):
        hwId = c_int(hwId)
        ret = self.lib.EMCameraObj_Connect(self.obj, hwId)
        if ret:
            self.is_connected = True
            print("Camera connected (hwId={})".format(hwId.value))
        else:
            raise IOError("Could not establish connection to camera.")
        return ret

    def disconnect(self):
        if not self.is_connected:
            return True
        ret = self.lib.EMCameraObj_Disconnect(self.obj)
        if ret:
            self.is_connected = False
            print("Camera disconnected")
        else:
            print("Camera disconnect failed...")
        return ret

    def getFrameSize(self):
        return self.lib.EMCameraObj_getFrameSize(self.obj)

    def readRealDacs(self, filename):
        "std::string filename"
        if not os.path.exists(filename):
            raise IOError("Cannot find `RealDacs` file: {}".format(filename))

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer
        
        try:
            self.lib.EMCameraObj_readRealDacs(self.obj, buffer)
        except Exception as e:
            traceback.print_exc()
            self.disconnect()
            sys.exit()

    def readHwDacs(self, filename):
        "std::string filename"
        if not os.path.exists(filename):
            raise IOError("Cannot find `HwDacs` file: {}".format(filename))

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer

        try:
            self.lib.EMCameraObj_readHwDacs(self.obj, buffer)
        except Exception as e:
            traceback.print_exc()
            self.disconnect()
            sys.exit()

    def readPixelsCfg(self, filename):
        "std::string filename"
        "int mode = TPX_MODE_DONT_SET  ->  set in header file"
        if not os.path.exists(filename):
            raise IOError("Cannot find `PixelsCfg` file: {}".format(filename))

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer

        try:
            self.lib.EMCameraObj_readPixelsCfg(self.obj, buffer)
        except Exception as e:
            traceback.print_exc()
            self.disconnect()
            sys.exit()

    def processRealDac(self, chipnr=None, index=None, key=None, value=None):
        "int *chipnr"
        "int *index"
        "std::string *key"
        "std::string *value"

        chipnr = c_int(0)
        index = c_int(0)
        key = create_unicode_buffer(20)
        value = create_unicode_buffer(20)

        self.lib.EMCameraObj_processRealDac(self.obj, byref(chipnr), byref(index), key, value)
    
    def processHwDac(self, key, value):
        "std::string *key"
        "std::string *value"

        key = create_unicode_buffer(20)
        value = create_unicode_buffer(20)
        self.lib.EMCameraObj_processHwDac(self.obj, byref(key), byref(value))
    
    def startAcquisition(self):
        """Equivalent to openShutteR?"""
        self.lib.EMCameraObj_startAcquisition(self.obj)
    
    def stopAcquisition(self):
        """Equivalent to closeShutter?"""       
        self.lib.EMCameraObj_stopAcquisition(self.obj)
    
    def openShutter(self):
        """Opens the Relaxd shutter under software control. Note
        that opening and closing the shutter under software control does
        not give a good control over the timing and should only be used
        for debugging or very long exposures where timing is less important."""
        self.lib.EMCameraObj_openShutter(self.obj)
    
    def closeShutter(self):
        """Closes shutter under software control."""
        self.lib.EMCameraObj_closeShutter(self.obj)
    
    def readMatrix(self, arr=None, sz=512*512):
        """Reads a frame from all connected devices, decodes the data
        and stores the pixel counts in array data.
        
        i16 *data # data storage array
        u32 sz    # size of array"""

        if arr is None:
            arr = np.empty(sz, dtype=np.int16)
    
        ref = np.ctypeslib.as_ctypes(arr)
        sz = ctypes.c_uint32(sz)

        # readout speed
        # 100 loops, best of 3: 7.52 ms per loop
        self.lib.EMCameraObj_readMatrix(self.obj, byref(ref), sz)

        return arr
    
    def enableTimer(self, enable, us):
        """Disables (enable is false) or enables the timer and sets the timer time-out
        to us microseconds. Note that the timer resolution is 10 us. After the Relaxd
        shutter opens (either explicitly by software or by an external trigger),
        it closes again after the set time.

        bool enable
        int us = 10 # microseconds"""

        enable = c_bool(enable)
        us = c_int(us)

        self.lib.EMCameraObj_enableTimer(self.obj, enable, us)
    
    def resetMatrix(self):
        self.lib.EMCameraObj_resetMatrix(self.obj)

    def timerExpired(self):
        return self.lib.EMCameraObj_timerExpired(self.obj)
    
    def setAcqPars(self, pars):
        "AcqParams *pars"

        raise NotImplementedError
        pars = AcqParams
        self.lib.EMCameraObj_setAcqPars(self.obj, byref(pars))
    
    def isBusy(self, busy):
        "bool *busy"

        busy = c_bool(busy)
        self.lib.EMCameraObj_isBusy(self.obj, byref(busy))

    def acquireData(self, exposure=0.001):
        microseconds = int(exposure * 1e6)  # seconds to microseconds
        self.enableTimer(True, microseconds)

        self.openShutter()

        # sleep here to avoid burning cycles
        # only sleep if exposure is longer than Windows timer resolution, i.e. 1 ms
        if exposure > 0.001:
            time.sleep(exposure - 0.001)

        while not self.timerExpired():
            pass
            
        # self.closeShutter()
        
        arr = self.readMatrix()

        out = arrangeData(arr)
        correctCross(out, factor=self.correction_ratio)

        out = np.rot90(out, k=3)

        return out

    def getImage(self, exposure):
        return self.acquireData(exposure=exposure)

    def getName(self):
        return "timepix"

    def getDimensions(self):
        return self.dimensions

    def load_defaults(self):
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = True


def initialize(config):
    from pathlib import Path

    base = Path(config).parent
    
    # read config.txt
    with open(config, "r") as f:
        for line in f:
            inp = line.split()
            if inp[0] == "HWID":
                hwId = int(inp[1])
            if inp[0] == "HWDACS":
                hwDacs = base / inp[1]
            if inp[0] == "PIXELDACS":
                realDacs = base / inp[1]
            if inp[0] == "PIXELBPC":
                pixelsCfg = base / inp[1]

    cam = CameraTPX()
    isConnected = cam.connect(hwId)
    
    cam.init()

    cam.readHwDacs(hwDacs)
    cam.readPixelsCfg(pixelsCfg)
    cam.readRealDacs(realDacs)

    print(f"Camera {cam.getName()} initialized (resolution: {cam.getDimensions()})")

    return cam


if __name__ == '__main__':
    from IPython import embed

    """To restart the camera in case SoPhy hangs,
        in terminal on linux pc:
            ./stopcooling
            ./startcooling
    """

    base = Path("..\\instamatic\\camera\\tpx").resolve()

    print(base)
    print()

    config = base / "config.txt"
    
    cam = initialize(config)
       
    if True:
        t = 0.01
        n = 100

        arr = cam.acquireData(t)
        print("[ py hardware timer] -> shape: {}".format(arr.shape))
        t0 = time.perf_counter()
        for x in range(n):
            cam.acquireData(t)
        dt = time.perf_counter() - t0
        print(f"Total time: {dt:.1f} s, acquisition time: {1000*(dt/n):.2f} ms, overhead: {1000*(dt/n - t):.2f} ms")
    
    embed(banner1='')
    
    isDisconnected = cam.disconnect()
