from __future__ import annotations

import queue
import threading
from tkinter import *
from tkinter.ttk import *

import numpy as np

from instamatic import config
from instamatic.calibrate import CalibBeamShift
from instamatic.calibrate.filenames import CALIB_BEAMSHIFT
from instamatic.exceptions import TEMCommunicationError
from instamatic.gui.click_dispatcher import ClickEvent, MouseButton
from instamatic.utils.spinbox import Spinbox

from .base_module import BaseModule, ModuleFrameMixin


class ExperimentalCtrl(LabelFrame, ModuleFrameMixin):
    """This panel holds some frequently used functions to control the electron
    microscope."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Stage Control')
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        stage_reset_btn = Button(frame, text='Reset stage', command=self.reset_stage)
        stage_reset_btn.grid(row=0, column=1, sticky='W')

        b_stage_stop = Button(frame, text='Stop stage', command=self.stage_stop)
        b_stage_stop.grid(row=0, column=2, sticky='W')

        cb_nowait = Checkbutton(frame, text='Wait for stage', variable=self.var_stage_wait)
        cb_nowait.grid(row=0, column=3)

        b_find_eucentric_height = Button(
            frame, text='Find eucentric height', command=self.find_eucentric_height
        )
        b_find_eucentric_height.grid(row=0, column=0, sticky='EW')

        Label(frame, text='Mode:').grid(row=8, column=0, sticky='W')
        modes = list(config.microscope.ranges.keys())
        self.o_mode = OptionMenu(frame, self.var_mode, modes[0], *modes, command=self.set_mode)
        self.o_mode.grid(row=8, column=1, sticky='EW')

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text='Angle (-)', width=20).grid(row=1, column=0, sticky='W')
        Label(frame, text='Angle (0)', width=20).grid(row=2, column=0, sticky='W')
        Label(frame, text='Angle (+)', width=20).grid(row=3, column=0, sticky='W')
        Label(frame, text='Alpha wobbler (±)', width=20).grid(row=4, column=0, sticky='W')
        Label(frame, text='Stage (XYZ)', width=20).grid(row=6, column=0, sticky='W')

        angle = {'width': 10, 'from_': -90, 'to': 90, 'increment': 5}
        angle_i1 = {**angle, 'increment': 1}
        stage = {'width': 10, 'from_': -1e6, 'to': 1e6, 'increment': 100}

        e_negative_angle = Spinbox(frame, textvariable=self.var_negative_angle, **angle)
        e_negative_angle.grid(row=1, column=1, sticky='EW')
        e_neutral_angle = Spinbox(frame, textvariable=self.var_neutral_angle, **angle)
        e_neutral_angle.grid(row=2, column=1, sticky='EW')
        e_positive_angle = Spinbox(frame, textvariable=self.var_positive_angle, **angle)
        e_positive_angle.grid(row=3, column=1, sticky='EW')
        e_alpha_wobbler = Spinbox(frame, textvariable=self.var_alpha_wobbler, **angle_i1)
        e_alpha_wobbler.grid(row=4, column=1, sticky='EW')

        b_wobble = Checkbutton(
            frame,
            text='Toggle wobble',
            variable=self.var_alpha_wobbler_on,
            command=self.toggle_alpha_wobbler,
        )
        b_wobble.grid(row=4, column=2, sticky='W', columnspan=2)

        text = 'Move stage with LMB'
        self.lmb_stage = Checkbutton(frame, text=text, variable=self.var_lmb_stage)
        self.lmb_stage.grid(row=1, column=3, columnspan=3, sticky='W')
        self.var_lmb_stage.trace_add('write', self.toggle_lmb_stage)

        text = 'Move beam with RMB'
        self.rmb_beam = Checkbutton(frame, text=text, variable=self.var_rmb_beam)
        self.rmb_beam.grid(row=2, column=3, columnspan=3, sticky='W')
        self.var_rmb_beam.trace_add('write', self.toggle_rmb_beam)

        e_stage_x = Spinbox(frame, textvariable=self.var_stage_x, **stage)
        e_stage_x.grid(row=6, column=1, sticky='EW')
        e_stage_y = Spinbox(frame, textvariable=self.var_stage_y, **stage)
        e_stage_y.grid(row=6, column=2, sticky='EW')
        e_stage_z = Spinbox(frame, textvariable=self.var_stage_z, **stage)
        e_stage_z.grid(row=6, column=3, sticky='EW')

        Label(frame, text='Rotation speed', width=20).grid(row=5, column=0, sticky='W')
        e_goniotool_tx = Spinbox(
            frame, width=10, textvariable=self.var_goniotool_tx, from_=1, to=12, increment=1
        )
        e_goniotool_tx.grid(row=5, column=1, sticky='EW')
        b_goniotool_set = Button(frame, text='Set', command=self.set_goniotool_tx)
        b_goniotool_set.grid(row=5, column=2, sticky='EW')
        if config.settings.use_goniotool:
            b_goniotool_default = Button(
                frame, text='Default', command=self.set_goniotool_tx_default
            )
            b_goniotool_default.grid(row=5, column=3, sticky='W')

        b_negative_angle = Button(frame, text='Set', command=self.set_negative_angle)
        b_negative_angle.grid(row=1, column=2, sticky='W')
        b_neutral_angle = Button(frame, text='Set', command=self.set_neutral_angle)
        b_neutral_angle.grid(row=2, column=2, sticky='W')
        b_positive_angle = Button(frame, text='Set', command=self.set_positive_angle)
        b_positive_angle.grid(row=3, column=2, sticky='W')

        b_stage = Button(frame, text='Set', command=self.set_stage)
        b_stage.grid(row=6, column=4, sticky='W')
        b_stage_get = Button(frame, text='Get', command=self.get_stage)
        b_stage_get.grid(row=6, column=5, sticky='W')

        # defocus button
        Label(frame, text='Diff defocus', width=20).grid(row=13, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(
            frame,
            textvariable=self.var_diff_defocus,
            width=10,
            from_=-10000,
            to=10000,
            increment=100,
        )
        self.e_diff_defocus.grid(row=13, column=1, sticky='EW')

        self.c_toggle_defocus = Checkbutton(
            frame,
            text='Toggle defocus',
            variable=self.var_diff_defocus_on,
            command=self.toggle_diff_defocus,
        )
        self.c_toggle_defocus.grid(row=13, column=2, sticky='W', columnspan=2)

        self.b_reset_defocus = Button(
            frame, text='Reset', command=self.reset_diff_defocus, state=DISABLED
        )
        self.b_reset_defocus.grid(row=13, column=4, sticky='EW')

        # frame.grid_columnconfigure(1, weight=1)
        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)

        Label(frame, text='Brightness', width=20).grid(row=11, column=0, sticky='W')
        e_brightness = Entry(frame, width=10, textvariable=self.var_brightness)
        e_brightness.grid(row=11, column=1, sticky='W')

        b_brightness = Button(frame, text='Set', command=self.set_brightness)
        b_brightness.grid(row=11, column=2, sticky='W')

        b_brightness_get = Button(frame, text='Get', command=self.get_brightness)
        b_brightness_get.grid(row=11, column=3, sticky='W')

        slider = Scale(
            frame,
            variable=self.var_brightness,
            from_=0,
            to=2**16 - 1,
            orient=HORIZONTAL,
            command=self.set_brightness,
        )
        slider.grid(row=12, column=0, columnspan=3, sticky='EW')

        # Magnification
        Label(frame, text='Magnification', width=20).grid(row=14, column=0, sticky='W')
        mag_inc_btn = Button(frame, text='+', command=self.increase_mag)
        mag_inc_btn.grid(row=14, column=1)
        mag_dec_btn = Button(frame, text='-', command=self.decrease_mag)
        mag_dec_btn.grid(row=14, column=2)

        Label(frame, text='DiffFocus', width=20).grid(row=21, column=0, sticky='W')
        e_difffocus = Entry(frame, width=10, textvariable=self.var_difffocus)
        e_difffocus.grid(row=21, column=1, sticky='W')

        b_difffocus = Button(frame, text='Set', command=self.set_difffocus)
        b_difffocus.grid(row=21, column=2, sticky='WE')

        b_difffocus_get = Button(frame, text='Get', command=self.get_difffocus)
        b_difffocus_get.grid(row=21, column=3, sticky='W')

        slider = Scale(
            frame,
            variable=self.var_difffocus,
            from_=0,
            to=2**16 - 1,
            orient=HORIZONTAL,
            command=self.set_difffocus,
        )
        slider.grid(row=22, column=0, columnspan=3, sticky='EW')

        frame.pack(side='top', fill='x', padx=10, pady=10)

        from instamatic import controller

        self.ctrl = controller.get_instance()

    def init_vars(self):
        self.var_negative_angle = DoubleVar(value=-40)
        self.var_neutral_angle = DoubleVar(value=0)
        self.var_positive_angle = DoubleVar(value=40)

        self.var_mode = StringVar(value='diff')

        self.var_alpha_wobbler = DoubleVar(value=5)
        self.var_alpha_wobbler_on = BooleanVar(value=False)

        self.var_stage_x = IntVar(value=0)
        self.var_stage_y = IntVar(value=0)
        self.var_stage_z = IntVar(value=0)

        self.var_goniotool_tx = DoubleVar(value=1)

        self.var_brightness = IntVar(value=65535)
        self.var_difffocus = IntVar(value=65535)

        self.var_diff_defocus = IntVar(value=1500)
        self.var_diff_defocus_on = BooleanVar(value=False)

        self.var_stage_wait = BooleanVar(value=True)
        self.var_lmb_stage = BooleanVar(value=False)
        self.var_rmb_beam = BooleanVar(value=False)

    def set_mode(self, event=None):
        self.ctrl.mode.set(self.var_mode.get())

    def set_brightness(self, event=None):
        self.var_brightness.set(self.var_brightness.get())
        self.q.put(('ctrl', {'task': 'brightness.set', 'value': self.var_brightness.get()}))

    def get_brightness(self, event=None):
        self.var_brightness.set(self.ctrl.brightness.get())

    def increase_mag(self):
        self.ctrl.magnification.increase()
        print(f'Set magnification: {self.ctrl.magnification.get()}')

    def decrease_mag(self):
        self.ctrl.magnification.decrease()
        print(f'Set magnification: {self.ctrl.magnification.get()}')

    def reset_stage(self):
        self.ctrl.stage.neutral()

    def set_difffocus(self, event=None):
        self.var_difffocus.set(self.var_difffocus.get())
        self.q.put(('ctrl', {'task': 'difffocus.set', 'value': self.var_difffocus.get()}))

    def get_difffocus(self, event=None):
        self.var_difffocus.set(self.ctrl.difffocus.get())

    def _set_angle(self, var: Variable) -> None:
        kwargs = {'task': 'stage.set', 'a': var.get(), 'wait': self.var_stage_wait.get()}
        self.q.put(('ctrl', kwargs))

    def set_negative_angle(self):
        return self._set_angle(self.var_negative_angle)

    def set_neutral_angle(self):
        return self._set_angle(self.var_neutral_angle)

    def set_positive_angle(self):
        return self._set_angle(self.var_positive_angle)

    def set_goniotool_tx(self, event=None, value=None):
        if not value:
            value = self.var_goniotool_tx.get()
        try:
            self.ctrl.stage.set_rotation_speed(value)
        except AttributeError:
            print('This TEM does not implement `setRotationSpeed` method')
        except TEMCommunicationError:
            print('Could not connect to the stage rotation speed controller')

    def set_goniotool_tx_default(self, event=None):
        value = 12
        self.set_goniotool_tx(value=value)

    def set_stage(self):
        self.q.put(
            (
                'ctrl',
                {
                    'task': 'stage.set',
                    'x': self.var_stage_x.get(),
                    'y': self.var_stage_y.get(),
                    'z': self.var_stage_z.get(),
                    'wait': self.var_stage_wait.get(),
                },
            )
        )

    def get_stage(self, event=None):
        x, y, z, _, _ = self.ctrl.stage.get()
        self.var_stage_x.set(round(x))
        self.var_stage_y.set(round(y))
        self.var_stage_z.set(round(z))

    def toggle_alpha_wobbler(self):
        if self.var_alpha_wobbler_on.get():
            wobble_stop_event = threading.Event()
            wobbler_task_keywords = {
                'task': 'stage.alpha_wobbler',
                'delta': self.var_alpha_wobbler.get(),
                'event': wobble_stop_event,
            }
            try:
                self.q.put(('ctrl', wobbler_task_keywords), block=False)
            except queue.Full:
                pass
            else:
                self.wobble_stop_event = wobble_stop_event
        else:
            if self.wobble_stop_event:
                self.wobble_stop_event.set()

    def toggle_lmb_stage(self, _name, _index, _mode):
        """If self.var_lmb_stage, move stage using Left Mouse Button."""

        d = self.app.get_module('stream').click_dispatcher
        if not self.var_lmb_stage.get():
            d.listeners.pop('lmb_stage', None)
            return

        try:
            stage_matrix = self.ctrl.get_stagematrix()
        except KeyError:
            print('No stage matrix for current mode and magnification found.')
            print('Run `instamatic.calibrate_stagematrix` to use this feature.')
            self.var_lmb_stage.set(False)
            return

        def _callback(click: ClickEvent) -> None:
            if click.button == MouseButton.LEFT:
                cam_dim_x, cam_dim_y = self.ctrl.cam.get_camera_dimensions()
                pixel_delta = np.array([click.y - cam_dim_y / 2, click.x - cam_dim_x / 2])
                stage_delta = np.dot(pixel_delta, stage_matrix)
                self.ctrl.stage.move_in_projection(*stage_delta)

        d.add_listener('lmb_stage', _callback, active=True)

    def toggle_rmb_beam(self, _name, _index, _mode) -> None:
        """If self.var_rmb_beam, move beam using Right Mouse Button."""

        d = self.app.get_module('stream').click_dispatcher
        if not self.var_rmb_beam.get():
            d.listeners.pop('rmb_beam', None)
            return

        path = self.app.get_module('io').get_working_directory() / 'calib'
        try:
            calib_beamshift = CalibBeamShift.from_file(path / CALIB_BEAMSHIFT)
        except OSError:
            print(f'No {CALIB_BEAMSHIFT} file in directory {path} found.')
            print('Run `instamatic.calibrate_beamshift` there to use this feature.')
            self.var_rmb_beam.set(False)
            return

        binning = self.ctrl.cam.default_binsize

        def _callback(click: ClickEvent) -> None:
            if click.button == MouseButton.RIGHT:
                pixel_x = click.x * binning
                pixel_y = click.y * binning
                bs = calib_beamshift.pixelcoord_to_beamshift((pixel_y, pixel_x))
                self.ctrl.beamshift.set(*[float(b) for b in bs])

        d.add_listener('rmb_beam', _callback, active=True)

    def stage_stop(self):
        self.q.put(('ctrl', {'task': 'stage.stop'}))

    def find_eucentric_height(self):
        self.q.put(('ctrl', {'task': 'find_eucentric_height'}))

    def toggle_diff_defocus(self):
        if self.var_diff_defocus_on.get():
            offset = self.var_diff_defocus.get()
            self.ctrl.difffocus.defocus(offset=offset)
            self.b_reset_defocus.config(state=NORMAL)
        else:
            self.ctrl.difffocus.refocus()
            self.var_diff_defocus_on.set(False)

        self.get_difffocus()

    def reset_diff_defocus(self):
        self.ctrl.difffocus.refocus()
        self.var_diff_defocus_on.set(False)
        self.get_difffocus()


module = BaseModule(
    name='ctrl', display_name='control', tk_frame=ExperimentalCtrl, location='bottom'
)
commands = {}


if __name__ == '__main__':
    root = Tk()
    ExperimentalCtrl(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
