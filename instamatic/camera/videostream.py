from Tkinter import *
from PIL import Image, ImageEnhance
from PIL import ImageTk
import threading
import numpy as np
import time
import datetime
from instamatic.formats import write_tiff
from camera import Camera
import os, sys


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

        self.last = time.time()
        self.nframes = 1
        self.update_frequency = 0.25
        self.last_interval = self.frametime

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
        ewidth = 10
        lwidth = 12

        frame = Frame(master)
        self.e_fps         = Entry(frame, bd=0, width=ewidth, textvariable=self.var_fps, state=DISABLED)
        self.e_interval = Entry(frame, bd=0, width=ewidth, textvariable=self.var_interval, state=DISABLED)
        # self.e_overhead    = Entry(frame, bd=0, width=ewidth, textvariable=self.var_overhead, state=DISABLED)
        
        Label(frame, anchor=E, width=lwidth, text="fps:").grid(row=1, column=0)
        self.e_fps.grid(row=1, column=1)
        Label(frame, anchor=E, width=lwidth, text="interval (ms):").grid(row=1, column=2)
        self.e_interval.grid(row=1, column=3)
        # Label(frame, anchor=E, width=lwidth, text="overhead (ms):").grid(row=1, column=4)
        # self.e_overhead.grid(row=1, column=5)
        
        frame.pack()

        frame = Frame(master)
        
        self.e_frametime = Spinbox(frame, width=ewidth, textvariable=self.var_frametime, from_=0.0, to=1.0, increment=0.01)
        
        Label(frame, anchor=E, width=lwidth, text="exposure (s)").grid(row=1, column=0)
        self.e_frametime.grid(row=1, column=1)

        self.e_brightness = Spinbox(frame, width=ewidth, textvariable=self.var_brightness, from_=0.0, to=10.0, increment=0.1)
        
        Label(frame, anchor=E, width=lwidth, text="Brightness").grid(row=1, column=2)
        self.e_brightness.grid(row=1, column=3)
        
        frame.pack()

    def makepanel(self, master, resolution=(512,512)):
        if self.panel is None:
            image = Image.fromarray(np.zeros(resolution))
            image = ImageTk.PhotoImage(image)

            self.panel = Label(image=image)
            self.panel.image = image
            self.panel.pack(side="left", padx=10, pady=10)

    def buttonbox(self, master):
        frame = LabelFrame(master, text="Experiment control")
        frame.pack(side="right", fill="both", expand="yes", padx=10, pady=10)

        ########################################################
        
        frame_io = LabelFrame(frame, text="Input/output")

        self.directory = Entry(frame_io, width=50, textvariable=self.var_directory)
        self.directory.grid(row=2, column=1)

        self.BrowseButton = Button(frame_io, text="Browse..", command=self.browse_directory)
        self.BrowseButton.grid(row=2, column=2)
        
        self.sample_name = Entry(frame_io, width=50, textvariable=self.var_sample_name)
        self.sample_name.grid(row=3, column=1)
        
        Label(frame_io, width=30, text="Directory:").grid(row=2, column=0)
        Label(frame_io, width=30, text="Sample name:").grid(row=3, column=0)

        self.incrementer = Spinbox(frame_io, from_=0, to=999, increment=1, textvariable=self.var_experiment_number)
        self.incrementer.grid(row=3, column=2)

        frame_io.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
        
        ########################################################

        frame_cred = LabelFrame(frame, text="Continuous rotation electron diffraction")
        Label(frame_cred, width=30,text="Exposure time").grid(row=4, column=0)
        self.exposure_time = Entry(frame_cred, width=50, textvariable=self.var_exposure_time)
        self.exposure_time.grid(row=4, column=1)

        self.CollectionButton = Button(frame_cred, text="Start Collection", command=self.start_cred_collection, anchor=W)
        self.CollectionButton.grid(row=10, column=0)

        self.CollectionStopButton = Button(frame_cred, text="Stop Collection", command=self.stop_cred_collection, anchor=W)
        self.CollectionStopButton.grid(row=11 , column=0)

        self.CollectionContButton = Button(frame_cred, text="Continue Collection", command=None, anchor=W)
        self.CollectionContButton.grid(row=12, column=0)

        self.CollectionContButton = Button(frame_cred, text="Exit", command=self.exit_collection, anchor=W)
        self.CollectionContButton.grid(row=13, column=0)

        frame_cred.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
            
        ########################################################

        frame_sed = LabelFrame(frame, text="Serial electron diffraction")

        self.CollectionButton = Button(frame_sed, text="Start Collection", command=self.start_sed_collection, anchor=W)
        self.CollectionButton.grid(row=10, column=0)

        self.CollectionStopButton = Button(frame_sed, text="Stop Collection (Does nothing)", command=self.stop_sed_collection, anchor=W)
        self.CollectionStopButton.grid(row=11 , column=0)

        frame_sed.pack(side="top", fill="both", expand="yes", padx=10, pady=10)

        ########################################################

        btn = Button(master, text="Save image",
            command=self.saveImage)
        btn.pack(side="bottom", fill="both", expand="yes", padx=10, pady=10)

    def browse_directory(self):
        import tkFileDialog
        drc = tkFileDialog.askdirectory(parent=self.root, title="Select working directory")
        self.var_directory.set(drc)
        print self.get_experiment_directory()
        return drc

    def get_working_directory(self):
        drc = self.var_directory.get()
        return drc

    def get_experiment_directory(self):
        drc = self.var_directory.get()
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        path = os.path.join(drc, "{}_{}".format(name, number))
        return path

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_sed_events(self, startEvent=None, stopEvent=None, exitEvent=None):
        self.startEvent_SED = startEvent
        self.stopEvent_SED = stopEvent
        self.exitEvent = exitEvent

    def start_sed_collection(self):
        print "Start button pressed"
        self.startEvent_SED.set()
        self.triggerEvent.set()

    def stop_sed_collection(self):
        print "Stop button pressed"
        self.stopEvent_SED.set()

    def set_cred_events(self, startEvent=None, stopEvent=None, exitEvent=None):
        self.startEvent_cRED = startEvent
        self.stopEvent_cRED = stopEvent
        self.exitEvent = exitEvent

    def start_cred_collection(self):
        print "Start button pressed"
        self.startEvent_cRED.set()
        self.triggerEvent.set()

    def stop_cred_collection(self):
        print "Stop button pressed"
        self.stopEvent_cRED.set()

    def exit_collection(self):
        print "exiting"
        self.exitEvent.set()
        self.triggerEvent.set()

    def init_vars(self):
        self.var_fps = DoubleVar()
        self.var_interval = DoubleVar()
        # self.var_overhead = DoubleVar()

        self.var_frametime = DoubleVar()
        self.var_frametime.set(self.frametime)
        self.var_frametime.trace("w", self.update_frametime)

        self.var_brightness = DoubleVar(value=1.0)
        self.var_brightness.set(self.brightness)
        self.var_brightness.trace("w", self.update_brightness)

        # Button box
        self.var_fps = DoubleVar()
        self.var_interval = DoubleVar()
        self.var_directory = StringVar(value="C:/")
        self.var_sample_name = StringVar(value="experiment")
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_experiment_number = IntVar(value=1)

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

    def saveImage(self):
        drc = self.get_directory()
        if not os.path.exists(drc):
            os.mkdir(drc)
        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        outfile = os.path.join(drc, outfile)
        write_tiff(outfile, self.frame)
        print " >> Wrote file:", outfile

    def close(self):
        self.stream.stopEvent.set()
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
        return ImageGrabber(self.cam, callback=self.send_frame, frametime=self.frametime)
    
    def start_stream(self):
        self.stream.start_loop()
        self.root.after(500, self.on_frame)

    def on_frame(self, event=None):
        self.stream.lock.acquire(True)
        frame = self.frame
        self.stream.lock.release()

        frame = np.rot90(frame, k=3)

        if self.brightness != 1:
            image = Image.fromarray(frame).convert("L")
            image = ImageEnhance.Brightness(image).enhance(self.brightness)
            # Can also use ImageEnhance.Sharpness or ImageEnhance.Contrast if needed

        else:
            image = Image.fromarray(frame)

        image = ImageTk.PhotoImage(image=image)

        self.panel.configure(image=image)
        # keep a reference to avoid premature garbage collection
        self.panel.image = image

        self.update_frametimes()
        # self.root.update_idletasks()

        self.root.after(self.frame_delay, self.on_frame)

    def update_frametimes(self):
        self.current = time.time()
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
    stream = VideoStream(cam="simulate")
    from IPython import embed
    embed()
    stream.close()