from tkinter import *
from tkinter.ttk import *
from instamatic.utils.spinbox import Spinbox


class ExperimentalTVIPS(LabelFrame):
    """docstring for ExperimentalRED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Continuous rotation electron diffraction (TVIPS")
        self.parent = parent

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time (s):").grid(row=4, column=0, sticky="W")
        self.e_target_angle = Spinbox(frame, textvariable=self.var_target_angle, width=sbwidth, from_=-80.0, to=80.0, increment=5.0)
        self.e_target_angle.grid(row=4, column=1, sticky="W", padx=10)
        
        # Label(frame, text="Tilt range (deg):").grid(row=5, column=0, sticky="W")
        # self.e_tilt_range = Spinbox(frame, textvariable=self.var_tilt_range, width=sbwidth, from_=0.1, to=9999, increment=0.5)
        # self.e_tilt_range.grid(row=5, column=1, sticky="W", padx=10)

        # Label(frame, text="Step size (deg):").grid(row=6, column=0, sticky="W")
        # self.e_stepsize = Spinbox(frame, textvariable=self.var_stepsize, width=sbwidth, from_=-10.0, to=10.0, increment=0.2)
        # self.e_stepsize.grid(row=6, column=1, sticky="W", padx=10)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text="Output formats:").grid(row=5, columnspan=2, sticky="EW")
        # Checkbutton(frame, text="PETS (.tiff)", variable=self.var_save_tiff, state=DISABLED).grid(row=5, column=2, sticky="EW")
        # Checkbutton(frame, text="REDp (.mrc)", variable=self.var_save_red, state=DISABLED).grid(row=5, column=3, sticky="EW")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        self.GetReadyButton = Button(frame, text="Get Ready", command=self.prime_collection)
        self.GetReadyButton.grid(row=1, column=0, sticky="EW")

        self.AcquireButton = Button(frame, text="Acquire", command=self.start_collection, state=DISABLED)
        self.AcquireButton.grid(row=1, column=1, sticky="EW")

        self.FinalizeButton = Button(frame, text="Finalize", command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.grid(row=1, column=2, sticky="EW")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_target_angle = DoubleVar(value=40.0)
        # self.var_tilt_range = DoubleVar(value=5.0)
        # self.var_stepsize = DoubleVar(value=1.0)

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)


    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def prime_collection(self):
        self.GetReadyButton.config(state=DISABLED)
        self.AcquireButton.config(state=NORMAL)
        self.FinalizeButton.config(state=NORMAL)
        self.e_target_angle.config(state=DISABLED)
        # self.e_stepsize.config(state=DISABLED)
        params = self.get_params(task="get_ready")
        self.q.put(("cred_tvips", params))
        self.triggerEvent.set()

    def start_collection(self):
        params = self.get_params(task="acquire")
        self.q.put(("cred_tvips", params))
        self.triggerEvent.set()

    def stop_collection(self):
        self.GetReadyButton.config(state=NORMAL)
        self.AcquireButton.config(state=DISABLED)
        self.FinalizeButton.config(state=DISABLED)
        self.e_target_angle.config(state=NORMAL)
        # self.e_stepsize.config(state=NORMAL)
        params = self.get_params(task="stop")
        self.q.put(("cred_tvips", params))
        self.triggerEvent.set()

    def get_params(self, task=None):
        params = { "target_angle": self.var_target_angle.get(), 
                   "task": task }
        return params


def acquire_data_CRED_TVIPS(controller, **kwargs):
    controller.log.info("Start cRED (TVIPS) experiment")
    from instamatic.experiments import cRED_tvips

    task = kwargs["task"]

    target_angle = kwargs["target_angle"]

    if task == "get_ready":
        expdir = controller.module_io.get_new_experiment_directory()
        expdir.mkdir(exist_ok=True, parents=True)
    
        controller.cred_tvips_exp = cRED_tvips.Experiment(ctrl=controller.ctrl, path=expdir, log=controller.log)
        controller.cred_tvips_exp.get_ready()
    elif task == "acquire":
        controller.cred_tvips_exp.start_collection(target_angle=target_angle)
    elif task == "stop":
        del controller.red_exp


from .base_module import BaseModule
module = BaseModule("tvips", "TVIPS", True, ExperimentalTVIPS, commands={
    "cred_tvips": acquire_data_CRED_TVIPS
    })


if __name__ == '__main__':
    root = Tk()
    ExperimentalTVIPS(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

