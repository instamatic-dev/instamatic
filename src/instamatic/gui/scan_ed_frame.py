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

pad10 = {'sticky': 'EW', 'padx': 5, 'pady': 1}
scan_step = {'from_': 100, 'to': 100_000, 'increment': 100}
scan_exposure = {'from_': 0.01, 'to': 10, 'increment': 0.01}
target_hits = {'from_': 0, 'to': 1_000_000, 'increment': 100}
target_xy = {'from_': 0, 'to': 1_000_000, 'increment': 1000}
small_ints = {'from_': 0, 'to': 30, 'increment': 1}
res_range = {'from_': 0, 'to': 1000, 'increment': 1}
percentile = {'from_': 0, 'to': 100, 'increment': 0.1}


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
        self.regionalization = StringVar()
        self.scan_x_step = IntVar(value=1000)
        self.scan_y_step = IntVar(value=1000)
        self.scan_exposure = DoubleVar(value=0.1)
        self.max_tilt = DoubleVar(value=0)

        self.grid_finding = StringVar()
        self.target_hits = IntVar(value=1000)
        self.target_x = IntVar(value=500_000)
        self.target_y = IntVar(value=500_000)
        self.target_time = IntVar(value=8)
        self.save_all = BooleanVar(value=False)

        self.target_hits_b = BooleanVar(value=False)
        self.target_x_b = BooleanVar(value=False)
        self.target_y_b = BooleanVar(value=False)
        self.target_time_b = BooleanVar(value=False)

        self.min_radius = DoubleVar(value=40)
        self.threshold_perc = DoubleVar(value=99)
        self.threshold_mult = DoubleVar(value=2)
        self.min_peak_count = IntVar(value=10)
        self.min_peak_sep = IntVar(value=5)

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
        text = 'Scan entire grid window by window until any finish condition is met'
        super().__init__(parent, text=text)
        self.pack_propagate(False)  # keep the width fixed
        self.parent = parent
        self.var = ExperimentalScanEDVariables()
        self.busy: bool = False
        self.ctrl = controller.get_instance()

        # Top-aligned part of the frame with experiment parameters
        f = Frame(self)
        for column in range(5):
            f.grid_columnconfigure(column, weight=3, uniform='buttons')
        f.grid_columnconfigure(5, weight=2, uniform='buttons')
        f.grid_rowconfigure(10, weight=1)

        Label(f, text='Grid geometry:').grid(row=2, column=0, **pad10)
        m = ['hexagonal', 'rectangular', 'square']
        self.grid_geometry = OptionMenu(f, self.var.grid_geometry, m[2], *m)
        self.grid_geometry.grid(row=2, column=1, **pad10)

        Label(f, text='Scan geometry:').grid(row=3, column=0, **pad10)
        m = ['X-raster', 'X-serpentine', 'Y-raster', 'Y-serpentine']
        self.scan_geometry = OptionMenu(f, self.var.scan_geometry, m[1], *m)
        self.scan_geometry.grid(row=3, column=1, **pad10)

        Label(f, text='Windows in scan:').grid(row=4, column=0, **pad10)
        m = ['1 x 1', '3 x 1', '1 x 3', '3 x 3']
        self.regionalization = OptionMenu(f, self.var.regionalization, m[0], *m)
        self.regionalization.grid(row=4, column=1, **pad10)

        Label(f, text='X step (nm):').grid(row=5, column=0, **pad10)
        var = self.var.scan_x_step
        self.scan_x_step = Spinbox(f, textvariable=var, **scan_step)
        self.scan_x_step.grid(row=5, column=1, **pad10)

        Label(f, text='Y step (nm):').grid(row=6, column=0, **pad10)
        var = self.var.scan_y_step
        self.scan_y_step = Spinbox(f, textvariable=var, **scan_step)
        self.scan_y_step.grid(row=6, column=1, **pad10)

        Label(f, text='Exposure (s):').grid(row=7, column=0, **pad10)
        var = self.var.scan_exposure
        self.scan_exposure = Spinbox(f, textvariable=var, **scan_exposure)
        self.scan_exposure.grid(row=7, column=1, **pad10)

        Label(f, text='Max tilt (deg):').grid(row=8, column=0, **pad10)
        self.max_tilt = Spinbox(f, textvariable=self.var.max_tilt, **small_ints)
        self.max_tilt.grid(row=8, column=1, **pad10)

        # Finish conditions area with tick marks

        Label(f, text='Find windows:').grid(row=2, column=2, **pad10)
        m = ['All manually', 'First manually', 'All automatically']
        self.grid_finder = OptionMenu(f, self.var.grid_finding, m[1], *m)
        self.grid_finder.grid(row=2, column=3, **pad10)

        text = 'Finish experiment once exceeds:'
        Label(f, text=text).grid(row=3, column=2, columnspan=2, **pad10)

        text = 'Hits:'
        self.target_hits_b = Checkbutton(f, variable=self.var.target_hits_b, text=text)
        self.target_hits_b.grid(row=4, column=2, **pad10)
        self.target_hits = Spinbox(f, textvariable=self.var.target_hits, **target_hits)
        self.target_hits.grid(row=4, column=3, **pad10)

        text = 'Stage X (nm):'
        self.target_x_b = Checkbutton(f, variable=self.var.target_x_b, text=text)
        self.target_x_b.grid(row=5, column=2, **pad10)
        self.target_x = Spinbox(f, textvariable=self.var.target_x, **target_xy)
        self.target_x.grid(row=5, column=3, **pad10)

        text = 'Stage Y (nm):'
        self.target_y_b = Checkbutton(f, variable=self.var.target_y_b, text=text)
        self.target_y_b.grid(row=6, column=2, **pad10)
        self.target_y = Spinbox(f, textvariable=self.var.target_y, **target_xy)
        self.target_y.grid(row=6, column=3, **pad10)

        text = 'Time (h):'
        self.target_time_b = Checkbutton(f, variable=self.var.target_time_b, text=text)
        self.target_time_b.grid(row=7, column=2, **pad10)
        self.target_time = Spinbox(f, textvariable=self.var.target_time, **res_range)
        self.target_time.grid(row=7, column=3, **pad10)

        text = 'Save all data for reprocessing'
        self.save_all = Checkbutton(f, variable=self.var.save_all, text=text)
        self.save_all.grid(row=8, column=2, columnspan=2, **pad10)

        text = 'Peakfinding parameters:'
        Label(f, text=text).grid(row=3, column=4, columnspan=2, **pad10)

        Label(f, text='Min radius (px):').grid(row=4, column=4, **pad10)
        var = self.var.min_radius
        self.min_radius = Spinbox(f, textvariable=var, **res_range)
        self.min_radius.grid(row=4, column=5, **pad10)

        Label(f, text='Threshold perc:').grid(row=5, column=4, **pad10)
        var = self.var.threshold_perc
        self.threshold_perc = Spinbox(f, textvariable=var, **percentile)
        self.threshold_perc.grid(row=5, column=5, **pad10)

        Label(f, text='Threshold mult:').grid(row=6, column=4, **pad10)
        var = self.var.threshold_mult
        self.threshold_mult = Spinbox(f, textvariable=var, **percentile)
        self.threshold_mult.grid(row=6, column=5, **pad10)

        Label(f, text='Min peak count:').grid(row=7, column=4, **pad10)
        var = self.var.min_peak_count
        self.min_peak_count = Spinbox(f, textvariable=var, **small_ints)
        self.min_peak_count.grid(row=7, column=5, **pad10)

        Label(f, text='Min peak sep:').grid(row=8, column=4, **pad10)
        var = self.var.min_peak_sep
        self.min_peak_sep = Spinbox(f, textvariable=var, **small_ints)
        self.min_peak_sep.grid(row=8, column=5, **pad10)

        # Bottom area for progress and experiment flow control buttons

        self.progress = ProgressTable(f)
        self.progress.grid(row=10, columnspan=6, sticky=NSEW, padx=10, pady=0)
        f.pack(side='top', fill=BOTH, expand=True, padx=5, pady=10)

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
    mode: SCAN_ED_MODE = params.pop('mode', 'start')  # noqa type
    progress: Optional[ProgressTable] = params.pop('progress', None)
    flat_field = controller.module_io.get_flatfield()
    stop_event: Optional[ThreadingEvent] = params.pop('stop_event', None)
    if stop_event is not None:
        stop_event.clear()

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
    if params.get('grid_finding') == 'All automatically':
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
        stop_event=stop_event,
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
