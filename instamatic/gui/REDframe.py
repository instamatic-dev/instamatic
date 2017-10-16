from Tkinter import *
from ttk import *


class ExperimentalRED(LabelFrame):
    """docstring for ExperimentalRED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Rotation electron diffraction")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time:").grid(row=4, column=0)
        self.e_exposure_time = Entry(frame, textvariable=self.var_exposure_time)
        self.e_exposure_time.grid(row=4, column=1, sticky="W", padx=10)
        
        Label(frame, text="Tilt range (deg):").grid(row=5, column=0)
        self.e_tilt_range = Entry(frame, textvariable=self.var_tilt_range)
        self.e_tilt_range.grid(row=5, column=1, sticky="W", padx=10)

        Label(frame, text="Step size (deg):").grid(row=6, column=0)
        self.e_stepsize = Entry(frame, textvariable=self.var_stepsize)
        self.e_stepsize.grid(row=6, column=1, sticky="W", padx=10)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        self.StartButton = Button(frame, text="Start Collection", command=self.start_collection)
        self.StartButton.grid(row=1, column=0, sticky="EW")

        self.ContinueButton = Button(frame, text="Continue", command=self.continue_collection, state=DISABLED)
        self.ContinueButton.grid(row=1, column=1, sticky="EW")

        self.FinalizeButton = Button(frame, text="Finalize", command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.grid(row=1, column=2, sticky="EW")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

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
        self.e_exposure_time.config(state=DISABLED)
        self.e_stepsize.config(state=DISABLED)
        self.startEvent.set()
        self.triggerEvent.set()

    def continue_collection(self):
        self.startEvent.set()
        self.triggerEvent.set()

    def stop_collection(self):
        self.StartButton.config(state=NORMAL)
        self.ContinueButton.config(state=DISABLED)
        self.FinalizeButton.config(state=DISABLED)
        self.e_exposure_time.config(state=NORMAL)
        self.e_stepsize.config(state=NORMAL)
        self.triggerEvent.set()
        self.stopEvent.set()

    def get_params(self):
        return self.var_exposure_time.get(), self.var_tilt_range.get(), self.var_stepsize.get()


if __name__ == '__main__':
    root = Tk()
    ExperimentalRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

