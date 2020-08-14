import time
import multiprocessing
import threading
import queue
import decimal
import numpy as np

from .camera_dm import CameraDM

frame_buffer = multiprocessing.Queue(2)
stream_buffer_proc = multiprocessing.Queue(2048)
stream_buffer_thread = queue.Queue(2048)

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
        #i = 0
        try:
            self.cam.init()
            self.cam.startAcquisition()
            time.sleep(0.5)
            while not self.stopProcEvent.is_set():
                arr = self.cam.getImage(exposure=self.cam.exposure)
                queue.put(arr)
                #if i%10 == 0:
                #    print(f"Number of images produced: {i}")
                #i = i + 1
        except:
            raise DataStreamError(f'CameraDataStream encountered en error!')
        finally:
            self.cam.stopAcquisition()

    def start_loop(self):
        self.stopProcEvent.clear()
        self.proc = multiprocessing.Process(target=self.run_proc, args=(frame_buffer,), daemon=True)
        self.proc.start()

    def stop(self):
        self.stopProcEvent.set()
        time.sleep(0.5)
        print('\nStopping the data stream')

class StreamBuffer:
    """
    Base class for StreamBufferProc and StreamBufferThread
    """
    def __init__(self, exposure, frametime):
        self.stopEvent = None

        self.exposure = exposure
        self.frametime = frametime

    def run_proc(self, queue_in, queue_out):        
        # i = 0
        try:
            arr = queue_in.get()
            dim_x, dim_y = arr.shape
            self.stopEvent.clear()

            while not self.stopEvent.is_set():
                n = decimal.Decimal(str(self.exposure)) / decimal.Decimal(str(self.frametime))
                if n != int(n):
                    print(f"Exposure should be integer times of frametime.")
                    self.stop()
                    return

                arr = np.empty((dim_x, dim_y))
                t0 = time.perf_counter()
                for j in range(int(n)):
                    if not self.stopEvent.is_set():
                        tmp = queue_in.get()
                        arr += tmp
                    else:
                        break
                dt = time.perf_counter() - t0
                image = arr / (j + 1)
                queue_out.put_nowait(image)
                #if i%2 == 0:
                    #print(f"Number of images processed: {i} {n}")
                print(f"Frame Buffer: {queue_in.qsize()}, Stream Buffer: {queue_out.qsize()}, Actual time: {dt}")
                #i = i + 1
        except:
            raise StreamBufferError(f"StreamBuffer encountered en error!")

    def start_loop(self):
        pass

    def stop(self):
        self.stopEvent.set()
        time.sleep(0.1)
        print('\nStopping the buffer stream')

    

class StreamBufferProc(StreamBuffer):
    """
    Start a new process to buffer and process data stream from camera
    Later it can be used to do more computational entensive online processing, such as drift correction
    However, you need restart the process before you can change the exposure parameter
    """
    def __init__(self, exposure, frametime):
        super().__init__(exposure, frametime)
        self.stopEvent = multiprocessing.Event()

    def start_loop(self):
        self.proc = multiprocessing.Process(target=self.run_proc, args=(frame_buffer,stream_buffer_proc), daemon=True)
        self.proc.start()

class StreamBufferThread(StreamBuffer):
    """
    Start a new thread to buffer and process data stream from camera
    Later it can be used to do more processing, such as drift correction, but not so computational entensive because it will
    slow the response for the main program
    The good thing is you can easily change the exposure time.
    """
    def __init__(self, exposure, frametime):
        super().__init__(exposure, frametime)
        self.stopEvent = threading.Event()

    def start_loop(self):
        self.thread = threading.Thread(target=self.run_proc, args=(frame_buffer,stream_buffer_thread), daemon=True)
        self.thread.start()


if __name__ == '__main__':
    from instamatic import config
    data_stream = CameraDataStream(cam=config.camera.name, frametime=0.3)
    data_stream.start_loop()
    image_stream = StreamBufferProc(exposure=0.6, frametime=0.3)
    image_stream.start_loop()
    from IPython import embed
    embed()
