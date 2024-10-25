from __future__ import annotations

import atexit
import ctypes
import os
import sys
import time
import traceback
from ctypes import *
from pathlib import Path

import numpy as np

from instamatic import config
from instamatic.camera.camera_base import CameraBase
from instamatic.utils import high_precision_timers

high_precision_timers.enable()

# SoPhy > File > Medipix/Timepix control > Save parametrized settings
# Save updated config for timepix camera
CONFIG_PYTIMEPIX = 'tpx'


class LockingError(RuntimeError):
    pass


def arrange_data(raw, out=None):
    """10000 loops, best of 3: 81.3 s per loop."""
    s = 256 * 256
    q1 = raw[0:s].reshape(256, 256)
    q2 = raw[s : 2 * s].reshape(256, 256)
    q3 = raw[2 * s : 3 * s][::-1].reshape(256, 256)
    q4 = raw[3 * s : 4 * s][::-1].reshape(256, 256)

    if out is None:
        out = np.empty((516, 516), dtype=raw.dtype)
    out[0:256, 0:256] = q1
    out[0:256, 260:516] = q2
    out[260:516, 0:256] = q4
    out[260:516, 260:516] = q3

    return out


def correct_cross(raw, factor=2.15):
    """100000 loops, best of 3: 18 us per loop."""
    raw[255:258] = raw[255] / factor
    raw[:, 255:258] = raw[:, 255:256] / factor

    raw[258:261] = raw[260] / factor
    raw[:, 258:261] = raw[:, 260:261] / factor


class CameraTPX(CameraBase):
    streamable = True

    def __init__(self, name='pytimepix'):
        super().__init__(name)
        libdrc = Path(__file__).parent

        self.lockfile = libdrc / 'timepix.lockfile'
        self.acquire_lock()

        libpath = libdrc / 'EMCameraObj.dll'
        curdir = Path.cwd()

        os.chdir(libdrc)
        self.lib = ctypes.cdll.LoadLibrary(str(libpath))
        os.chdir(curdir)

        # self.lib.EMCameraObj_readHwDacs.argtypes = [c_char]
        self.lib.EMCameraObj_Connect.restype = c_bool
        self.lib.EMCameraObj_Disconnect.restype = c_bool
        self.lib.EMCameraObj_timerExpired.restype = c_bool

        self.obj = self.lib.EMCameraObj_new()
        atexit.register(self.release_connection)
        self.is_connected = None

    def acquire_lock(self):
        try:
            os.rename(self.lockfile, self.lockfile)
            # WinError 32 if file is open by the same/another process
        except PermissionError:
            raise LockingError(
                f'Cannot establish lock to {self.lockfile} because it is used by another process'
            )
        else:
            self._lock = open(self.lockfile)

        atexit.register(self.release_lock)

    def release_lock(self):
        self._lock.close()

    def init(self):
        self.lib.EMCameraObj_Init(self.obj)

    def uninit(self):
        """Doesn't do anything."""
        self.lib.EMCameraObj_UnInit(self.obj)

    def establish_connection(self, hwId):
        hwId = c_int(hwId)
        ret = self.lib.EMCameraObj_Connect(self.obj, hwId)
        if ret:
            self.is_connected = True
            print(f'Camera connected (hwId={hwId.value})')
        else:
            raise OSError('Could not establish connection to camera.')
        return ret

    def connect(self):
        self.establish_connection()

    def release_connection(self):
        if not self.is_connected:
            return True
        ret = self.lib.EMCameraObj_Disconnect(self.obj)
        if ret:
            self.is_connected = False
            print('Camera disconnected')
        else:
            print('Camera disconnect failed...')
        return ret

    def disconnect(self):
        self.release_connection()

    def get_frame_size(self):
        return self.lib.EMCameraObj_getFrameSize(self.obj)

    def read_real_dacs(self, filename):
        """std::string filename."""
        if not os.path.exists(filename):
            raise OSError(f'Cannot find `RealDacs` file: {filename}')

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer

        try:
            self.lib.EMCameraObj_readRealDacs(self.obj, buffer)
        except BaseException:
            traceback.print_exc()
            self.release_connection()
            sys.exit()

    def read_hw_dacs(self, filename):
        """std::string filename."""
        if not os.path.exists(filename):
            raise OSError(f'Cannot find `HwDacs` file: {filename}')

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer

        try:
            self.lib.EMCameraObj_readHwDacs(self.obj, buffer)
        except BaseException:
            traceback.print_exc()
            self.release_connection()
            sys.exit()

    def read_pixels_cfg(self, filename):
        """std::string filename."""
        'int mode = TPX_MODE_DONT_SET  ->  set in header file'
        if not os.path.exists(filename):
            raise OSError(f'Cannot find `PixelsCfg` file: {filename}')

        filename = str(filename).encode()
        buffer = create_string_buffer(filename)
        # print buffer.value, len(buffer), buffer

        try:
            self.lib.EMCameraObj_readPixelsCfg(self.obj, buffer)
        except BaseException:
            traceback.print_exc()
            self.release_connection()
            sys.exit()

    def process_real_dac(self, chipnr=None, index=None, key=None, value=None):
        """Int *chipnr."""
        'int *index'
        'std::string *key'
        'std::string *value'

        chipnr = c_int(0)
        index = c_int(0)
        key = create_unicode_buffer(20)
        value = create_unicode_buffer(20)

        self.lib.EMCameraObj_processRealDac(self.obj, byref(chipnr), byref(index), key, value)

    def process_hw_dac(self, key, value):
        """std::string *key."""
        'std::string *value'

        key = create_unicode_buffer(20)
        value = create_unicode_buffer(20)
        self.lib.EMCameraObj_processHwDac(self.obj, byref(key), byref(value))

    def start_acquisition(self):
        """Equivalent to openShutter?"""
        self.lib.EMCameraObj_startAcquisition(self.obj)

    def stop_acquisition(self):
        """Equivalent to close_shutter?"""
        self.lib.EMCameraObj_stopAcquisition(self.obj)

    def open_shutter(self):
        """Opens the Relaxd shutter under software control.

        Note that opening and closing the shutter under software control
        does not give a good control over the timing and should only be
        used for debugging or very long exposures where timing is less
        important.
        """
        self.lib.EMCameraObj_openShutter(self.obj)

    def close_shutter(self):
        """Closes shutter under software control."""
        self.lib.EMCameraObj_closeShutter(self.obj)

    def read_matrix(self, arr=None, sz=512 * 512):
        """Reads a frame from all connected devices, decodes the data and
        stores the pixel counts in array data.

        i16 *data # data storage array u32 sz    # size of array
        """
        if arr is None:
            arr = np.empty(sz, dtype=np.int16)

        ref = np.ctypeslib.as_ctypes(arr)
        sz = ctypes.c_uint32(sz)

        # readout speed
        # 100 loops, best of 3: 7.52 ms per loop
        self.lib.EMCameraObj_readMatrix(self.obj, byref(ref), sz)

        return arr

    def enable_timer(self, enable, us):
        """Disables (enable is false) or enables the timer and sets the timer
        time-out to us microseconds. Note that the timer resolution is 10 us.
        After the Relaxd shutter opens (either explicitly by software or by an
        external trigger), it closes again after the set time.

        bool enable int us = 10 # microseconds
        """
        enable = c_bool(enable)
        us = c_int(us)

        self.lib.EMCameraObj_enableTimer(self.obj, enable, us)

    def reset_matrix(self):
        self.lib.EMCameraObj_resetMatrix(self.obj)

    def timer_expired(self):
        return self.lib.EMCameraObj_timerExpired(self.obj)

    def set_acq_pars(self, pars):
        """AcqParams *pars."""
        raise NotImplementedError
        pars = AcqParams
        self.lib.EMCameraObj_setAcqPars(self.obj, byref(pars))

    def is_busy(self, busy):
        """Bool *busy."""
        busy = c_bool(busy)
        self.lib.EMCameraObj_isBusy(self.obj, byref(busy))

    def acquire_data(self, exposure=0.001):
        microseconds = int(exposure * 1e6)  # seconds to microseconds
        self.enable_timer(True, microseconds)

        self.open_shutter()

        # sleep here to avoid burning cycles
        # only sleep if exposure is longer than Windows timer resolution, i.e. 1 ms
        if exposure > 0.001:
            time.sleep(exposure - 0.001)

        while not self.timer_expired():
            pass

        # self.close_shutter()

        arr = self.read_matrix()

        out = arrange_data(arr)
        correct_cross(out, factor=self.correction_ratio)

        out = np.rot90(out, k=3)

        return out

    def get_image(self, exposure):
        return self.acquire_data(exposure=exposure)

    def get_name(self):
        return 'timepix'


def initialize(tpx_config_file, name='pytimepix') -> CameraTPX:
    base = Path(tpx_config_file).parent

    # read config.txt
    with open(tpx_config_file) as f:
        for line in f:
            inp = line.split()
            if inp[0] == 'HWID':
                hwId = int(inp[1])
            if inp[0] == 'HWDACS':
                hwDacs = base / inp[1]
            if inp[0] == 'PIXELDACS':
                realDacs = base / inp[1]
            if inp[0] == 'PIXELBPC':
                pixelsCfg = base / inp[1]

    cam = CameraTPX(name=name)
    cam.establish_connection(hwId)

    cam.init()

    cam.read_hw_dacs(hwDacs)
    cam.read_pixels_cfg(pixelsCfg)
    cam.read_real_dacs(realDacs)

    print(f'Camera {cam.get_name()} initialized (resolution: {cam.get_camera_dimensions()})')

    return cam


if __name__ == '__main__':
    from IPython import embed

    """To restart the camera in case SoPhy hangs,
        in terminal on linux pc:
            ./stopcooling
            ./startcooling
    """

    base = (Path(__file__).parent / 'tpx').resolve()

    print(base)
    print()

    tpx_config_file = base / 'config.txt'

    cam = initialize(tpx_config_file)

    if True:
        t = 0.01
        n = 100

        arr = cam.acquire_data(t)
        print(f'[ py hardware timer] -> shape: {arr.shape}')
        t0 = time.perf_counter()
        for x in range(n):
            cam.acquire_data(t)
        dt = time.perf_counter() - t0
        print(
            f'Total time: {dt:.1f} s, acquisition time: {1000 * (dt / n):.2f} ms, overhead: {1000 * (dt / n - t):.2f} ms'
        )

    embed(banner1='')

    isDisconnected = cam.release_connection()
