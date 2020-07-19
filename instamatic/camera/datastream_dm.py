import time
import multiprocessing

from .camera_dm import CameraDM

frame_buffer = multiprocessing.Queue(1024)

def get_from_buffer(queue, exposure):
    time.sleep(exposure+0.006)
    return queue.get()

class DataStreamError(RuntimeError):
    pass

class CameraDataStream:
    """
    Start a new process and continuously call getImage to obtain image data from Gatan cameras
    """
    def __init__(self, cam, frametime):
        self.cam = CameraDM(cam, exposure=frametime)
        self.stopProcEvent = multiprocessing.Event()

    def run_proc(self, queue):
        i = 0
        try:
            self.cam.init()
            self.cam.startAcquisition()
            time.sleep(0.5)
            print('test')
            while not self.stopProcEvent.is_set():
                arr = self.cam.getImage(exposure=self.cam.exposure)
                queue.put(arr)
                if i%10 == 0:
                    print(f"Number of images produced: {i}")
                i = i + 1
        except:
            raise DataStreamError(f'CameraDataStream encountered en error!')
        finally:
            self.cam.stopAcquisition()

    def start_loop(self):
        self.proc = multiprocessing.Process(target=self.run_proc, args=(frame_buffer,), daemon=True)
        self.proc.start()

    def stop(self):
        self.stopProcEvent.set()
        print('Stopping data stream')

