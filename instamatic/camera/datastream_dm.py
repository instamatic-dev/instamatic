import time
import multiprocessing

from .camera_dm import CameraDM

frame_buffer = multiprocessing.Queue(1024)
stream_buffer = multiprocessing.Queue(2048)

class DataStreamError(RuntimeError):
    pass

class StreamBufferError(RuntimeError):
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
        #print('Stopping data stream')

class StreamBuffer:
    """
    Start a new process to buffer and process data stream from camera
    Later it can be used to do more processing, such as drift correction
    """
    def __init__(self, exposure, frametime):
        self.stopProcEvent = multiprocessing.Event()
        self.clearBufferEvent = multiprocessing.Event()

        self.exposure = exposure
        self.frametime = frametime

    def run_proc(self, queue_in, queue_out):
        if self.exposure%self.frametime != 0:
            print('Exposure should be integer times of frametime')
            self.stop()
            return

        i = 0
        n = int(self.exposure/self.frametime)
        arr = queue_in.get()
        dim_x, dim_y = arr.shape
        arr = np.empty((dim_x, dim_y, n))
        try:
            while not self.stopProcEvent.is_set():
                for j in range(n):
                    tmp = queue_in.get()
                    arr[:,:,j] = tmp
                image = arr.mean(axis=2)
                queue_out.put(image)
                if i%10 == 0:
                    print(f"Number of images processed: {i}")
                i = i + 1
                #while self
        except:
            raise StreamBufferError(f'StreamBuffer encountered en error!')

    def start_loop(self):
        self.proc = multiprocessing.Process(target=self.run_proc, args=(frame_buffer,stream_buffer), daemon=True)
        self.proc.start()

    def stop(self):
        self.stopProcEvent.set()
        print('Stopping buffer stream')

    def clear_buffer(self):
        self.clearBufferEvent.set()

