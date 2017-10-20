from Tkinter import *
from ttk import *
import threading


class ExperimentalcRED(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Continuous rotation electron diffraction")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time:").grid(row=4, column=0)
        self.exposure_time = Entry(frame, textvariable=self.var_exposure_time)
        self.exposure_time.grid(row=4, column=1, sticky="W", padx=10)
        
        Checkbutton(frame, text="Beam unblanker", variable=self.var_unblank_beam).grid(row=4, column=2)

        Label(frame, text="Image interval:").grid(row=5, column=0)
        self.e_image_interval = Spinbox(frame, textvariable=self.var_image_interval, from_=1, to=9999, increment=1)
        self.e_image_interval.grid(row=5, column=1, sticky="W", padx=10)

        self.lb_coll1 = Label(frame, text="Now you can start to rotate the goniometer at any time.")
        self.lb_coll2 = Label(frame, text="Click STOP COLLECTION BEFORE removing your foot from the pedal!")
        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        frame = Frame(self)
        self.CollectionButton = Button(frame, text="Start Collection", command=self.start_collection)
        self.CollectionButton.grid(row=1, column=0, sticky="EW")

        self.CollectionStopButton = Button(frame, text="Stop Collection", command=self.stop_collection, state=DISABLED)
        self.CollectionStopButton.grid(row=1, column=1, sticky="EW")
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.pack(side="bottom", fill="x", padx=10, pady=10)

        self.stopEvent = threading.Event()

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_unblank_beam = BooleanVar(value=False)
        self.var_image_interval = IntVar(value=10)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        # TODO: make a pop up window with the STOP button?
        self.CollectionStopButton.config(state=NORMAL)
        self.CollectionButton.config(state=DISABLED)
        self.lb_coll1.grid(row=10, column=0, columnspan=2, sticky="EW")
        self.lb_coll2.grid(row=11, column=0, columnspan=2, sticky="EW")

        params = self.get_params()
        self.q.put(("cred", params))

        self.triggerEvent.set()

    def stop_collection(self):
        self.CollectionStopButton.config(state=DISABLED)
        self.CollectionButton.config(state=NORMAL)
        self.lb_coll1.grid_forget()
        self.lb_coll2.grid_forget()
        self.stopEvent.set()

    def get_params(self):
        params = { "exposure_time": self.var_exposure_time.get(),
                   "unblank_beam": self.var_unblank_beam.get(),
                   "stop_event": self.stopEvent }
        return params


if __name__ == '__main__':
    root = Tk()
    ExperimentalcRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

