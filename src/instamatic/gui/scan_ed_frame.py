from __future__ import annotations

from enum import Enum
from pathlib import Path
from threading import Event as ThreadingEvent
from tkinter import *
from tkinter.ttk import *
from typing import Any, Literal, Optional, Union

from instamatic import controller
from instamatic.experiments.scan_ed.progress import ProgressTable, ThreadSafeProgressTableProxy
from instamatic.utils.spinbox import Spinbox

from .base_module import BaseModule, ModuleFrameMixin

SCAN_ED_MODE = Literal['start', 'continue', 'reprocess']

pad10 = {'sticky': 'EW', 'padx': 10, 'pady': 1}
scan_step = {'from_': 100, 'to': 100_000, 'increment': 100}
scan_exposure = {'from_': 0.01, 'to': 10, 'increment': 0.01}
target_hits = {'from_': 0, 'to': 1_000_000, 'increment': 100}
target_time = {'from_': 0, 'to': 43_200, 'increment': 60}
target_xy = {'from_': 0, 'to': 1_000_000, 'increment': 1000}
angle_delta = {'from_': 0, 'to': 30, 'increment': 1}
radius_range = {'from_': 0, 'to': 1000, 'increment': 1}


class WidgetState(Enum):
    IDLE = 0
    BUSY = 1
    STOPPING = 2


class ThreadSafeTkCallback:
    """Run callback(*args, **kwargs) on the Tk thread."""

    def __init__(self, parent, callback):
        self._parent = parent
        self._callback = callback

    def __call__(self, *args, **kwargs):
        self._parent.after(0, lambda: self._callback(*args, **kwargs))


class ExperimentalScanEDVariables:
    """A collection of tkinter Variable instances passed to the experiment."""

    def __init__(self) -> None:
        self.grid_geometry = StringVar()
        self.scan_geometry = StringVar()
        self.scan_x_step = IntVar(value=500)
        self.scan_y_step = IntVar(value=500)
        self.scan_exposure = DoubleVar(value=0.1)
        self.grid_finder = StringVar()

        self.target_hits = IntVar(value=1000)
        self.target_x = IntVar(value=500_000)
        self.target_y = IntVar(value=500_000)
        self.target_time = IntVar(value=480)
        self.max_alpha = DoubleVar(value=0)
        self.save_all = BooleanVar(value=False)

        self.target_hits_b = BooleanVar(value=False)
        self.target_x_b = BooleanVar(value=False)
        self.target_y_b = BooleanVar(value=False)
        self.target_time_b = BooleanVar(value=False)

        self.min_peak_count = IntVar(value=10)
        self.min_radius = DoubleVar(value=40)

        self.stop_event = ThreadingEvent()

    def as_dict(self) -> dict[str, Union[float, int, str]]:
        """Return self as dict, replace values with None if key_b is False."""
        d = {n: v.get() for n, v in vars(self).items() if isinstance(v, Variable)}
        d['stop_event'] = self.stop_event
        for key in d.copy().keys():
            if (key_b := key + '_b') in d:
                if d.pop(key_b) is False:
                    d[key] = None
        return d


class ExperimentalScanED(LabelFrame, ModuleFrameMixin):
    """GUI panel to control Scanning (precession-assisted) ED experiments."""

    def __init__(self, parent):
        text = 'Automatically scan entire grid until any finish condition is met'
        super().__init__(parent, text=text)
        self.pack_propagate(False)  # keep the width fixed
        self.parent = parent
        self.var = ExperimentalScanEDVariables()
        self.busy: bool = False
        self.ctrl = controller.get_instance()

        # Top-aligned part of the frame with experiment parameters
        f = Frame(self)
        for column in range(6):
            f.grid_columnconfigure(column, weight=1, uniform='buttons')
        f.grid_rowconfigure(10, weight=1)

        Label(f, text='Grid geometry:').grid(row=3, column=0, **pad10)
        m = ['hexagonal', 'rectangular', 'square']
        self.grid_geometry = OptionMenu(f, self.var.grid_geometry, m[1], *m)
        self.grid_geometry.grid(row=3, column=1, **pad10)

        Label(f, text='Scan geometry:').grid(row=4, column=0, **pad10)
        m = ['X-raster', 'X-serpentine', 'Y-raster', 'Y-serpentine']
        self.scan_geometry = OptionMenu(f, self.var.scan_geometry, m[1], *m)
        self.scan_geometry.grid(row=4, column=1, **pad10)

        Label(f, text='Scan X step (nm):').grid(row=5, column=0, **pad10)
        var = self.var.scan_x_step
        self.scan_x_step = Spinbox(f, textvariable=var, **scan_step)
        self.scan_x_step.grid(row=5, column=1, **pad10)

        Label(f, text='Scan Y step (nm):').grid(row=6, column=0, **pad10)
        var = self.var.scan_y_step
        self.scan_y_step = Spinbox(f, textvariable=var, **scan_step)
        self.scan_y_step.grid(row=6, column=1, **pad10)

        Label(f, text='Scan exposure (s):').grid(row=7, column=0, **pad10)
        var = self.var.scan_exposure
        self.scan_exposure = Spinbox(f, textvariable=var, **scan_exposure)
        self.scan_exposure.grid(row=7, column=1, **pad10)

        Label(f, text='Max alpha tilt (deg):').grid(row=8, column=0, **pad10)
        self.max_alpha = Spinbox(f, textvariable=self.var.max_alpha, **angle_delta)
        self.max_alpha.grid(row=8, column=1, **pad10)

        # Finish conditions area with tick marks

        Label(f, text='Find new grid windows:').grid(row=3, column=2, **pad10)
        m = ['All manually', 'First manually', 'All automatically']
        self.grid_finder = OptionMenu(f, self.var.grid_finder, m[1], *m)
        self.grid_finder.grid(row=3, column=3, **pad10)

        text = 'Finish experiment once:'
        Label(f, text=text).grid(row=4, column=2, columnspan=2, **pad10)

        text = 'Hits exceed:'
        self.target_hits_b = Checkbutton(f, variable=self.var.target_hits_b, text=text)
        self.target_hits_b.grid(row=5, column=2, **pad10)
        self.target_hits = Spinbox(f, textvariable=self.var.target_hits, **target_hits)
        self.target_hits.grid(row=5, column=3, **pad10)

        text = '±X exceeds (nm):'
        self.target_x_b = Checkbutton(f, variable=self.var.target_x_b, text=text)
        self.target_x_b.grid(row=6, column=2, **pad10)
        self.target_x = Spinbox(f, textvariable=self.var.target_x, **target_xy)
        self.target_x.grid(row=6, column=3, **pad10)

        text = '±Y exceeds (nm):'
        self.target_y_b = Checkbutton(f, variable=self.var.target_y_b, text=text)
        self.target_y_b.grid(row=7, column=2, **pad10)
        self.target_y = Spinbox(f, textvariable=self.var.target_y, **target_xy)
        self.target_y.grid(row=7, column=3, **pad10)

        text = 'Time exceeds (h):'
        self.target_time_b = Checkbutton(f, variable=self.var.target_time_b, text=text)
        self.target_time_b.grid(row=8, column=2, **pad10)
        self.target_time = Spinbox(f, textvariable=self.var.target_time, **target_time)
        self.target_time.grid(row=8, column=3, **pad10)

        Label(f, text='Min peak count:').grid(row=3, column=4, **pad10)
        var = self.var.min_peak_count
        self.min_peak_count = Spinbox(f, textvariable=var, **angle_delta)
        self.min_peak_count.grid(row=3, column=5, **pad10)

        Label(f, text='Min radius (px):').grid(row=4, column=4, **pad10)
        var = self.var.min_radius
        self.min_resolution = Spinbox(f, textvariable=var, **radius_range)
        self.min_resolution.grid(row=4, column=5, **pad10)

        text = 'Save all images in ./all:'
        self.save_all_b = Checkbutton(f, variable=self.var.save_all, text=text)
        self.save_all_b.grid(row=8, column=4, columnspan=2, **pad10)

        # Bottom area for progress and experiment flow control buttons

        self.progress = ProgressTable(f)
        self.progress.grid(row=10, columnspan=6, sticky=NSEW, padx=10, pady=0)
        f.pack(side='top', fill=BOTH, expand=True, pady=10)

        g = Frame(self)
        for column in range(4):
            g.grid_columnconfigure(column, weight=1, uniform='buttons')

        self.start_button = Button(g, text='Start collection', command=self.run_start)
        self.start_button.grid(row=20, column=0, sticky=EW)
        self.load_button = Button(g, text='Load and continue', command=self.run_continue)
        self.load_button.grid(row=20, column=1, sticky=EW)
        self.load_button = Button(g, text='Load and reprocess', command=self.run_reprocess)
        self.load_button.grid(row=20, column=2, sticky=EW)
        self.stop_button = Button(g, text='Stop collection', command=self.run_stop)
        self.stop_button.grid(row=20, column=3, sticky=EW)
        self.update_widget()
        g.pack(side='bottom', fill=X, padx=10, pady=(0, 10))  # pad from the bottom only

    def _run(self, mode: SCAN_ED_MODE) -> None:
        """Schedule the scan_ed job on the experiment thread in given mode."""
        self.progress.clear()
        callback = ThreadSafeTkCallback(self, self.update_widget)
        progress = ThreadSafeProgressTableProxy(self, self.progress)
        kwargs = {'callback': callback, 'mode': mode, 'progress': progress}
        self.q.put(('scan_ed', {**kwargs, **self.var.as_dict()}))
        self.update_widget(state=WidgetState.BUSY)

    def run_start(self) -> None:
        self._run(mode='start')

    def run_continue(self) -> None:
        self._run(mode='continue')

    def run_reprocess(self) -> None:
        self._run(mode='reprocess')

    def run_stop(self) -> None:
        self.var.stop_event.set()
        self.update_widget(state=WidgetState.STOPPING)

    def update_widget(self, state: WidgetState = WidgetState.IDLE) -> None:
        """Update the buttons to reflect the current state of the widget."""
        self.start_button.config(state=NORMAL if state is WidgetState.IDLE else DISABLED)
        self.load_button.config(state=NORMAL if state is WidgetState.IDLE else DISABLED)
        self.stop_button.config(state=NORMAL if state is WidgetState.BUSY else DISABLED)


def sced_interface_command(controller, **params: Any) -> None:
    from instamatic.experiments.scan_ed.experiment import Experiment

    callback = params.pop('callback', lambda: None)
    mode: SCAN_ED_MODE = params.get('mode', 'start')  # noqa type
    progress: Optional[ProgressTable] = params.get('progress', None)
    flat_field = controller.module_io.get_flatfield()
    if params.get('stop_event', None) is not None:
        params['stop_event'].clear()

    if mode == 'start':
        exp_dir = controller.module_io.get_new_experiment_directory()
        exp_dir.mkdir(exist_ok=True, parents=True)
    else:
        exp_dir = controller.module_io.get_experiment_directory()
        journal_path = Path(exp_dir) / 'journal.jsonl'
        try:
            if not journal_path.is_file():
                raise FileNotFoundError(f'No journal file found at {journal_path}')
        except FileNotFoundError:
            callback()

    # get the videostreaming frame only if needed for manual window determination
    if params.get('grid_finder') == 'All automatically':
        vsf = None
    else:
        vsf = controller.app.get_module('stream')

    controller.fast_adt = Experiment(
        ctrl=controller.ctrl,
        path=exp_dir,
        log=controller.log,
        flatfield=flat_field,
        progress=progress,
        mode=mode,
        videostream_frame=vsf,
    )
    try:
        controller.fast_adt.start_collection(**params)
    except RuntimeError:
        pass  # RuntimeError is raised if experiment is terminated early
    finally:
        callback()
        del controller.fast_adt


module = BaseModule(
    name='scan_ed', display_name='ScanED', tk_frame=ExperimentalScanED, location='bottom'
)
commands = {'scan_ed': sced_interface_command}


if __name__ == '__main__':
    root = Tk()
    ExperimentalScanED(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
