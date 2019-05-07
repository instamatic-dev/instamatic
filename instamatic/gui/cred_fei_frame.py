from tkinter import *
from tkinter.ttk import *
from instamatic.utils.spinbox import Spinbox

class ExperimentalcRED_FEI(LabelFrame):
    """docstring for ExperimentalcRED on FEI"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="cRED_FEI")
        self.parent = parent

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time (s):").grid(row=4, column=0, sticky="W")
        self.e_exposure_time = Spinbox(frame, textvariable=self.var_exposure_time, width=sbwidth, from_=0.1, to=9999, increment=0.1)
        self.e_exposure_time.grid(row=4, column=1, sticky="W", padx=10)
        
        Label(frame, text="Target angle (deg):").grid(row=5, column=0, sticky="W")
        self.e_endangle = Spinbox(frame, textvariable=self.var_endangle, width=sbwidth, from_=0.1, to=9999, increment=0.5)
        self.e_endangle.grid(row=5, column=1, sticky="W", padx=10)

        Label(frame, text="Rotation speed (0 - 1):").grid(row=6, column=0, sticky="W")
        self.e_rotspeed = Spinbox(frame, textvariable=self.var_rotspeed, width=sbwidth, from_=-10.0, to=10.0, increment=0.2)
        self.e_rotspeed.grid(row=6, column=1, sticky="W", padx=10)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text="Output formats:").grid(row=5, columnspan=2, sticky="EW")
        Checkbutton(frame, text="PETS (.tiff)", variable=self.var_save_tiff, state=DISABLED).grid(row=5, column=2, sticky="EW")
        Checkbutton(frame, text="REDp (.mrc)", variable=self.var_save_red, state=DISABLED).grid(row=5, column=3, sticky="EW")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        self.StartButton = Button(frame, text="Start Rotation", command=self.start_collection)
        self.StartButton.grid(row=1, column=0, sticky="EW")

        self.FinalizeButton = Button(frame, text="Stop Rotation", command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.grid(row=1, column=2, sticky="EW")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_endangle = DoubleVar(value=60.0)
        self.var_rotspeed = DoubleVar(value=1.0)

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)


    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        self.StartButton.config(state=DISABLED)
        self.FinalizeButton.config(state=NORMAL)
        self.e_exposure_time.config(state=DISABLED)
        self.e_rotspeed.config(state=DISABLED)
                    
        self.q.put(("credfei", {"task": "stageposition.set_with_speed",
                                "a": self.var_endangle.get(),
                                "speed": self.var_rotspeed.get()}))
        self.triggerEvent.set()

    def stop_collection(self):
        self.StartButton.config(state=NORMAL)
        self.FinalizeButton.config(state=DISABLED)
        self.e_exposure_time.config(state=NORMAL)
        self.e_rotspeed.config(state=NORMAL)
        params = self.get_params(task="None")
        self.q.put(("credfei", params))
        self.triggerEvent.set()

    def get_params(self, task=None):
        params = { "exposure_time": self.var_exposure_time.get(), 
                   "endangle": self.var_endangle.get(), 
                   "rotspeed": self.var_rotspeed.get(),
                   "task": task }
        return params


def acquire_data_cREDfei(controller, **kwargs):
    from operator import attrgetter

    task = kwargs.pop("task")
    
    if task == "None":
        pass
    else:
        f = attrgetter(task)(controller.ctrl)
        f(**kwargs)


from .base_module import BaseModule
module = BaseModule("credfei", "cRED_FEI", True, ExperimentalcRED_FEI, commands={
    "credfei": acquire_data_cREDfei
    })


if __name__ == '__main__':
    root = Tk()
    ExperimentalRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

