import threading
import time
from tkinter import *
from tkinter.ttk import *

from .base_module import BaseModule
from instamatic.utils.spinbox import Spinbox
from instamatic import config

ENABLE_FOOTFREE_OPTION = False


class ExperimentalcRED(LabelFrame):
    """GUI panel for doing cRED experiments on a Timepix camera and Gatan camera."""

    def __init__(self, parent, image_stream):
        LabelFrame.__init__(self, parent, text='Continuous rotation electron diffraction')
        self.parent = parent
        self.image_stream = image_stream

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)
        Label(frame, text='Exposure time (s):').grid(row=1, column=0, sticky='W')
        exposure_time = Spinbox(frame, textvariable=self.var_exposure_time, width=sbwidth, from_=0.0, to=100.0, increment=0.01)
        exposure_time.grid(row=1, column=1, sticky='W', padx=10)
        if config.settings.microscope[:3]=="fei":
            self.ExposureButton = Button(frame, text='Confirm Exposure', command=self.confirm_exposure_time, state=NORMAL)
            self.ExposureButton.grid(row=1, column=2, sticky='W')
            Checkbutton(frame, text='Beam unblanker', variable=self.var_unblank_beam).grid(row=1, column=3, sticky='W')
            Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=4, sticky='ew', pady=10)
        else:
            Checkbutton(frame, text='Beam unblanker', variable=self.var_unblank_beam).grid(row=1, column=2, sticky='W')
            Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=3, sticky='ew', pady=10)

        Checkbutton(frame, text='Enable image interval', variable=self.var_enable_image_interval, command=self.toggle_interval_buttons).grid(row=5, column=2, sticky='W')
        self.c_toggle_defocus = Checkbutton(frame, text='Toggle defocus', variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus, state=DISABLED)
        self.c_toggle_defocus.grid(row=6, column=2, sticky='W')

        Label(frame, text='Image interval:').grid(row=5, column=0, sticky='W')
        self.e_image_interval = Spinbox(frame, textvariable=self.var_image_interval, width=sbwidth, from_=1, to=9999, increment=1, state=DISABLED)
        self.e_image_interval.grid(row=5, column=1, sticky='W', padx=10)

        Label(frame, text='Diff defocus:').grid(row=6, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=sbwidth, from_=-10000, to=10000, increment=100, state=DISABLED)
        self.e_diff_defocus.grid(row=6, column=1, sticky='W', padx=10)

        Label(frame, text='Image exposure (s):').grid(row=7, column=0, sticky='W')
        self.e_image_exposure = Spinbox(frame, textvariable=self.var_exposure_time_image, width=sbwidth, from_=0.0, to=100.0, increment=0.01, state=DISABLED)
        self.e_image_exposure.grid(row=7, column=1, sticky='W', padx=10)

        self.RelaxButton = Button(frame, text='Relax beam', command=self.relax_beam, state=DISABLED)
        self.RelaxButton.grid(row=7, column=2, sticky='EW')

        if ENABLE_FOOTFREE_OPTION and config.settings.microscope[:3]!="fei":
            Separator(frame, orient=HORIZONTAL).grid(row=8, columnspan=3, sticky='ew', pady=10)

            Label(frame, text='Rotate to:').grid(row=9, column=0, sticky='W')
            self.e_endangle = Spinbox(frame, textvariable=self.var_footfree_rotate_to, width=sbwidth, from_=-80.0, to=80.0, increment=1.0, state=DISABLED)
            self.e_endangle.grid(row=9, column=1, sticky='W', padx=10)

            Checkbutton(frame, text='Footfree mode', variable=self.var_toggle_footfree, command=self.toggle_footfree).grid(row=9, column=4, sticky='W')

        elif config.settings.microscope[:3]=="fei":
            Separator(frame, orient=HORIZONTAL).grid(row=8, columnspan=4, sticky='ew', pady=10)

            Label(frame, text='Rotate to:').grid(row=9, column=0, sticky='W')
            self.e_endangle = Spinbox(frame, textvariable=self.var_footfree_rotate_to, width=sbwidth, from_=-80.0, to=80.0, increment=1.0, state=NORMAL)
            self.e_endangle.grid(row=9, column=1, sticky='W', padx=10)
            Label(frame, text='Rotation Speed:').grid(row=9, column=2, sticky='W')
            self.e_rotspeed = OptionMenu(frame, self.var_rotation_speed, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1)
            self.e_rotspeed.grid(row=9, column=3, sticky='W', padx=10)


        self.lb_coll0 = Label(frame, text='')
        self.lb_coll1 = Label(frame, text='')
        self.lb_coll2 = Label(frame, text='')
        self.lb_coll0.grid(row=10, column=0, columnspan=3, sticky='EW')
        self.lb_coll1.grid(row=11, column=0, columnspan=3, sticky='EW')
        self.lb_coll2.grid(row=12, column=0, columnspan=3, sticky='EW')
        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side='top', fill='x', expand=False, padx=10, pady=10)

        frame = Frame(self)
        Label(frame, text='Select output formats:').grid(row=5, columnspan=2, sticky='EW')
        Checkbutton(frame, text='.tiff', variable=self.var_save_tiff).grid(row=5, column=2, sticky='EW')
        Checkbutton(frame, text='XDS (.smv)', variable=self.var_save_xds).grid(row=5, column=3, sticky='EW')
        Checkbutton(frame, text='DIALS (.smv)', variable=self.var_save_dials).grid(row=6, column=2, sticky='EW')
        Checkbutton(frame, text='REDp (.mrc)', variable=self.var_save_red).grid(row=6, column=3, sticky='EW')
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)
        self.CollectionButton = Button(frame, text='Start Collection', command=self.start_collection)
        self.CollectionButton.grid(row=1, column=0, sticky='EW')

        if config.settings.microscope[:3]!="fei":
            self.CollectionStopButton = Button(frame, text='Stop Collection', command=self.stop_collection, state=DISABLED)
            self.CollectionStopButton.grid(row=1, column=1, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.pack(side='bottom', fill='x', padx=10, pady=10)

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
        self.var_rotation_speed = DoubleVar(value=0.1)
        self.mode = 'regular'

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_xds = BooleanVar(value=True)
        self.var_save_dials = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)

    def confirm_exposure_time(self):
        """Change the exposure time for Gatan camera. Need to stop and restart the data stream generation process"""
        self.image_stream.stop()
        time.sleep(0.3)
        self.image_stream.exposure = self.var_exposure_time.get()
        self.image_stream.start_loop()

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        # TODO: make a pop up window with the STOP button?
        if self.var_toggle_diff_defocus.get():
            self.var_toggle_diff_defocus.set(False)
            self.toggle_diff_defocus()

        if config.settings.microscope[:3]!="fei":
            self.CollectionStopButton.config(state=NORMAL)

        self.CollectionButton.config(state=DISABLED)
        if self.mode == 'footfree':
            self.lb_coll1.config(text='Data collection has started.')
            self.lb_coll2.config(text='Click STOP COLLECTION to end the experiment.')
        elif config.settings.microscope[:3]=="fei":
            self.lb_coll1.config(text='FEI cRED Data collection has started.')
            self.lb_coll2.config(text='Wait until the stage is rotated to the target angle.')
        else:
            self.lb_coll1.config(text='Now you can start to rotate the goniometer at any time.')
            self.lb_coll2.config(text='Click STOP COLLECTION BEFORE removing your foot from the pedal!')

        self.parent.bind_all('<space>', self.stop_collection)

        params = self.get_params()
        self.q.put(('cred', params))

        self.triggerEvent.set()

        if config.settings.microscope[:3]=="fei":
            def stop_collection():
                self.stopEvent.wait()
                self.CollectionButton.config(state=NORMAL)
                self.lb_coll1.config(text='')
                self.lb_coll2.config(text='')
            p = threading.Thread(target=stop_collection,args=())
            p.start()

    def stop_collection(self, event=None):
        self.stopEvent.set()

        self.parent.unbind_all('<space>')

        self.CollectionStopButton.config(state=DISABLED)
        self.CollectionButton.config(state=NORMAL)
        self.lb_coll1.config(text='')
        self.lb_coll2.config(text='')

    def get_params(self):
        params = {'exposure_time': self.var_exposure_time.get(),
                  'exposure_time_image': self.var_exposure_time_image.get(),
                  'unblank_beam': self.var_unblank_beam.get(),
                  'enable_image_interval': self.var_enable_image_interval.get(),
                  'image_interval': self.var_image_interval.get(),
                  'diff_defocus': self.var_diff_defocus.get(),
                  'mode': self.mode,
                  'footfree_rotate_to': self.var_footfree_rotate_to.get(),
                  'rotation_speed': self.var_rotation_speed.get(),
                  'write_tiff': self.var_save_tiff.get(),
                  'write_xds': self.var_save_xds.get(),
                  'write_dials': self.var_save_dials.get(),
                  'write_red': self.var_save_red.get(),
                  'stop_event': self.stopEvent}
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

        self.q.put(('relax_beam', {'value': difffocus}))
        self.triggerEvent.set()

    def toggle_footfree(self):
        enable = self.var_toggle_footfree.get()
        if enable:
            self.mode = 'footfree'
            self.e_endangle.config(state=NORMAL)
            self.e_rotspeed.config(state=NORMAL)
        else:
            self.mode == 'regular'
            self.e_endangle.config(state=DISABLED)
            self.e_rotspeed.config(state=DISABLED)

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()
        difffocus = self.var_diff_defocus.get()

        self.q.put(('toggle_difffocus', {'value': difffocus, 'toggle': toggle}))
        self.triggerEvent.set()


def acquire_data_cRED(controller, **kwargs):
    controller.log.info('Start cRED experiment')
    from instamatic.experiments import cRED

    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)

    cexp = cRED.Experiment(ctrl=controller.ctrl, path=expdir, flatfield=controller.module_io.get_flatfield(), log=controller.log, **kwargs)

    success = cexp.start_collection()

    if not success:
        return

    controller.log.info('Finish cRED experiment')

    if controller.use_indexing_server:
        controller.q.put(('autoindex', {'task': 'run', 'path': cexp.smv_path}))
        controller.triggerEvent.set()


module = BaseModule(name='cred', display_name='cRED', tk_frame=ExperimentalcRED, location='bottom')
commands = {'cred': acquire_data_cRED}


if __name__ == '__main__':
    root = Tk()
    ExperimentalcRED(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
