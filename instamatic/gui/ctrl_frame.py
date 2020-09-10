import threading
from tkinter import *
from tkinter.ttk import *
import tkinter

from .base_module import BaseModule
from instamatic import config
from instamatic.utils.spinbox import Spinbox


class ExperimentalCtrl(LabelFrame):
    """This panel holds some frequently used functions to control the electron
    microscope."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='TEM Control')

        from instamatic import TEMController
        self.ctrl = TEMController.get_instance()
        self.mode = self.ctrl.mode.state

        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        Label(frame, text='Alpha Angle', width=15).grid(row=1, column=0, sticky='W')
        Label(frame, text='Wobbler (±)', width=15).grid(row=2, column=0, sticky='W')
        Label(frame, text='Stage(XYZ)', width=15).grid(row=3, column=0, sticky='W')

        e_alpha_angle = Spinbox(frame, width=10, textvariable=self.var_alpha_angle, from_=-90, to=90, increment=5)
        e_alpha_angle.grid(row=1, column=1, sticky='EW')
        b_alpha_angle = Button(frame, text='Set', command=self.set_alpha_angle)
        b_alpha_angle.grid(row=1, column=2, sticky='W')
        b_alpha_angle_get = Button(frame, text='Get', command=self.get_alpha_angle)
        b_alpha_angle_get.grid(row=1, column=3, sticky='W')

        b_find_eucentric_height = Button(frame, text='Eucentric Height', command=self.find_eucentric_height)
        b_find_eucentric_height.grid(row=1, column=4, sticky='EW', columnspan=2)

        if config.settings.microscope[:3] != "fei":
            b_stage_stop = Button(frame, text='Stop stage', command=self.stage_stop)
            b_stage_stop.grid(row=1, column=5, sticky='W')

        cb_nowait = Checkbutton(frame, text='Wait for stage', variable=self.var_stage_wait)
        cb_nowait.grid(row=1, column=6, sticky='W')

        e_alpha_wobbler = Spinbox(frame, width=10, textvariable=self.var_alpha_wobbler, from_=-90, to=90, increment=1)
        e_alpha_wobbler.grid(row=2, column=1, sticky='EW')
        self.b_start_wobble = Button(frame, text='Start', command=self.start_alpha_wobbler)
        self.b_start_wobble.grid(row=2, column=2, sticky='W')
        self.b_stop_wobble = Button(frame, text='Stop', command=self.stop_alpha_wobbler, state=DISABLED)
        self.b_stop_wobble.grid(row=2, column=3, sticky='W')

        Label(frame, text='Select TEM Mode:').grid(row=2, column=4, columnspan=2, sticky='E')
        
        if config.settings.microscope[:3] == "fei":
            self.o_mode = OptionMenu(frame, self.var_mode, self.mode, 'LM', 'Mi', 'SA', 'Mh', 'LAD', 'D', command=self.set_mode)
        else:
            self.o_mode = OptionMenu(frame, self.var_mode, self.mode, 'diff', 'mag1', 'mag2', 'lowmag', 'samag', command=self.set_mode)
        self.o_mode.grid(row=2, column=6, sticky='E', padx=10)

        e_stage_x = Entry(frame, width=10, textvariable=self.var_stage_x)
        e_stage_x.grid(row=3, column=1, sticky='EW')
        e_stage_y = Entry(frame, width=10, textvariable=self.var_stage_y)
        e_stage_y.grid(row=3, column=2, sticky='EW')
        e_stage_y = Entry(frame, width=10, textvariable=self.var_stage_z)
        e_stage_y.grid(row=3, column=3, sticky='EW')

        if config.settings.use_goniotool:
            Label(frame, text='Speed', width=15).grid(row=4, column=0, sticky='W')
            e_goniotool_tx = Spinbox(frame, width=10, textvariable=self.var_goniotool_tx, from_=1, to=12, increment=1)
            e_goniotool_tx.grid(row=4, column=1, sticky='EW')
            b_goniotool_set = Button(frame, text='Set', command=self.set_goniotool_tx)
            b_goniotool_set.grid(row=4, column=2, sticky='W')
            b_goniotool_default = Button(frame, text='Default', command=self.set_goniotool_tx_default)
            b_goniotool_default.grid(row=4, column=3, sticky='W')

        b_stage = Button(frame, text='Set', command=self.set_stage)
        b_stage.grid(row=3, column=4, sticky='W')
        b_stage_get = Button(frame, text='Get', command=self.get_stage)
        b_stage_get.grid(row=3, column=5, sticky='W')

        frame.pack(side='top', fill='x', padx=10, pady=10)
        frame = Frame(self)

        # defocus button
        Label(frame, text='Diff Defocus', width=15).grid(row=5, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=10, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=5, column=1, sticky='EW')

        self.c_toggle_defocus = Checkbutton(frame, text='Toggle defocus ', variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=5, column=2, sticky='E', columnspan=2)

        self.b_reset_defocus = Button(frame, text='Reset', command=self.reset_diff_defocus, state=DISABLED)
        self.b_reset_defocus.grid(row=5, column=4, sticky='EW')

        Label(frame, text='Diff Defocus', width=15).grid(row=6, column=0, sticky='W')
        self.e_difffocus = Entry(frame, width=12, textvariable=self.var_difffocus)
        self.e_difffocus.grid(row=6, column=1, sticky='W')

        self.b_difffocus = Button(frame, width=10, text='Set', command=self.set_difffocus)
        self.b_difffocus.grid(row=6, column=2, sticky='W')

        self.b_difffocus_get = Button(frame, width=10, text='Get', command=self.get_difffocus)
        self.b_difffocus_get.grid(row=6, column=3, sticky='W')

        if self.ctrl.tem.name[:3] == 'fei':
            self.difffocus_slider = tkinter.Scale(frame, variable=self.var_difffocus, from_=-600000, to=600000, length=250, 
                showvalue=0, orient=HORIZONTAL, command=self.set_difffocus)
        else:
            self.difffocus_slider = tkinter.Scale(frame, variable=self.var_difffocus, from_=0, to=65535, length=250, 
                showvalue=0, orient=HORIZONTAL, command=self.set_difffocus)
        self.difffocus_slider.grid(row=6, column=4, columnspan=3, sticky='W')

        Label(frame, text='ObjFocus', width=15).grid(row=7, column=0, sticky='W')
        self.e_objfocus = Entry(frame, width=12, textvariable=self.var_objfocus)
        self.e_objfocus.grid(row=7, column=1, sticky='W')

        self.b_objfocus = Button(frame, width=10, text='Set', command=self.set_objfocus)
        self.b_objfocus.grid(row=7, column=2, sticky='W')

        self.b_objfocus_get = Button(frame, width=10, text='Get', command=self.get_objfocus)
        self.b_objfocus_get.grid(row=7, column=3, sticky='W')

        if self.ctrl.tem.name[:3] == 'fei':
            self.objfocus_slider = tkinter.Scale(frame, variable=self.var_objfocus, from_=-600000, to=600000, length=250, 
                showvalue=0, orient=HORIZONTAL, command=self.set_objfocus)
        else:
            self.objfocus_slider = tkinter.Scale(frame, variable=self.var_objfocus, from_=0, to=65535, length=250, 
                showvalue=0, orient=HORIZONTAL, command=self.set_objfocus)
        self.objfocus_slider.grid(row=7, column=4, columnspan=3, sticky='W')

        self.set_gui_diffobj()

        Label(frame, text='Brightness', width=15).grid(row=8, column=0, sticky='W')
        e_brightness = Entry(frame, width=12, textvariable=self.var_brightness)
        e_brightness.grid(row=8, column=1, sticky='W')

        b_brightness = Button(frame, width=10, text='Set', command=self.set_brightness)
        b_brightness.grid(row=8, column=2, sticky='W')

        b_brightness_get = Button(frame, width=10, text='Get', command=self.get_brightness)
        b_brightness_get.grid(row=8, column=3, sticky='W')

        if self.ctrl.tem.name[:3] == 'fei':
            slider = tkinter.Scale(frame, variable=self.var_brightness, from_=-1.0, to=1.0, resolution=0.01, length=250, 
                showvalue=0, orient=HORIZONTAL, command=self.set_brightness)
        else:
            slider = tkinter.Scale(frame, variable=self.var_brightness, from_=0, to=65535, length=250, orient=HORIZONTAL, 
                showvalue=0, command=self.set_brightness)
        slider.grid(row=8, column=4, columnspan=3, sticky='W')

        frame.pack(side='top', fill='x', padx=10, pady=10)

    def init_vars(self):
        self.var_alpha_angle = DoubleVar(value=0.0)

        self.var_mode = StringVar(value=self.mode)

        self.var_alpha_wobbler = DoubleVar(value=5)

        self.var_stage_x = DoubleVar(value=0)
        self.var_stage_y = DoubleVar(value=0)
        self.var_stage_z = DoubleVar(value=0)

        self.var_goniotool_tx = IntVar(value=1)

        if self.ctrl.tem.name[:3] == 'fei':
            self.var_brightness = DoubleVar(value=self.ctrl.brightness.value)
            if self.mode in ('D', 'LAD'):
                self.var_difffocus = IntVar(value=self.ctrl.difffocus.value)
                self.var_objfocus = IntVar(value=0)
            else:
                self.var_difffocus = IntVar(value=0)
                self.var_objfocus = IntVar(value=self.ctrl.objfocus.value)
        else:
            self.var_brightness = IntVar(value=self.ctrl.brightness.value)
            if self.mode in ('diff'):
                self.var_difffocus = IntVar(value=self.ctrl.difffocus.value)
                self.var_objfocus = IntVar(value=0)
            else:
                self.var_difffocus = IntVar(value=0)
                self.var_objfocus = IntVar(value=self.ctrl.objfocus.value)

        self.var_diff_defocus = IntVar(value=1500)
        self.var_toggle_diff_defocus = BooleanVar(value=False)

        self.var_stage_wait = BooleanVar(value=True)

    def GUI_DiffFocus(self):
        self.e_diff_defocus.config(state=NORMAL)
        self.c_toggle_defocus.config(state=NORMAL)
        self.b_reset_defocus.config(state=NORMAL)
        self.e_difffocus.config(state=NORMAL)
        self.b_difffocus.config(state=NORMAL)
        self.b_difffocus_get.config(state=NORMAL)
        self.difffocus_slider.config(state=NORMAL)
        self.e_objfocus.config(state=DISABLED)
        self.b_objfocus.config(state=DISABLED)
        self.b_objfocus_get.config(state=DISABLED)
        self.objfocus_slider.config(state=DISABLED)

    def GUI_ObjFocus(self):
        self.e_diff_defocus.config(state=DISABLED)
        self.c_toggle_defocus.config(state=DISABLED)
        self.b_reset_defocus.config(state=DISABLED)
        self.e_difffocus.config(state=DISABLED)
        self.b_difffocus.config(state=DISABLED)
        self.b_difffocus_get.config(state=DISABLED)
        self.difffocus_slider.config(state=DISABLED)
        self.e_objfocus.config(state=NORMAL)
        self.b_objfocus.config(state=NORMAL)
        self.b_objfocus_get.config(state=NORMAL)
        self.objfocus_slider.config(state=NORMAL)

    def set_gui_diffobj(self):
        if self.ctrl.tem.name[:3] == 'fei':
            if self.ctrl.mode.state in ('D','LAD'):
                self.GUI_DiffFocus()
            else:
                self.GUI_ObjFocus()
        else:
            if self.ctrl.mode.state == 'diff':
                self.GUI_DiffFocus()
            else:
                self.GUI_ObjFocus()

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def set_mode(self, event=None):
        if self.ctrl.cam.name[:2] == 'DM':
            if self.var_mode.get() in ('D', 'LAD'):
                self.ctrl.tem.setProjectionMode('diffraction')
                self.var_mode.set(self.ctrl.mode.state)
                self.q.put(('ctrl', {'task': 'in_diff_state'}))
                self.triggerEvent.set()
            else:
                self.ctrl.tem.setProjectionMode('imaging')
                self.var_mode.set(self.ctrl.mode.state)
                self.q.put(('ctrl', {'task': 'in_img_state'}))
                self.triggerEvent.set()
            self.set_gui_diffobj()
        else:
            self.ctrl.mode.set(self.var_mode.get())
            self.set_gui_diffobj()

    def set_brightness(self, event=None):
        self.var_brightness.set(self.var_brightness.get())
        self.q.put(('ctrl', {'task': 'brightness.set',
                             'value': self.var_brightness.get()}))
        self.triggerEvent.set()

    def get_brightness(self, event=None):
        self.var_brightness.set(self.ctrl.brightness.get())

    def set_difffocus(self, event=None):
        self.var_difffocus.set(self.var_difffocus.get())
        self.q.put(('ctrl', {'task': 'difffocus.set',
                             'value': self.var_difffocus.get()}))
        self.triggerEvent.set()

    def get_difffocus(self, event=None):
        self.var_difffocus.set(self.ctrl.difffocus.get())

    def set_objfocus(self, event=None):
        self.var_objfocus.set(self.var_objfocus.get())
        self.q.put(('ctrl', {'task': 'objfocus.set',
                             'value': self.var_objfocus.get()}))
        self.triggerEvent.set()

    def get_objfocus(self, event=None):
        self.var_objfocus.set(self.ctrl.objfocus.get())

    def get_alpha_angle(self):
        self.var_alpha_angle.set(self.ctrl.stage.a)

    def set_alpha_angle(self):
        self.q.put(('ctrl', {'task': 'stage.set',
                             'a': self.var_alpha_angle.get(),
                             'wait': self.var_stage_wait.get()}))
        self.triggerEvent.set()

    def set_goniotool_tx(self, event=None, value=None):
        if not value:
            value = self.var_goniotool_tx.get()
        self.ctrl.stage.set_rotation_speed(value)

    def set_goniotool_tx_default(self, event=None):
        value = 12
        self.set_goniotool_tx(value=value)

    def set_stage(self):
        self.q.put(('ctrl', {'task': 'stage.set',
                             'x': self.var_stage_x.get(),
                             'y': self.var_stage_y.get(),
                             'z': self.var_stage_z.get(),
                             'wait': self.var_stage_wait.get()}))
        self.triggerEvent.set()

    def get_stage(self, event=None):
        x, y, z, _, _ = self.ctrl.stage.get()
        self.var_stage_x.set(round(x,2))
        self.var_stage_y.set(round(y,2))
        self.var_stage_z.set(round(z,2))

    def start_alpha_wobbler(self):
        self.wobble_stop_event = threading.Event()

        self.b_stop_wobble.config(state=NORMAL)
        self.b_start_wobble.config(state=DISABLED)

        self.q.put(('ctrl', {'task': 'stage.alpha_wobbler',
                             'delta': self.var_alpha_wobbler.get(),
                             'event': self.wobble_stop_event}))
        self.triggerEvent.set()

    def stop_alpha_wobbler(self):
        self.wobble_stop_event.set()

        self.b_stop_wobble.config(state=DISABLED)
        self.b_start_wobble.config(state=NORMAL)

    def stage_stop(self):
        self.q.put(('ctrl', {'task': 'stage.stop'}))
        self.triggerEvent.set()

    def find_eucentric_height(self):
        self.q.put(('ctrl', {'task': 'find_eucentric_height'}))
        self.triggerEvent.set()

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()

        if toggle:
            offset = self.var_diff_defocus.get()
            self.ctrl.difffocus.defocus(offset=offset)
            self.b_reset_defocus.config(state=NORMAL)
        else:
            self.ctrl.difffocus.refocus()
            self.var_toggle_diff_defocus.set(False)

        self.get_difffocus()

    def reset_diff_defocus(self):
        self.ctrl.difffocus.refocus()
        self.var_toggle_diff_defocus.set(False)
        self.get_difffocus()


module = BaseModule(name='ctrl', display_name='control', tk_frame=ExperimentalCtrl, location='bottom')
commands = {}

def run(ctrl, trigger, q):
    from .modules import JOBS

    while True:
        trigger.wait()
        trigger.clear()

        job, kwargs = q.get()
        try:
            print(job)
            func = JOBS[job]
        except KeyError:
            print(f'Unknown job: {job}')
            print(f'Kwargs:\n{kwargs}')
            continue
        func(ctrl, **kwargs)


if __name__ == '__main__':
    import threading
    import queue
    
    root = Tk()
    trigger = threading.Event()
    q = queue.LifoQueue(maxsize=1)
    ctrl = ExperimentalCtrl(root)
    ctrl.pack(side='top', fill='both', expand=True)
    ctrl.set_trigger(trigger=trigger, q=q)

    p = threading.Thread(target=run, args=(ctrl,trigger,q,))
    p.start()

    root.mainloop()
    ctrl.ctrl.close()
