import threading
from .camera import Camera
import numpy as np
from instamatic.tools import autoscale


class VideoStream(threading.Thread):
    """docstring for VideoStream"""
    def __init__(self, cam="simulate"):
        threading.Thread.__init__(self)

        if isinstance(cam, str):
            self.cam = Camera(name=cam, as_stream=False)
        else:
            self.cam = cam

        self.lock = threading.Lock()

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.name = self.cam.name

        self.frametime = self.default_exposure

        self.streamable = self.cam.streamable

        self.display_dim = 512

        self.frame, scale = autoscale(np.ones(self.dimensions), maxdim=self.display_dim)

    def __getattr__(self, attrname):
        """Pass attribute lookups to self.cam to prevent AttributeError"""
        try:
            return object.__getattribute__(self, attrname)
        except AttributeError as e:
            reraise_on_fail = e
            try:
                return getattr(self.cam, attrname)
            except AttributeError:
                raise reraise_on_fail

    def getImage(self, exposure=None, binsize=None):
        frame = self.cam.getImage(exposure=exposure, binsize=binsize)

        self.frame, scale = autoscale(frame, maxdim=self.display_dim)

        return frame

    def update_frametime(self, frametime):
        self.frametime = frametime

    def close(self):
        pass

    def block(self):
        pass

    def unblock(self):
        pass

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

            img = self.getImage(exposure=exposure)

            if callback:
                go_on = callback(img)
            else:
                buffer.append(img)
                go_on = i < n

        self.unblock()

        if not callback:
            return buffer

    def show_stream(self):
        from instamatic.gui import videostream_frame
        t = threading.Thread(target=videostream_frame.start_gui, args=(self, ), daemon=False)
        t.start()


if __name__ == '__main__':
    stream = VideoStream(cam="timepix")
    from IPython import embed
    embed()
    stream.stop()
