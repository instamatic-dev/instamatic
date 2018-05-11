from tkinter import *
from tkinter.ttk import *
from PIL import Image, ImageEnhance
from PIL import ImageTk
import threading
from instamatic.formats import write_tiff
from .camera import Camera
from instamatic.utils.spinbox import Spinbox
import atexit


class ImageGrabber(object):
    """docstring for ImageGrabber"""
    def __init__(self, cam, callback, frametime=0.05):
        super(ImageGrabber, self).__init__()
        
        self.callback = callback
        self.cam = cam

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.defaults = self.cam.defaults
        self.name = self.cam.name

        self.frame = None
        self.thread = None
        self.stopEvent = None

        self.stash = None

        self.frametime = frametime
        self.exposure = self.frametime
        self.binsize = self.cam.default_binsize

        self.lock = threading.Lock()

        self.stopEvent = threading.Event()
        self.acquireInitiateEvent = threading.Event()
        self.acquireCompleteEvent = threading.Event()
        self.continuousCollectionEvent = threading.Event()

    def run(self):
        while not self.stopEvent.is_set():

            if self.acquireInitiateEvent.is_set():
                self.acquireInitiateEvent.clear()
                
                frame = self.cam.getImage(t=self.exposure, fastmode=True)
                self.callback(frame, acquire=True)

            elif not self.continuousCollectionEvent.is_set():
                frame = self.cam.getImage(t=self.frametime, fastmode=True)
                self.callback(frame)

    def start_loop(self):
        self.thread = threading.Thread(target=self.run, args=(), daemon=True)
        self.thread.start()

    def stop(self):
        self.stopEvent.set()
        self.thread.join()


class VideoStream(threading.Thread):
    """docstring for VideoStream"""
    def __init__(self, cam="simulate"):
        threading.Thread.__init__(self)

        if isinstance(cam, str):
            self.cam = Camera(kind=cam)
        else:
            self.cam = cam

        self.lock = threading.Lock()

        self.panel = None

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.defaults = self.cam.defaults
        self.name = self.cam.name

        self.frametime = self.default_exposure

        self.grabber = self.setup_grabber()

        self.start()

    def start(self):
        self.grabber.start_loop()

    def send_frame(self, frame, acquire=False):
        if acquire:
            self.grabber.lock.acquire(True)
            self.acquired_frame = self.frame = frame
            self.grabber.lock.release()
            self.grabber.acquireCompleteEvent.set()
        else:
            self.grabber.lock.acquire(True)
            self.frame = frame
            self.grabber.lock.release()

    def setup_grabber(self):
        grabber = ImageGrabber(self.cam, callback=self.send_frame, frametime=self.frametime)
        atexit.register(grabber.stop)
        return grabber

    def getImage(self, t=None, binsize=1):
        current_frametime = self.grabber.frametime

        # set to 0 to prevent it lagging data acquisition
        self.grabber.frametime = 0
        if t:
            self.grabber.exposure = t
        if binsize:
            self.grabber.binsize = binsize

        self.grabber.acquireInitiateEvent.set()

        self.grabber.acquireCompleteEvent.wait()

        self.grabber.lock.acquire(True)
        frame = self.acquired_frame
        self.grabber.lock.release()
        
        self.grabber.acquireCompleteEvent.clear()
        self.grabber.frametime = current_frametime
        return frame

    def update_frametime(self, frametime):
        self.frametime = frametime
        self.grabber.frametime = frametime

    def close(self):
        self.grabber.stop()

    def block(self):
        self.grabber.continuousCollectionEvent.set()

    def unblock(self):
        self.grabber.continuousCollectionEvent.clear()

    def continuous_collection(self, exposure=0.1, n=100, callback=None):
        """
        Function to continuously collect data
        Blocks the videostream while collecting data, and only shows collected images

        exposure: float
            exposure time
        n: int
            number of frames to collect
            if defined, returns a list of collected frames
        callback: function
            This function is called on every iteration with the image as first argument
            Should return True or False if data collection is to continue
        """
        buffer = []

        go_on = True
        i = 0

        self.block()
        while go_on:
            i += 1

            img = self.getImage(t=exposure)

            if callback:
                go_on = callback(img)
            else:
                buffer.append(img)
                go_on = i < n

        self.unblock()

        if not callback:
            return buffer

    def start_gui(self):
        from instamatic.gui import videostream_frame
        t = threading.Thread(target=videostream_frame.start_gui, args=(self, ), daemon=True)
        t.start()


if __name__ == '__main__':
    stream = VideoStream(cam="timepix")
    from IPython import embed
    embed()
    stream.stop()
