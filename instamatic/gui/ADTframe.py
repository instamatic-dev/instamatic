from Tkinter import *
from ttk import *


class ExperimentalADT(LabelFrame):
    """docstring for ExperimentalADT"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Assisted Diffraction Tomography")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time:").grid(row=4, column=0)
        self.exposure_time = Entry(frame, textvariable=self.var_exposure_time)
        self.exposure_time.grid(row=4, column=1, sticky="W", padx=10)
        
        Label(frame, text="Tilt range (deg):").grid(row=5, column=0)
        self.exposure_time = Entry(frame, textvariable=self.var_tilt_range)
        self.exposure_time.grid(row=5, column=1, sticky="W", padx=10)

        Label(frame, text="Step size (deg):").grid(row=6, column=0)
        self.exposure_time = Entry(frame, textvariable=self.var_stepsize)
        self.exposure_time.grid(row=6, column=1, sticky="W", padx=10)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        self.StartButton = Button(self, text="Start Collection", command=self.start_collection)
        self.StartButton.pack(side="left", expand=True, fill="x", padx=10, pady=10)

        self.ContinueButton = Button(self, text="Continue", command=self.continue_collection, state=DISABLED)
        self.ContinueButton.pack(side="left", expand=True, fill="x", padx=10, pady=10)

        self.FinalizeButton = Button(self, text="Finalize", command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.pack(side="left", expand=True, fill="x", padx=10, pady=10)
        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_tilt_range = DoubleVar(value=10.0)
        self.var_stepsize = DoubleVar(value=0.2)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None, stopEvent=None):
        self.startEvent = startEvent
        self.stopEvent = stopEvent

    def start_collection(self):
        self.StartButton.config(state=DISABLED)
        self.ContinueButton.config(state=NORMAL)
        self.FinalizeButton.config(state=NORMAL)
        self.startEvent.set()
        self.triggerEvent.set()

    def continue_collection(self):
        self.startEvent.set()
        self.triggerEvent.set()

    def stop_collection(self):
        self.StartButton.config(state=NORMAL)
        self.ContinueButton.config(state=DISABLED)
        self.FinalizeButton.config(state=DISABLED)
        self.triggerEvent.set()
        self.stopEvent.set()

    def get_params(self):
        return self.var_exposure_time.get(), self.var_tilt_range.get(), self.var_stepsize.get()


if __name__ == '__main__':
    root = Tk()
    ExperimentalcRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

