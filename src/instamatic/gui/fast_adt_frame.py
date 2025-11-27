from __future__ import annotations

from functools import wraps
from tkinter import *
from tkinter.ttk import *
from typing import Any, Callable, Optional

from instamatic import controller
from instamatic.utils.spinbox import Spinbox

from .base_module import BaseModule, ModuleFrameMixin

pad0 = {'sticky': 'EW', 'padx': 0, 'pady': 1}
pad10 = {'sticky': 'EW', 'padx': 10, 'pady': 1}
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

    def __init__(self, on_change: Optional[Callable[[], None]] = None) -> None:
        self.diffraction_mode = StringVar()
        self.diffraction_start = DoubleVar(value=-30)
        self.diffraction_stop = DoubleVar(value=30)
        self.diffraction_step = DoubleVar(value=0.5)
        self.diffraction_time = DoubleVar(value=0.5)
        self.tracking_algo = StringVar()
        self.tracking_time = DoubleVar(value=0.5)
        self.tracking_step = DoubleVar(value=5.0)

        if on_change:
            self._add_callback(on_change)

    def _add_callback(self, callback: Callable[[], None]) -> None:
        """Add a safe trace callback to all `Variable` instances in self."""

        @wraps(callback)
        def safe_callback(*_):
            try:
                callback()
            except TclError as e:  # Ignore invalid/incomplete GUI edits
                if 'expected floating-point number' not in str(e):
                    raise
            except AttributeError as e:  # Ignore incomplete initialization
                if 'object has no attribute' not in str(e):
                    raise

        for name, var in vars(self).items():
            if isinstance(var, Variable):
                var.trace_add('write', safe_callback)

    def as_dict(self):
        return {n: v.get() for n, v in vars(self).items() if isinstance(v, Variable)}


class ExperimentalFastADT(LabelFrame, ModuleFrameMixin):
    """GUI panel to perform selected FastADT-style (c)RED & PED experiments."""

    def __init__(self, parent):
        super().__init__(parent, text='Experiment with a priori tracking options')
        self.parent = parent
        self.var = ExperimentalFastADTVariables(on_change=self.update_widget)
        self.busy: bool = False
        self.ctrl = controller.get_instance()

        # Top-aligned part of the frame with experiment parameters
        f = Frame(self)

        Label(f, text='Diffraction mode:').grid(row=3, column=0, **pad10)
        m = ['stills', 'continuous']
        self.diffraction_mode = OptionMenu(f, self.var.diffraction_mode, m[0], *m)
        self.diffraction_mode.grid(row=3, column=1, **pad10)

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

        Label(f, text='Tracking algorithm:').grid(row=3, column=2, **pad10)
        var = self.var.tracking_algo
        m = ['none', 'manual']
        self.tracking_algo = OptionMenu(f, var, m[0], *m)
        self.tracking_algo.grid(row=3, column=3, **pad10)

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

        # Center-aligned sticky message areas 1, 2, and the bottom start button
        f = Frame(self)

        self.message1 = StringVar(value='Further information will appear here.')
        self.message1_area = Label(f, textvariable=self.message1, anchor=NW)
        self.message1_area.pack(fill='x')

        self.message2 = StringVar(value='')
        self.message2_area = Label(f, textvariable=self.message2, anchor=NW)
        self.message2_area.pack(fill='both', expand=True)
        f.pack(side='top', fill='both', expand=True, padx=10)

        self.start_button = Button(self, text='Start', width=1, command=self.start_collection)
        self.start_button.pack(side='bottom', fill='x', padx=10, pady=10)

        self.update_widget()

    def estimate_times(self) -> tuple[float, float]:
        """Estimate time needed for tracking + each diffraction in seconds."""
        a_span = abs(self.var.diffraction_start.get() - self.var.diffraction_stop.get())
        try:
            track_step = self.var.tracking_step.get()
        except TclError:
            track_step = 0.001
        try:
            diff_step = self.var.diffraction_step.get()
        except TclError:
            diff_step = 0.001
        track_time = 0
        if self.var.tracking_algo.get() != 'none':
            track_time = self.var.tracking_time.get() * a_span / track_step
        diff_time = self.var.diffraction_time.get() * a_span / diff_step
        return track_time, diff_time

    def toggle_beam_blank(self) -> None:
        (self.ctrl.beam.unblank if self.ctrl.beam.is_blanked else self.ctrl.beam.blank)()

    def update_widget(self, *_, busy: Optional[bool] = None, **__) -> None:
        self.busy = busy if busy is not None else self.busy
        no_tracking = self.var.tracking_algo.get() == 'none'
        widget_state = 'disabled' if self.busy else 'enabled'
        tracking_state = 'disabled' if self.busy or no_tracking else 'enabled'

        self.start_button.config(state=widget_state)
        self.diffraction_mode.config(state=widget_state)
        self.diffraction_start.config(state=widget_state)
        self.diffraction_stop.config(state=widget_state)
        self.diffraction_step.config(state=widget_state)
        self.diffraction_time.config(state=widget_state)
        self.tracking_algo.config(state=widget_state)
        self.tracking_step.config(state=tracking_state)
        self.tracking_time.config(state=tracking_state)

        try:
            tracking_time, diffraction_time = self.estimate_times()
        except ZeroDivisionError:
            return
        tt = '{:.0f}:{:02.0f}'.format(*divmod(tracking_time, 60))
        dt = '{:.0f}:{:02.0f}'.format(*divmod(diffraction_time, 60))
        if tracking_time:  # don't display tracking time or per-attempts if zero
            msg = f'Estimated time required: {tt} + {dt} / tracking.'
        else:
            msg = f'Estimated time required: {dt}.'
        self.message2.set(msg)

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
        fast_adt_frame.update_widget(busy=True)
        controller.fast_adt.start_collection(**params)
    except RuntimeError:
        pass  # RuntimeError is raised if experiment is terminated early
    finally:
        del controller.fast_adt
        fast_adt_frame.update_widget(busy=False)


module = BaseModule(
    name='fast_adt', display_name='FastADT', tk_frame=ExperimentalFastADT, location='bottom'
)
commands = {'fast_adt': fast_adt_interface_command}


if __name__ == '__main__':
    root = Tk()
    ExperimentalFastADT(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
