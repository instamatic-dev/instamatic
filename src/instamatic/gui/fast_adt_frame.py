from __future__ import annotations

import threading
from queue import Queue
from tkinter import *
from tkinter.ttk import *
from typing import Any, Optional

from instamatic import controller
from instamatic.utils.spinbox import Spinbox

from .base_module import BaseModule, HasQMixin

pad0 = {'sticky': 'EW', 'padx': 0, 'pady': 1}
pad10 = {'sticky': 'EW', 'padx': 10, 'pady': 1}
width = {'width': 19}
angle_lim = {'from_': -90, 'to': 90, 'increment': 1, 'width': 20}
angle_delta = {'from_': 0, 'to': 180, 'increment': 0.1, 'width': 20}
duration = {'from_': 0, 'to': 60, 'increment': 0.1}


class FastADTConfigProxy:
    keys = (
        'FunctionMode',
        'GunShift',
        'GunTilt',
        'BeamShift',
        'BeamTilt',
        'ImageShift1',
        'ImageShift2',
        'DiffShift',
        'Magnification',
        'DiffFocus',
        'Brightness',
        'SpotSize',
    )

    def __init__(self, name='') -> None:
        self.ctrl = controller.get_instance()
        self.name = name

    def store(self) -> None:
        self.ctrl.store(f'FastADT_{self.name}', keys=self.keys, save_to_file=True)

    def restore(self) -> None:
        self.ctrl.restore(f'FastADT_{self.name}')


class ExperimentalFastADTVariables:
    """A collection of tkinter Variable instances passed to the experiment."""

    def __init__(self):
        self.diffraction_mode = StringVar()
        self.diffraction_start = DoubleVar(value=-30)
        self.diffraction_stop = DoubleVar(value=30)
        self.diffraction_step = DoubleVar(value=0.5)
        self.diffraction_time = DoubleVar(value=0.5)
        self.tracking_mode = StringVar()
        self.tracking_time = DoubleVar(value=0.5)
        self.tracking_step = DoubleVar(value=5.0)

    def as_dict(self):
        return {
            v: getattr(self, v).get()
            for v in dir(self)
            if isinstance(getattr(self, v), Variable)
        }


class ExperimentalFastADT(LabelFrame, HasQMixin):
    """GUI panel to perform selected FastADT-style (c)RED & PED experiments."""

    def __init__(self, parent):
        super().__init__(parent, text='Experiment with a priori tracking options')
        self.parent = parent
        self.var = ExperimentalFastADTVariables()
        self.q: Optional[Queue] = None
        self.busy: bool = False
        self.ctrl = controller.get_instance()

        # Top-aligned part of the frame with experiment parameters
        f = Frame(self)

        Label(f, text='Diffraction mode:').grid(row=3, column=0, **pad10)
        self.diffraction_mode = Combobox(f, textvariable=self.var.diffraction_mode, **width)
        self.diffraction_mode['values'] = ['stills', 'continuous']
        self.diffraction_mode['state'] = 'readonly'
        self.diffraction_mode.grid(row=3, column=1, **pad10)
        self.diffraction_mode.current(0)

        Label(f, text='Diffraction start (deg):').grid(row=4, column=0, **pad10)
        var = self.var.diffraction_start
        self.diffraction_start = Spinbox(f, textvariable=var, **angle_lim)
        self.diffraction_start.grid(row=4, column=1, **pad10)

        Label(f, text='Diffraction stop (deg):').grid(row=5, column=0, **pad10)
        var = self.var.diffraction_stop
        self.diffraction_stop = Spinbox(f, textvariable=var, **angle_lim)
        self.diffraction_stop.grid(row=5, column=1, **pad10)

        Label(f, text='Diffraction step (deg):').grid(row=6, column=0, **pad10)
        var = self.var.diffraction_step
        self.diffraction_step = Spinbox(f, textvariable=var, **angle_delta)
        self.diffraction_step.grid(row=6, column=1, **pad10)

        Label(f, text='Diffraction exposure (s):').grid(row=7, column=0, **pad10)
        var = self.var.diffraction_time
        self.diffraction_time = Spinbox(f, textvariable=var, **duration)
        self.diffraction_time.grid(row=7, column=1, **pad10)

        Label(f, text='Tracking mode:').grid(row=3, column=2, **pad10)
        var = self.var.tracking_mode
        self.tracking_mode = Combobox(f, textvariable=var, **width)
        self.tracking_mode['values'] = ['none', 'manual']
        self.tracking_mode['state'] = 'readonly'
        self.tracking_mode.grid(row=3, column=3, **pad10)
        self.tracking_mode.bind('<<ComboboxSelected>>', self.update_widget_state)
        self.tracking_mode.current(0)

        Label(f, text='Tracking step (deg):').grid(row=6, column=2, **pad10)
        var = self.var.tracking_step
        self.tracking_step = Spinbox(f, textvariable=var, **angle_delta)
        self.tracking_step.grid(row=6, column=3, **pad10)

        Label(f, text='Tracking exposure (s):').grid(row=7, column=2, **pad10)
        var = self.var.tracking_time
        self.tracking_time = Spinbox(f, textvariable=var, **duration)
        self.tracking_time.grid(row=7, column=3, **pad10)

        Separator(f, orient=HORIZONTAL).grid(row=8, columnspan=4, sticky=EW, padx=10, pady=10)

        f.pack(side='top', fill='x', pady=10)

        # Store / restore settings buttons
        g = Frame(f)
        b = Label(g, width=1, text='Config settings:', anchor=NW)
        b.grid(row=9, column=0, **pad0)

        image_config = FastADTConfigProxy('image')
        track_config = FastADTConfigProxy('track')
        diff_config = FastADTConfigProxy('diff')

        text = 'Beam blank/unblank'
        beam_blank = Button(g, width=1, text=text, command=self.toggle_beam_blank)
        beam_blank.grid(row=10, column=0, **pad0)

        text = 'Image store'
        self.image_store = Button(g, width=1, text=text, command=image_config.store)
        self.image_store.grid(row=9, column=1, **pad0)

        text = 'Image restore'
        self.image_restore = Button(g, width=1, text=text, command=image_config.restore)
        self.image_restore.grid(row=10, column=1, **pad0)

        text = 'Tracking store'
        self.track_store = Button(g, width=1, text=text, command=track_config.store)
        self.track_store.grid(row=9, column=2, **pad0)

        text = 'Tracking restore'
        self.track_restore = Button(g, width=1, text=text, command=track_config.restore)
        self.track_restore.grid(row=10, column=2, **pad0)

        text = 'Diffraction store'
        self.diff_store = Button(g, width=1, text=text, command=diff_config.store)
        self.diff_store.grid(row=9, column=3, **pad0)

        text = 'Diffraction restore'
        self.diff_restore = Button(g, width=1, text=text, command=diff_config.restore)
        self.diff_restore.grid(row=10, column=3, **pad0)

        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)
        g.columnconfigure(2, weight=1)
        g.columnconfigure(3, weight=1)
        g.grid(row=9, column=0, columnspan=4, sticky=EW, padx=10)

        Separator(f, orient=HORIZONTAL).grid(row=11, columnspan=4, sticky=EW, padx=10, pady=10)

        # Center-aligned sticky message area and bottom start button
        f = Frame(self)

        self.message = StringVar(value='Further information will appear here.')
        self.message_area = Label(f, textvariable=self.message, anchor=NW)
        self.message_area.pack(fill='both', expand=True)
        f.pack(side='top', fill='both', expand=True, padx=10)

        self.start_button = Button(self, text='Start', width=1, command=self.start_collection)
        self.start_button.pack(side='bottom', fill='x', padx=10, pady=10)

        self.update_widget_state()

    def toggle_beam_blank(self) -> None:
        (self.ctrl.beam.unblank if self.ctrl.beam.is_blanked else self.ctrl.beam.blank)()

    def update_widget_state(self, *_, busy: Optional[bool] = None, **__) -> None:
        self.busy = busy if busy is not None else self.busy
        no_tracking = self.var.tracking_mode.get() == 'none'
        widget_state = 'disabled' if self.busy else 'enabled'
        tracking_state = 'disabled' if self.busy or no_tracking else 'enabled'

        self.start_button.config(state=widget_state)
        self.diffraction_mode.config(state=widget_state)
        self.diffraction_start.config(state=widget_state)
        self.diffraction_stop.config(state=widget_state)
        self.diffraction_step.config(state=widget_state)
        self.diffraction_time.config(state=widget_state)
        self.tracking_mode.config(state=widget_state)

        self.tracking_step.config(state=tracking_state)
        self.tracking_time.config(state=tracking_state)

    def start_collection(self) -> None:
        self.q.put(('fast_adt', {'frame': self, **self.var.as_dict()}))


def fast_adt_interface_command(controller, **params: Any) -> None:
    from instamatic.experiments import fast_adt as fast_adt_module

    fast_adt_frame: ExperimentalFastADT = params['frame']
    flat_field = controller.module_io.get_flatfield()
    exp_dir = controller.module_io.get_new_experiment_directory()
    videostream_frame = controller.app.get_module('stream')
    exp_dir.mkdir(exist_ok=True, parents=True)

    controller.fast_adt = fast_adt_module.Experiment(
        ctrl=controller.ctrl,
        path=exp_dir,
        log=controller.log,
        flatfield=flat_field,
        experiment_frame=fast_adt_frame,
        videostream_frame=videostream_frame,
    )
    try:
        fast_adt_frame.update_widget_state(busy=True)
        controller.fast_adt.start_collection(**params)
        controller.fast_adt.finalize()
    except RuntimeError:
        pass  # RuntimeError is raised if experiment is terminated early
    finally:
        del controller.fast_adt
        fast_adt_frame.update_widget_state(busy=False)


module = BaseModule(
    name='fast_adt', display_name='FastADT', tk_frame=ExperimentalFastADT, location='bottom'
)
commands = {'fast_adt': fast_adt_interface_command}


if __name__ == '__main__':
    root = Tk()
    ExperimentalFastADT(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
