from tkinter import *
from tkinter.ttk import *
from PIL import Image, ImageEnhance
from PIL import ImageTk
import threading
import numpy as np
import time
import datetime
from instamatic.formats import write_tiff
from .camera import Camera
import os, sys
from instamatic.gui.spinbox import Spinbox


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
        self.thread = threading.Thread(target=self.run, args=())
        self.thread.start()

    def end_loop(self):
        self.thread.stop()


class VideoStream(threading.Thread):
    """docstring for VideoStream"""
    def __init__(self, cam="simulate"):
        threading.Thread.__init__(self)

        self.cam = Camera(kind=cam)

        self.panel = None

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.defaults = self.cam.defaults
        self.name = self.cam.name

        self.frame_delay = 50

        self.frametime = 0.05
        self.brightness = 1.0
        self.disprang = self.disprang_default = self.defaults.dynamic_range
        # Maximum number from image readout

        self.auto_contrast = True

        self.resize_image = False

        self.last = time.clock()
        self.nframes = 1
        self.update_frequency = 0.25
        self.last_interval = self.frametime

        self._atexit_funcs = []
        self.stream = self.setup_stream()

        self.start()

    def run(self):
        self.root = Tk()
        
        self.init_vars()
        self.buttonbox(self.root)
        self.header(self.root)
        self.makepanel(self.root)

        # self.stopEvent = threading.Event()
 
        self.root.wm_title("Instamatic stream")
        self.root.wm_protocol("WM_DELETE_WINDOW", self.close)

        self.root.bind('<Escape>', self.close)

        self.root.bind('<<StreamAcquire>>', self.on_frame)
        self.root.bind('<<StreamEnd>>', self.close)
        self.root.bind('<<StreamFrame>>', self.on_frame)

        self.start_stream()
        self.root.mainloop()

    def header(self, master):
        ewidth = 8
        lwidth = 12

        frame = Frame(master)

        self.cb_resize = Checkbutton(frame, text="Increase size", variable=self.var_resize_image)
        self.cb_resize.grid(row=1, column=4)

        self.cb_contrast = Checkbutton(frame, text="Auto contrast", variable=self.var_auto_contrast)
        self.cb_contrast.grid(row=1, column=5)

        self.e_fps      = Entry(frame, width=lwidth, textvariable=self.var_fps, state=DISABLED)
        self.e_interval = Entry(frame, width=lwidth, textvariable=self.var_interval, state=DISABLED)
        # self.e_overhead    = Entry(frame, bd=0, width=ewidth, textvariable=self.var_overhead, state=DISABLED)
        
        Label(frame, width=lwidth, text="fps:").grid(row=1, column=0)
        self.e_fps.grid(row=1, column=1, sticky='we')
        Label(frame, width=lwidth, text="interval (ms):").grid(row=1, column=2)
        self.e_interval.grid(row=1, column=3, sticky='we')
        # Label(frame, width=lwidth, text="overhead (ms):").grid(row=1, column=4)
        # self.e_overhead.grid(row=1, column=5)
        
        frame.pack()

        frame = Frame(master)
        
        self.e_frametime = Spinbox(frame, width=ewidth, textvariable=self.var_frametime, from_=0.0, to=1.0, increment=0.01)
        
        Label(frame, width=lwidth, text="exposure (s)").grid(row=1, column=0)
        self.e_frametime.grid(row=1, column=1)

        self.e_brightness = Spinbox(frame, width=ewidth, textvariable=self.var_brightness, from_=0.0, to=10.0, increment=0.1)
        
        Label(frame, width=lwidth, text="Brightness").grid(row=1, column=2)
        self.e_brightness.grid(row=1, column=3)
        
        Label(frame, width=lwidth, text="DisplayRange").grid(row=1, column=4)
        self.e_disprang = Spinbox(frame, width=ewidth, textvariable=self.var_disprang, from_=1, to=self.disprang_default, increment=1000)
        self.e_disprang.grid(row=1, column=5)
        
        frame.pack()

    def makepanel(self, master, resolution=(512,512)):
        if self.panel is None:
            image = Image.fromarray(np.zeros(resolution))
            image = ImageTk.PhotoImage(image)

            self.panel = Label(image=image)
            self.panel.image = image
            self.panel.pack(side="left", padx=10, pady=10)

    def buttonbox(self, master):
        btn = Button(master, text="Save image",
            command=self.saveImage)
        btn.pack(side="bottom", fill="both", padx=10, pady=10)

    def init_vars(self):
        self.var_fps = DoubleVar()
        self.var_interval = DoubleVar()
        # self.var_overhead = DoubleVar()

        self.var_frametime = DoubleVar()
        self.var_frametime.set(self.frametime)
        self.var_frametime.trace("w", self.update_frametime)

        self.var_brightness = DoubleVar(value=self.brightness)
        self.var_brightness.trace("w", self.update_brightness)
        
        self.var_disprang = DoubleVar(value=self.disprang_default)
        self.var_disprang.trace("w",self.update_disprang)

        self.var_resize_image = BooleanVar(value=self.resize_image)
        self.var_resize_image.trace("w",self.update_resize_image)

        self.var_auto_contrast = BooleanVar(value=self.auto_contrast)
        self.var_auto_contrast.trace("w",self.update_auto_contrast)

    def update_resize_image(self, name, index, mode):
        # print name, index, mode
        try:
            self.resize_image = self.var_resize_image.get()
        except:
            pass

    def update_auto_contrast(self, name, index, mode):
        # print name, index, mode
        try:
            self.auto_contrast = self.var_auto_contrast.get()
        except:
            pass

    def update_frametime(self, name, index, mode):
        # print name, index, mode
        try:
            self.frametime = self.var_frametime.get()
        except:
            pass
        else:
            self.stream.frametime = self.frametime 

    def update_brightness(self, name, index, mode):
        # print name, index, mode
        try:
            self.brightness = self.var_brightness.get()
        except:
            pass
        
    def update_disprang(self, name, index, mode):
        try:
            val = self.var_disprang.get()
            self.disprang = max(1, val)
        except:
            pass

    def saveImage(self):
        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        write_tiff(outfile, self.frame)
        print(" >> Wrote file:", outfile)

    def close(self):
        for func in self._atexit_funcs:
            func()
        self.root.quit()

    def send_frame(self, frame, acquire=False):
        if acquire:
            self.stream.lock.acquire(True)
            self.acquired_frame = self.frame = frame
            self.stream.lock.release()
            self.stream.acquireCompleteEvent.set()
        else:
            self.stream.lock.acquire(True)
            self.frame = frame
            self.stream.lock.release()

        # these events feel fragile if fired in rapid succession
        # self.root.event_generate('<<StreamFrame>>', when='tail')

    def setup_stream(self):
        stream = ImageGrabber(self.cam, callback=self.send_frame, frametime=self.frametime)
        self._atexit_funcs.append(stream.stopEvent.set)
        return stream
    
    def start_stream(self):
        self.stream.start_loop()
        self.root.after(500, self.on_frame)

    def on_frame(self, event=None):
        self.stream.lock.acquire(True)
        frame = self.frame
        self.stream.lock.release()

        frame = np.rot90(frame, k=3)

        # the display range in ImageTk is from 0 to 256
        if self.auto_contrast:
            frame = frame * (256.0 / (1 + np.percentile(frame[::4,::4], 99.5)))  # use 128x128 array for faster calculation
                                                                                 
            image = Image.fromarray(frame)
        elif self.disprang != self.disprang_default:
            image = np.clip(frame, 0, self.disprang)
            image = (256.0 / self.disprang)*image
            image = Image.fromarray(image)
        else:
            image = Image.fromarray(frame)
            
        if self.brightness != 1:
            image = ImageEnhance.Brightness(image.convert("L")).enhance(self.brightness)
            # Can also use ImageEnhance.Sharpness or ImageEnhance.Contrast if needed
        
        if self.resize_image:
            image = image.resize((950, 950))

        image = ImageTk.PhotoImage(image=image)

        self.panel.configure(image=image)
        # keep a reference to avoid premature garbage collection
        self.panel.image = image

        self.update_frametimes()
        # self.root.update_idletasks()

        self.root.after(self.frame_delay, self.on_frame)

    def update_frametimes(self):
        self.current = time.clock()
        delta = self.current - self.last

        if delta > self.update_frequency:
            interval = delta/self.nframes

            interval = (interval * 0.5) + (self.last_interval * 0.5)

            fps = 1.0/interval
            # overhead = interval - self.stream.frametime

            self.var_fps.set(round(fps, 2))
            self.var_interval.set(round(interval*1000, 2))
            # self.var_overhead.set(round(overhead*1000, 2))
            self.last = self.current
            self.nframes = 1

            self.last_interval = interval
        else:
            self.nframes += 1

    def getImage(self, t=None, binsize=1):
        current_frametime = self.stream.frametime

        # set to 0 to prevent it lagging data acquisition
        self.stream.frametime = 0
        if t:
            self.stream.exposure = t
        if binsize:
            self.stream.binsize = binsize

        self.stream.acquireInitiateEvent.set()

        self.stream.acquireCompleteEvent.wait()

        self.stream.lock.acquire(True)
        frame = self.acquired_frame
        self.stream.lock.release()
        
        self.stream.acquireCompleteEvent.clear()
        self.stream.frametime = current_frametime
        return frame

    def block(self):
        self.stream.continuousCollectionEvent.set()

    def unblock(self):
        self.stream.continuousCollectionEvent.clear()

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


if __name__ == '__main__':
    stream = VideoStream(cam="timepix")
    from IPython import embed
    embed()
    stream.close()
