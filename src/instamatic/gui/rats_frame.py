from __future__ import annotations

import threading
from enum import Enum
from queue import Queue
from tkinter import *
from tkinter.ttk import *
from typing import Any, Dict, Optional

from instamatic.utils.spinbox import Spinbox

from .base_module import BaseModule

pad0 = dict(sticky='EW', padx=0, pady=1)
pad10 = dict(sticky='EW', padx=10, pady=1)
width = dict(width=19)
angle_lim = dict(from_=-90, to=90, increment=1, width=20)
angle_delta = dict(from_=0, to=180, increment=0.1, width=20)
time = dict(from_=0, to=60, increment=0.1)


class DiffractionMode(Enum):
    stills = 'stills'
    continuous = 'continuous'


class TrackingMode(Enum):
    none = 'none'
    manual = 'manual'


class ExperimentalRatsVariables:
    def __init__(self):
        self.diffraction_mode = StringVar()
        self.diffraction_start = DoubleVar(value=-30)
        self.diffraction_stop = DoubleVar(value=30)
        self.diffraction_step = DoubleVar(value=0.5)
        self.diffraction_time = DoubleVar(value=0.5)
        self.tracking_mode = StringVar()
        self.tracking_time = DoubleVar(value=0.5)
        self.tracking_step = DoubleVar(value=5.0)


class ExperimentalRats(LabelFrame):
    """GUI panel to perform selected RATS4-style (c)RED & PED experiments."""

    def __init__(self, parent):  # noqa: parent.__init__ is called
        LabelFrame.__init__(self, parent, text='RATS-style MicroED experiment')
        self.parent = parent
        self.var = ExperimentalRatsVariables()
        self.q: Optional[Queue] = None
        self.triggerEvent: Optional[threading.Event] = None
        self.experiment_in_progress: bool = False

        # Top-aligned part of the frame with experiment parameters
        f = Frame(self)

        Label(f, text='Diffraction mode:').grid(row=3, column=0, **pad10)
        self.diffraction_mode = Combobox(f, textvariable=self.var.diffraction_mode, **width)
        self.diffraction_mode['values'] = [e.value for e in DiffractionMode]
        self.diffraction_mode['state'] = 'readonly'
        self.diffraction_mode.grid(row=3, column=1, **pad10)
        self.diffraction_mode.current(0)

        Label(f, text='Diffraction start (deg):').grid(row=4, column=0, **pad10)
        self.diffraction_start = Spinbox(
            f, textvariable=self.var.diffraction_start, **angle_lim
        )
        self.diffraction_start.grid(row=4, column=1, **pad10)

        Label(f, text='Diffraction stop (deg):').grid(row=5, column=0, **pad10)
        self.diffraction_stop = Spinbox(f, textvariable=self.var.diffraction_stop, **angle_lim)
        self.diffraction_stop.grid(row=5, column=1, **pad10)

        Label(f, text='Diffraction step (deg):').grid(row=6, column=0, **pad10)
        self.diffraction_step = Spinbox(
            f, textvariable=self.var.diffraction_step, **angle_delta
        )
        self.diffraction_step.grid(row=6, column=1, **pad10)

        Label(f, text='Diffraction exposure (s):').grid(row=7, column=0, **pad10)
        self.diffraction_time = Spinbox(f, textvariable=self.var.diffraction_time, **time)
        self.diffraction_time.grid(row=7, column=1, **pad10)

        Label(f, text='Tracking mode:').grid(row=3, column=2, **pad10)
        self.tracking_mode = Combobox(f, textvariable=self.var.tracking_mode, **width)
        self.tracking_mode['values'] = [e.value for e in TrackingMode]
        self.tracking_mode['state'] = 'readonly'
        self.tracking_mode.grid(row=3, column=3, **pad10)
        self.tracking_mode.bind('<<ComboboxSelected>>', self.update_widget_state)
        self.tracking_mode.current(0)

        Label(f, text='Tracking step (s):').grid(row=6, column=2, **pad10)
        self.tracking_step = Spinbox(f, textvariable=self.var.tracking_step, **angle_delta)
        self.tracking_step.grid(row=6, column=3, **pad10)

        Label(f, text='Tracking exposure (s):').grid(row=7, column=2, **pad10)
        self.tracking_time = Spinbox(f, textvariable=self.var.tracking_time, **time)
        self.tracking_time.grid(row=7, column=3, **pad10)

        Separator(f, orient=HORIZONTAL).grid(row=8, columnspan=4, sticky='ew', padx=10, pady=10)

        f.pack(side='top', fill='x', pady=10)

        # Store / restore settings buttons
        g = Frame(f)
        self.store_diff = Button(g, width=1, text='Store diff config', command=self.store_diff)
        self.store_diff.grid(row=9, column=0, **pad0)
        self.restore_diff = Button(
            g, width=1, text='Restore diff config', command=self.restore_diff
        )
        self.restore_diff.grid(row=9, column=1, **pad0)
        self.store_image = Button(
            g, width=1, text='Store image config', command=self.store_image
        )
        self.store_image.grid(row=9, column=2, **pad0)
        self.restore_image = Button(
            g, width=1, text='Restore image config', command=self.restore_image
        )
        self.restore_image.grid(row=9, column=3, **pad0)
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)
        g.columnconfigure(2, weight=1)
        g.columnconfigure(3, weight=1)
        g.grid(row=9, column=0, columnspan=4, sticky='ew', padx=10)

        # Center-aligned sticky message area
        f = Frame(self)

        self.message = StringVar(value='Further information might appear here.')
        self.message_area = Label(f, textvariable=self.message, anchor='nw')
        self.message_area.pack(fill='both', expand=True)
        f.pack(side='top', fill='both', expand=True, padx=10)

        # Bottom-aligned part of the frame with experiment control buttons
        f = Frame(self)

        self.start_button = Button(f, text='Start', width=1, command=self.start_collection)
        self.start_button.grid(row=1, column=0, **pad0)

        self.extend_button = Button(f, text='Extend', width=1, command=self.extend_collection)
        self.extend_button.grid(row=1, column=1, **pad0)

        self.abort_button = Button(f, text='Abort', width=1, command=self.abort_collection)
        self.abort_button.grid(row=1, column=2, **pad0)

        self.finalize_button = Button(
            f, text='Finalize', width=1, command=self.finalize_collection
        )
        self.finalize_button.grid(row=1, column=3, **pad0)

        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(2, weight=1)
        f.columnconfigure(3, weight=1)
        f.pack(side='bottom', fill='x', padx=10, pady=10)

        self.update_widget_state()

    def update_widget_state(self, *_, **__) -> None:
        eip = self.experiment_in_progress
        self.start_button.config(state='disabled' if eip else 'enabled')
        self.extend_button.config(state='enabled' if eip else 'disabled')
        self.abort_button.config(state='enabled' if eip else 'disabled')
        self.finalize_button.config(state='enabled' if eip else 'disabled')
        self.diffraction_step.config(state='disabled' if eip else 'enabled')
        self.diffraction_time.config(state='disabled' if eip else 'enabled')

        no_track = TrackingMode(self.var.tracking_mode.get()) is TrackingMode.none
        self.tracking_step.config(state='disabled' if eip or no_track else 'enabled')
        self.tracking_time.config(state='disabled' if eip or no_track else 'enabled')

    def store_diff(self) -> None:
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='store_diff')))
        self.triggerEvent.set()

    def restore_diff(self) -> None:
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='restore_diff')))
        self.triggerEvent.set()

    def store_image(self) -> None:
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='store_image')))
        self.triggerEvent.set()

    def restore_image(self) -> None:
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='restore_image')))
        self.triggerEvent.set()

    def start_collection(self) -> None:
        self.experiment_in_progress = True
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='start')))
        self.triggerEvent.set()

    def extend_collection(self):
        self.experiment_in_progress = True
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='extend')))
        self.triggerEvent.set()

    def finalize_collection(self):
        self.experiment_in_progress = False
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='finalize')))
        self.triggerEvent.set()

    def abort_collection(self):
        self.experiment_in_progress = False
        self.update_widget_state()
        self.q.put(('rats', self.get_params(task='abort')))
        self.triggerEvent.set()

    def set_trigger(self, trigger: threading.Event, q: Queue) -> None:
        """A boilerplate method, connects to a GUI thread and command queue."""
        self.triggerEvent: threading.Event = trigger
        self.q: Queue = q

    def get_params(self, task: str) -> Dict[str, Any]:
        params = {
            v: getattr(self.var, v).get()
            for v in dir(self.var)
            if isinstance(getattr(self.var, v), Variable)
        }
        params['frame'] = self
        params['task'] = task
        return params


def rats_interface_command(controller, **params: Any) -> None:
    controller.log.info('Start RATS experiment')
    from instamatic.experiments import rats

    task: str = params['task']

    if task == 'start':
        frame: ExperimentalRats = params['frame']
        flat_field = controller.module_io.get_flatfield()
        exp_dir = controller.module_io.get_new_experiment_directory()
        videostream_frame = controller.app.get_module('stream')
        exp_dir.mkdir(exist_ok=True, parents=True)

        controller.rats_exp = rats.RatsExperiment(
            ctrl=controller.ctrl,
            path=exp_dir,
            log=controller.log,
            flatfield=flat_field,
            rats_frame=frame,
            videostream_frame=videostream_frame,
        )
        controller.rats_exp.start_collection(**params)

    elif task == 'extend':
        controller.rats_exp.start_collection(**params)

    elif task == 'finalize':
        controller.rats_exp.finalize()
        del controller.rats_exp

    elif task == 'abort':
        del controller.rats_exp

    elif task == 'store_diff':
        controller.ctrl.store('rats_diff')

    elif task == 'restore_diff':
        controller.ctrl.restore('rats_diff')

    elif task == 'store_image':
        controller.ctrl.store('rats_image')

    elif task == 'restore_image':
        controller.ctrl.restore('rats_image')

    else:
        raise ValueError(f'Invalid task: {task}')

    # TODO: frame.update_buttons() allow further actions finnally when everything ends


module = BaseModule(
    name='rats', display_name='RATS', tk_frame=ExperimentalRats, location='bottom'
)
commands = {'rats': rats_interface_command}


if __name__ == '__main__':
    root = Tk()
    ExperimentalRats(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
