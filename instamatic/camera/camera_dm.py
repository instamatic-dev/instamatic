import atexit
import os
import time
import decimal
import threading
from pathlib import Path
import numpy as np
from skimage.registration import phase_cross_correlation

import pyDMOneView as pyDM
from instamatic import config
from instamatic.utils import high_precision_timers
from instamatic.image_utils import translate_image

high_precision_timers.enable()

class LockingError(RuntimeError):
    pass

class InvalidNameError(RuntimeError):
    pass

class CameraDM:

    def __init__(self, name, frametime=config.settings.default_frame_time, numImg=1):

        if name not in ('DMK2', 'DMOneView', 'DMsimu_c', 'DMfaux', 'DMorius'):
            raise InvalidNameError(f"Please input a valid camera name!")

        libdrc = Path(__file__).parent

        self.lockfile = libdrc / 'DM.lockfile'
        #self.acquire_lock()

        self.frametime = frametime
        self.numImg = numImg

        self.is_connected = None

        atexit.register(self.uninit)

        self.name = name
        self.load_defaults()
        self.binsize = self.default_binsize

    def acquire_lock(self):
        try:
            os.rename(self.lockfile, self.lockfile)
            # WinError 32 if file is open by the same/another process
        except PermissionError:
            raise LockingError(f'Cannot establish lock to {self.lockfile} because it is used by another process')
        else:
            self._lock = open(self.lockfile)

        atexit.register(self.release_lock)

    def release_lock(self):
        self._lock.close()

    def init(self):
        pyDM.initCCDCOM()
        
        pyDM.initAcquisitionParam(self.processing, self.frametime, 
                                  self.binsize, self.binsize, 
                                  self.CCD_area[0], self.CCD_area[1], self.CCD_area[2], self.CCD_area[3],
                                  self.read_mode, self.quality_level, self.is_continuous)
        
        #pyDM.initAcquisitionMode(0)
        pyDM.prepareImgStack(self.numImg)

    def uninit(self):
        """Doesn't do anything."""
        pyDM.releaseImgStack()
        pyDM.releaseAcquisition()
        pyDM.releaseCCDCOM()

    def startAcquisition(self):
        """Equivalent to openShutteR?"""
        pyDM.startAcquireImgStack()

    def stopAcquisition(self):
        """Equivalent to closeShutter?"""
        pyDM.stopAcquireImgStack()

    def getImage(self, frametime=0.1, wait=0.02):
        #time.sleep(0.05)
        return pyDM.onAcquireImgStack(wait).squeeze()
        #return np.random.randint(65535, size=(self.dimensions[0], self.dimensions[1]))

    def get_from_buffer(self, queue, exposure, multiple=False, align=False):
        '''
        multiple: bool
            Toggle to average multiple images or not
        align: bool
            Toggle to align multiple images using phase_cross_correlation in scikit-image
        '''
        if not multiple:
            arr = queue.get()
            return arr.astype(np.uint16)
        else:
            self.clear_buffer(queue)
            n = int(decimal.Decimal(str(exposure)) / decimal.Decimal(str(self.frametime)))
            arr = queue.get()
            if n < 1:
                return arr.astype(np.uint16)
            for j in range(n-1):
                tmp = queue.get()
                if align:
                    shift, error, phasediff = phase_cross_correlation(arr, tmp)
                    tmp = translate_image(tmp, shift)
                arr += tmp
            arr = arr / n
            return arr.astype(np.uint16)

    def clear_buffer(self, queue):
        while not queue.empty():
            queue.get()

    def getCameraDimensions(self) -> (int, int):
        return self.dimensions

    def load_defaults(self):
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.__dict__.update(config.camera.mapping)

        self.streamable = True


def initialize(name='DM', frametime=0.1):

    cam = CameraDM(name=name, frametime=frametime)

    cam.init()

    print(f'Camera initialized (resolution: {cam.getCameraDimensions()})')

    return cam

def run_proc(queue, name):
    n = 100

    t = 0.1
    cam = initialize(name, frametime=t)

    cam.startAcquisition()
    time.sleep(2)

    arr = cam.getImage(wait=0.01)
    print(f'[ py hardware timer] -> shape: {arr.shape}')
    t0 = time.perf_counter()
    for i,x in enumerate(range(n)):
        arr = cam.getImage(wait=0.01)
        #arr = np.random.random((1024,1024))
        #queue.put(arr)
        if i%10 == 0:
            print(f"Number of images produced: {i}")
    print('producer done')
    print(arr)
    dt = time.perf_counter() - t0

    cam.stopAcquisition()
    print(f'Total time: {dt:.1f} s, acquisition time: {1000*(dt/n):.2f} ms, overhead: {1000*(dt/n - t):.2f} ms')

def run_thread(queue, exposure):
    n = 100

    for i,x in enumerate(range(n)):
        get_from_buffer(queue, exposure)
        if i%10 == 0:
            print(f"Number of images consumed: {i}")
    print('consumer done')

import multiprocessing
frame_buffer = multiprocessing.Queue()

if __name__ == '__main__':
    from IPython import embed
    import threading
    

    if False:
        run()
    if False:
        t = threading.Thread(target=run, args=(), daemon=True)
        t.start()
    if True:
        p = multiprocessing.Process(target = run_proc, args = (frame_buffer,'DMfaux'), daemon=True)
        p.start()
        #t = threading.Thread(target=run_thread, args=(frame_buffer,0.1,), daemon=True)
        #t.start()

    embed()
