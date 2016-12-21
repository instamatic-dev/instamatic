from Tkinter import *
from PIL import Image
from PIL import ImageTk
import threading
import numpy as np
import time
import datetime
from instamatic.formats import write_tiff
from camera import Camera

class VideoStream(threading.Thread):
    """docstring for VideoStream"""
    def __init__(self, cam):
        threading.Thread.__init__(self)
        self.cam = cam
        self.start()

    def callback(self):
        self.stopEvent.set()
        self.root.quit()

    def run(self):
        self.cam = Camera(kind=self.cam)

        self.frame = None
        self.thread = None
        self.stopEvent = None

        self.stash = None
        self.acquire = False

        self.frametime = 0.01
        self.exposure = self.frametime
        self.binsize = self.cam.default_binsize
 
        self.root = Tk()
        self.panel = None

        self.init_vars()
        self.buttonbox(self.root)
        self.header(self.root)
        self.makepanel(self.root)

        self.stopEvent = threading.Event()
        self.thread = threading.Thread(target=self.videoLoop, args=())
        self.thread.start()
 
        self.root.wm_title("Instamatic stream")
        self.root.wm_protocol("WM_DELETE_WINDOW", self.close)

        self.root.mainloop()

    def header(self, master):
        ewidth = 10
        lwidth = 12

        frame = Frame(master)
        self.e_fps       = Entry(frame, bd=0, width=ewidth, textvariable=self.var_fps, state=DISABLED)
        self.e_frametime = Entry(frame, bd=0, width=ewidth, textvariable=self.var_frametime, state=DISABLED)
        self.e_overhead = Entry(frame, bd=0, width=ewidth, textvariable=self.var_overhead, state=DISABLED)
        
        Label(frame, anchor=E, width=lwidth, text="fps:").grid(row=1, column=0)
        self.e_fps.grid(row=1, column=1)
        Label(frame, anchor=E, width=lwidth, text="frametime (ms):").grid(row=1, column=2)
        self.e_frametime.grid(row=1, column=3)
        Label(frame, anchor=E, width=lwidth, text="overhead (ms):").grid(row=1, column=4)
        self.e_overhead.grid(row=1, column=5)
        
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
        btn.pack(side="bottom", fill="both", expand="yes", padx=10, pady=10)

    def init_vars(self):
        self.var_fps = DoubleVar()
        self.var_frametime = DoubleVar()
        self.var_overhead = DoubleVar()

    def getImage(self, t=None, **kwargs):
        if t:
            self.exposure = t
        self.stash = None
        self.acquire = True
        
        while self.stash is None:
            pass

        self.acquire = False
        return self.stash.astype(int)

    def videoLoop(self):
        t0 = time.time()
        nframes = 1
        while not self.stopEvent.is_set():
            try:
                if self.acquire:
                    self.stash = self.frame = self.cam.getImage(t=self.exposure, fastmode=True)
                    # self.stash = self.frame = np.random.random((512, 512)) * 256
                    # time.sleep(self.exposure)
                else:
                    self.frame = self.cam.getImage(t=self.frametime, fastmode=True)
                    # self.frame = np.random.random((512, 512)) * 256
                    # time.sleep(self.frametime)
            except Exception as e:
                print time.time(), e
                time.sleep(1)
                continue

            # rotate image by 90 degrees to match DM/SoPhy
            image = Image.fromarray(np.rot90(self.frame, k=3))
            image = ImageTk.PhotoImage(image)
            
            self.panel.configure(image=image)
            # keep a reference to avoid premature garbage collection
            self.panel.image = image
            
            t1 = time.time()
            delta = t1 - t0

            if delta > 1:
                frametime = (delta)/nframes
                fps = 1.0/(frametime)
                overhead = frametime - self.frametime

                self.var_fps.set(round(fps, 2))
                self.var_frametime.set(round(frametime*1000, 2))
                self.var_overhead.set(round(overhead*1000, 2))
                t0 = t1
                nframes = 1
            else:
                nframes += 1

    def saveImage(self):
        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        write_tiff(outfile, self.frame)
        print " >> Wrote file:", outfile

    def close(self):
        self.stopEvent.set()
        self.root.quit()

if __name__ == '__main__':
    stream = VideoStream(cam="timepix")
    # stream.root.mainloop()
    from IPython import embed
    embed()