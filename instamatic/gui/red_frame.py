from tkinter import *
from tkinter.ttk import *

from .base_module import BaseModule
from instamatic.utils.spinbox import Spinbox


class ExperimentalRED(LabelFrame):
    """GUI panel to perform a simple RED experiment using discrete rotation
    steps."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Rotation electron diffraction')
        self.parent = parent

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)
        Label(frame, text='Exposure time (s):').grid(row=4, column=0, sticky='W')
        self.e_exposure_time = Spinbox(frame, textvariable=self.var_exposure_time, width=sbwidth, from_=0.1, to=9999, increment=0.1)
        self.e_exposure_time.grid(row=4, column=1, sticky='W', padx=10)

        Label(frame, text='Tilt range (deg):').grid(row=5, column=0, sticky='W')
        self.e_tilt_range = Spinbox(frame, textvariable=self.var_tilt_range, width=sbwidth, from_=0.1, to=9999, increment=0.5)
        self.e_tilt_range.grid(row=5, column=1, sticky='W', padx=10)

        Label(frame, text='Step size (deg):').grid(row=6, column=0, sticky='W')
        self.e_stepsize = Spinbox(frame, textvariable=self.var_stepsize, width=sbwidth, from_=-10.0, to=10.0, increment=0.2)
        self.e_stepsize.grid(row=6, column=1, sticky='W', padx=10)

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text='Output formats:').grid(row=5, columnspan=2, sticky='EW')
        Checkbutton(frame, text='PETS (.tiff)', variable=self.var_save_tiff, state=DISABLED).grid(row=5, column=2, sticky='EW')
        Checkbutton(frame, text='REDp (.mrc)', variable=self.var_save_red, state=DISABLED).grid(row=5, column=3, sticky='EW')
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)
        self.StartButton = Button(frame, text='Start Collection', command=self.start_collection)
        self.StartButton.grid(row=1, column=0, sticky='EW')

        self.ContinueButton = Button(frame, text='Continue', command=self.continue_collection, state=DISABLED)
        self.ContinueButton.grid(row=1, column=1, sticky='EW')

        self.FinalizeButton = Button(frame, text='Finalize', command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.grid(row=1, column=2, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        frame.pack(side='bottom', fill='x', padx=10, pady=10)

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_tilt_range = DoubleVar(value=5.0)
        self.var_stepsize = DoubleVar(value=1.0)

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        self.StartButton.config(state=DISABLED)
        self.ContinueButton.config(state=NORMAL)
        self.FinalizeButton.config(state=NORMAL)
        self.e_exposure_time.config(state=DISABLED)
        self.e_stepsize.config(state=DISABLED)
        params = self.get_params(task='start')
        self.q.put(('red', params))
        self.triggerEvent.set()

    def continue_collection(self):
        params = self.get_params(task='continue')
        self.q.put(('red', params))
        self.triggerEvent.set()

    def stop_collection(self):
        self.StartButton.config(state=NORMAL)
        self.ContinueButton.config(state=DISABLED)
        self.FinalizeButton.config(state=DISABLED)
        self.e_exposure_time.config(state=NORMAL)
        self.e_stepsize.config(state=NORMAL)
        params = self.get_params(task='stop')
        self.q.put(('red', params))
        self.triggerEvent.set()

    def get_params(self, task=None):
        params = {'exposure_time': self.var_exposure_time.get(),
                  'tilt_range': self.var_tilt_range.get(),
                  'stepsize': self.var_stepsize.get(),
                  'task': task}
        return params


def acquire_data_RED(controller, **kwargs):
    controller.log.info('Start RED experiment')
    from instamatic.experiments import RED

    task = kwargs['task']

    exposure_time = kwargs['exposure_time']
    tilt_range = kwargs['tilt_range']
    stepsize = kwargs['stepsize']

    if task == 'start':
        flatfield = controller.module_io.get_flatfield()

        expdir = controller.module_io.get_new_experiment_directory()
        expdir.mkdir(exist_ok=True, parents=True)

        controller.red_exp = RED.Experiment(ctrl=controller.ctrl, path=expdir, log=controller.log,
                                            flatfield=flatfield)
        controller.red_exp.start_collection(exposure_time=exposure_time, tilt_range=tilt_range, stepsize=stepsize)
    elif task == 'continue':
        controller.red_exp.start_collection(exposure_time=exposure_time, tilt_range=tilt_range, stepsize=stepsize)
    elif task == 'stop':
        controller.red_exp.finalize()
        del controller.red_exp


module = BaseModule(name='red', display_name='RED', tk_frame=ExperimentalRED, location='bottom')
commands = {'red': acquire_data_RED}


if __name__ == '__main__':
    root = Tk()
    ExperimentalRED(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
