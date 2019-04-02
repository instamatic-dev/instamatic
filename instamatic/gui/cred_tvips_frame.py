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
        Label(frame, text="Target angle (degrees):").grid(row=4, column=0, sticky="W")
        self.e_target_angle = Spinbox(frame, textvariable=self.var_target_angle, width=sbwidth, from_=-80.0, to=80.0, increment=5.0)
        self.e_target_angle.grid(row=4, column=1, sticky="W", padx=10)
        
        InvertAngleButton = Button(frame, text="Invert", command=self.invert_angle)
        InvertAngleButton.grid(row=4, column=2, sticky="EW")

        # defocus button
        Label(frame, text="Diff defocus:").grid(row=6, column=0, sticky="W")
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=sbwidth, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=6, column=1, sticky="W", padx=10)

        self.c_toggle_defocus = Checkbutton(frame, text="Toggle defocus", variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=6, column=3, sticky="W")

        self.b_reset_defocus = Button(frame, text="Reset", command=self.reset_diff_defocus, state=DISABLED)
        self.b_reset_defocus.grid(row=6, column=2, sticky="EW")

        self.c_toggle_diffraction = Checkbutton(frame, text="Toggle DIFF", variable=self.var_toggle_diff_mode, command=self.toggle_diff_mode)
        self.c_toggle_diffraction.grid(row=7, column=3, sticky="W")

        self.c_toggle_screen = Checkbutton(frame, text="Toggle screen", variable=self.var_toggle_screen, command=self.toggle_screen)
        self.c_toggle_screen.grid(row=8, column=3, sticky="W")

        self.b_toggle_liveview = Button(frame, text="Toggle live", command=self.toggle_live_view, state=DISABLED)
        self.b_toggle_liveview.grid(row=7, column=2, sticky="EW")

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

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)

        self.var_diff_defocus = IntVar(value=1500)
        self.var_toggle_diff_defocus = BooleanVar(value=False)

        self.var_toggle_diff_mode = BooleanVar(value=False)
        self.var_toggle_screen = BooleanVar(value=False)
        self.var_toggle_live_view = BooleanVar(value=False)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def invert_angle(self):
        angle = self.var_target_angle.get()
        self.var_target_angle.set(-angle)

    def prime_collection(self):
        self.GetReadyButton.config(state=DISABLED)
        self.AcquireButton.config(state=NORMAL)
        self.FinalizeButton.config(state=NORMAL)
        # self.e_target_angle.config(state=DISABLED)
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
        self.b_toggle_liveview.config(state=NORMAL)
        params = self.get_params(task="stop")
        self.q.put(("cred_tvips", params))
        self.triggerEvent.set()

    def get_params(self, task=None):
        params = { "target_angle": self.var_target_angle.get(), 
                   "task": task }
        return params

    def toggle_diff_mode(self):
        toggle = self.var_toggle_diff_mode.get()

        if toggle:
            self.q.put(("ctrl", {"task": "mode_diffraction"} ))
        else:
            self.q.put(("ctrl", {"task": "mode_mag1"} ))

        self.triggerEvent.set()

    def toggle_screen(self):
        toggle = self.var_toggle_screen.get()

        if toggle:
            self.q.put(("ctrl", {"task": "screen_up"} ))
        else:
            self.q.put(("ctrl", {"task": "screen_down"} ))

        self.triggerEvent.set()

    def toggle_live_view(self):
        toggle = True

        self.q.put(("emmenu", {"task": "view", "toggle": toggle} ))

        self.triggerEvent.set()

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()
        difffocus = self.var_diff_defocus.get()

        self.b_reset_defocus.config(state=NORMAL)

        self.q.put(("toggle_difffocus", {"value": difffocus, "toggle": toggle} ))
        self.triggerEvent.set()

    def reset_diff_defocus(self):
        self.var_toggle_diff_defocus.set(False)
        self.q.put(("toggle_difffocus", {"value": 0, "toggle": False} ))
        self.triggerEvent.set()


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
        pass


def ctrl_emmenu(controller, **kwargs):
    emmenu = controller.emmenu

    task = kwargs.get("task")

    if task == "view":
        toggle = kwargs.get("toggle")
        emmenu.toggle_live_view()


from .base_module import BaseModule
module = BaseModule("tvips", "TVIPS", True, ExperimentalTVIPS, commands={
    "cred_tvips": acquire_data_CRED_TVIPS,
    "emmenu": ctrl_emmenu,
    })


if __name__ == '__main__':
    root = Tk()
    ExperimentalTVIPS(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

