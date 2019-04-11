from tkinter import *
from tkinter.ttk import *
import threading
from instamatic.utils.spinbox import Spinbox

ENABLE_FOOTFREE_OPTION = False


class ExperimentalcRED(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Continuous rotation electron diffraction")
        self.parent = parent

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)
        Label(frame, text="Exposure time (s):").grid(row=1, column=0, sticky="W")
        exposure_time = Spinbox(frame, textvariable=self.var_exposure_time, width=sbwidth, from_=0.0, to=100.0, increment=0.01)
        exposure_time.grid(row=1, column=1, sticky="W", padx=10)
        
        Checkbutton(frame, text="Beam unblanker", variable=self.var_unblank_beam).grid(row=1, column=2, sticky="W")
        
        Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=3, sticky="ew", pady=10)

        Checkbutton(frame, text="Enable image interval", variable=self.var_enable_image_interval, command=self.toggle_interval_buttons).grid(row=5, column=2, sticky="W")
        self.c_toggle_defocus = Checkbutton(frame, text="Toggle defocus", variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus, state=DISABLED)
        self.c_toggle_defocus.grid(row=6, column=2, sticky="W")

        Label(frame, text="Image interval:").grid(row=5, column=0, sticky="W")
        self.e_image_interval = Spinbox(frame, textvariable=self.var_image_interval, width=sbwidth, from_=1, to=9999, increment=1, state=DISABLED)
        self.e_image_interval.grid(row=5, column=1, sticky="W", padx=10)

        Label(frame, text="Diff defocus:").grid(row=6, column=0, sticky="W")
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=sbwidth, from_=-10000, to=10000, increment=100, state=DISABLED)
        self.e_diff_defocus.grid(row=6, column=1, sticky="W", padx=10)
        
        Label(frame, text="Image exposure (s):").grid(row=7, column=0, sticky="W")
        self.e_image_exposure = Spinbox(frame, textvariable=self.var_exposure_time_image, width=sbwidth, from_=0.0, to=100.0, increment=0.01, state=DISABLED)
        self.e_image_exposure.grid(row=7, column=1, sticky="W", padx=10)

        self.RelaxButton = Button(frame, text="Relax beam", command=self.relax_beam, state=DISABLED)
        self.RelaxButton.grid(row=7, column=2, sticky="EW")

        if ENABLE_FOOTFREE_OPTION:
            Separator(frame, orient=HORIZONTAL).grid(row=8, columnspan=3, sticky="ew", pady=10)
            
            Label(frame, text="Rotate to:").grid(row=9, column=0, sticky="W")
            self.e_max_rotation = Spinbox(frame, textvariable=self.var_footfree_rotate_to, width=sbwidth, from_=0.0, to=70.0, increment=1.0, state=DISABLED)
            self.e_max_rotation.grid(row=9, column=1, sticky="W", padx=10)
        
            Checkbutton(frame, text="Footfree mode", variable=self.var_toggle_footfree, command=self.toggle_footfree).grid(row=9, column=2, sticky="W")

        self.lb_coll0 = Label(frame, text="")
        self.lb_coll1 = Label(frame, text="")
        self.lb_coll2 = Label(frame, text="")
        self.lb_coll0.grid(row=10, column=0, columnspan=3, sticky="EW")
        self.lb_coll1.grid(row=11, column=0, columnspan=3, sticky="EW")
        self.lb_coll2.grid(row=12, column=0, columnspan=3, sticky="EW")
        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side="top", fill="x", expand=False, padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text="Select output formats:").grid(row=5, columnspan=2, sticky="EW")
        Checkbutton(frame, text=".tiff", variable=self.var_save_tiff).grid(row=5, column=2, sticky="EW")
        Checkbutton(frame, text="XDS (.smv)", variable=self.var_save_xds).grid(row=5, column=3, sticky="EW")
        Checkbutton(frame, text="DIALS (.smv)", variable=self.var_save_dials).grid(row=6, column=2, sticky="EW")
        Checkbutton(frame, text="REDp (.mrc)", variable=self.var_save_red).grid(row=6, column=3, sticky="EW")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        frame.pack(side="top", fill="x", padx=10, pady=10)

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
        self.var_enable_image_interval = BooleanVar(value=False)
        self.var_toggle_diff_defocus = BooleanVar(value=False)
        self.var_exposure_time_image = DoubleVar(value=0.01)

        self.var_footfree_rotate_to = DoubleVar(value=65.0)
        self.var_toggle_footfree = BooleanVar(value=False)
        self.mode = "regular"

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_xds = BooleanVar(value=True)
        self.var_save_dials = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        # TODO: make a pop up window with the STOP button?
        if self.var_toggle_diff_defocus.get():
            self.var_toggle_diff_defocus.set(False)
            self.toggle_diff_defocus()

        self.CollectionStopButton.config(state=NORMAL)
        self.CollectionButton.config(state=DISABLED)
        if self.mode == "footfree":
            self.lb_coll1.config(text="Data collection has started.")
            self.lb_coll2.config(text="Click STOP COLLECTION to end the experiment.")
        else:
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
                   "exposure_time_image": self.var_exposure_time_image.get(),
                   "unblank_beam": self.var_unblank_beam.get(),
                   "enable_image_interval": self.var_enable_image_interval.get(),
                   "image_interval": self.var_image_interval.get(),
                   "diff_defocus": self.var_diff_defocus.get(),
                   "mode": self.mode,
                   "footfree_rotate_to": self.var_footfree_rotate_to.get(),
                   "write_tiff": self.var_save_tiff.get(),
                   "write_xds": self.var_save_xds.get(),
                   "write_dials": self.var_save_dials.get(),
                   "write_red": self.var_save_red.get(),
                   "stop_event": self.stopEvent }
        return params

    def toggle_interval_buttons(self):
        enable = self.var_enable_image_interval.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_image_exposure.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
            self.RelaxButton.config(state=NORMAL)
        else:
            self.e_image_interval.config(state=DISABLED)
            self.e_image_exposure.config(state=DISABLED)
            self.e_diff_defocus.config(state=DISABLED)
            self.c_toggle_defocus.config(state=DISABLED)     
            self.RelaxButton.config(state=DISABLED)     
    
    def relax_beam(self):
        difffocus = self.var_diff_defocus.get()

        self.q.put(("relax_beam", {"value": difffocus} ))
        self.triggerEvent.set()

    def toggle_footfree(self):
        enable = self.var_toggle_footfree.get()
        if enable:
            self.mode = "footfree"
            self.e_max_rotation.config(state=NORMAL)
        else:
            self.mode == "regular"
            self.e_max_rotation.config(state=DISABLED)

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()
        difffocus = self.var_diff_defocus.get()

        self.q.put(("toggle_difffocus", {"value": difffocus, "toggle": toggle} ))
        self.triggerEvent.set()


def relax_beam(controller, **kwargs):
    import time
    n_cycles = 4
    print(f"Relaxing beam ({n_cycles} cycles)")

    controller.ctrl.mode_diffraction()

    offset = kwargs["value"]

    for i in range(n_cycles):
        controller.ctrl.difffocus.defocus(offset=offset)
        time.sleep(0.25)
        controller.ctrl.difffocus.refocus()
        time.sleep(0.25)

    print("Done.")


def toggle_difffocus(controller, **kwargs):
    toggle = kwargs["toggle"]

    if toggle:
        offset = kwargs["value"]
        controller.ctrl.difffocus.defocus(offset=offset)
    else:
        controller.ctrl.difffocus.refocus()


def acquire_data_cRED(controller, **kwargs):
    controller.log.info("Start cRED experiment")
    from instamatic.experiments import cRED
    
    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)
    
    cexp = cRED.Experiment(ctrl=controller.ctrl, path=expdir, flatfield=controller.module_io.get_flatfield(), log=controller.log, **kwargs)

    success = cexp.start_collection()

    if not success:
        return
    
    controller.log.info("Finish cRED experiment")

    if controller.use_indexing_server:
        controller.q.put(("autoindex", {"task": "run", "path": cexp.smv_path} ))
        controller.triggerEvent.set()


from .base_module import BaseModule
module = BaseModule("cred", "cRED", True, ExperimentalcRED, commands={
    "cred": acquire_data_cRED,
    "toggle_difffocus": toggle_difffocus,
    "relax_beam": relax_beam
    })


if __name__ == '__main__':
    root = Tk()
    ExperimentalcRED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

