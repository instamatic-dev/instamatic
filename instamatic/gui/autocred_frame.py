from Tkinter import *
from ttk import *
import threading


class ExperimentalautocRED(LabelFrame):
    """docstring for ExperimentalautocRED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Automated Continuous rotation electron diffraction")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time:").grid(row=1, column=0, sticky="W")
        self.exposure_time = Entry(frame, textvariable=self.var_exposure_time)
        self.exposure_time.grid(row=1, column=1, sticky="W", padx=10)
        
        Checkbutton(frame, text="Beam unblanker", variable=self.var_unblank_beam).grid(row=1, column=2, sticky="W")
        
        Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=3, sticky="ew", pady=10)

        Checkbutton(frame, text="Enable image interval", variable=self.var_enable_image_interval, command=self.toggle_interval_buttons).grid(row=5, column=2, sticky="W")
        self.c_toggle_defocus = Checkbutton(frame, text="Toggle defocus", variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=6, column=2, sticky="W")

        Label(frame, text="Image interval:").grid(row=5, column=0, sticky="W")
        self.e_image_interval = Spinbox(frame, textvariable=self.var_image_interval, from_=1, to=9999, increment=1)
        self.e_image_interval.grid(row=5, column=1, sticky="W", padx=10)

        Label(frame, text="Diff defocus:").grid(row=6, column=0, sticky="W")
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=6, column=1, sticky="W", padx=10)
        
        Checkbutton(frame, text="Enable Auto Tracking", variable=self.var_enable_autotrack, command=self.autotrack).grid(row=7, column=2, sticky="W")

        self.lb_coll0 = Label(frame, text="")
        self.lb_coll1 = Label(frame, text="")
        self.lb_coll2 = Label(frame, text="")
        self.lb_coll0.grid(row=10, column=0, columnspan=3, sticky="EW")
        self.lb_coll1.grid(row=11, column=0, columnspan=3, sticky="EW")
        self.lb_coll2.grid(row=12, column=0, columnspan=3, sticky="EW")
        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side="top", fill="x", expand=False, padx=10, pady=10)

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
        self.var_diff_defocus = IntVar(value=1500)
        self.var_enable_image_interval = BooleanVar(value=True)
        self.var_toggle_diff_defocus = BooleanVar(value=False)
        self.var_enable_autotrack = BooleanVar(value=True)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        # TODO: make a pop up window with the STOP button?
        self.CollectionStopButton.config(state=NORMAL)
        self.CollectionButton.config(state=DISABLED)
        self.lb_coll1.config(text="Now you can start to rotate the goniometer at any time.")
        self.lb_coll2.config(text="Click STOP COLLECTION BEFORE removing your foot from the pedal!")

        self.parent.bind_all("<space>", self.stop_collection)

        params = self.get_params()
        self.q.put(("cred", params))

        self.triggerEvent.set()

    def stop_collection(self, event=None):
        self.stopEvent.set()

        self.parent.unbind_all("<space>")

        self.CollectionStopButton.config(state=DISABLED)
        self.CollectionButton.config(state=NORMAL)
        self.lb_coll1.config(text="")
        self.lb_coll2.config(text="")

    def get_params(self):
        params = { "exposure_time": self.var_exposure_time.get(),
                   "unblank_beam": self.var_unblank_beam.get(),
                   "enable_image_interval": self.var_enable_image_interval.get(),
                   "enable_autotrack": self.var_enable_autotrack.get(),
                   "image_interval": self.var_image_interval.get(),
                   "diff_defocus": self.var_diff_defocus.get(),
                   "stop_event": self.stopEvent }
        return params

    def toggle_interval_buttons(self):
        enable = self.var_enable_image_interval.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
        else:
            self.e_image_interval.config(state=DISABLED)
            self.e_diff_defocus.config(state=DISABLED)
            self.c_toggle_defocus.config(state=DISABLED)
            
    def autotrack(self):
        enable = self.var_enable_autotrack.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
        else:
            self.e_image_interval.config(state=DISABLED)
            self.e_diff_defocus.config(state=DISABLED)
            self.c_toggle_defocus.config(state=DISABLED)
    ##Focused beam, CC, Calibration for beam shift        
        

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()
        difffocus = self.var_diff_defocus.get()

        self.q.put(("toggle_difffocus", {"value": difffocus, "toggle": toggle} ))
        self.triggerEvent.set()


if __name__ == '__main__':
    root = Tk()
    ExperimentalautocRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

