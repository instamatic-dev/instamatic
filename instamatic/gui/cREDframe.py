from Tkinter import *
from ttk import *


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

        self.lb_coll1 = Label(frame, text="Now you can start to rotate the goniometer at any time.")
        self.lb_coll2 = Label(frame, text="Click STOP COLLECTION BEFORE removing your foot from the pedal!")
        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side="top", fill="both", expand=True, padx=10)

        frame = Frame(self)
        self.CollectionButton = Button(self, text="Start Collection", command=self.start_collection)
        self.CollectionButton.pack(side="left", expand=True, fill="x", padx=10, pady=10)

        self.CollectionStopButton = Button(self, text="Stop Collection", command=self.stop_collection, state=DISABLED)
        self.CollectionStopButton.pack(side="right", expand=True, fill="x", padx=10, pady=10)
        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_unblank_beam = BooleanVar(value=False)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None, stopEvent=None):
        self.startEvent = startEvent
        self.stopEvent = stopEvent

    def start_collection(self):
        # TODO: make a pop up window with the STOP button?
        self.CollectionStopButton.config(state=NORMAL)
        self.CollectionButton.config(state=DISABLED)
        self.lb_coll1.grid(row=10, column=0, columnspan=2, sticky="EW")
        self.lb_coll2.grid(row=11, column=0, columnspan=2, sticky="EW")
        self.startEvent.set()
        self.triggerEvent.set()

    def stop_collection(self):
        self.CollectionStopButton.config(state=DISABLED)
        self.CollectionButton.config(state=NORMAL)
        self.lb_coll1.grid_forget()
        self.lb_coll2.grid_forget()
        self.stopEvent.set()

    def get_expt(self):
        return self.var_exposure_time.get()

    def get_unblank_beam(self):
        return self.var_unblank_beam.get()


if __name__ == '__main__':
    root = Tk()
    ExperimentalcRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

