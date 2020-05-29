import datetime
import os
import pickle
import threading
from pathlib import Path
from tkinter import *
from tkinter.ttk import *

import matplotlib.pyplot as plt

from .base_module import BaseModule
from instamatic import config
from instamatic.calibrate import CalibBeamShift
from instamatic.calibrate.filenames import *


class ExperimentalautocRED(LabelFrame):
    """Data collection protocol for SerialRED data collection on a high-speed
    Timepix camera using automated screening and crystal tracking.

    Related publication:     IUCrJ (2019). 6(5), 854-867
    https://doi.org/10.1107/S2052252519007681 .
    """

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Serial Rotation Electron Diffraction (SerialRED)')
        self.parent = parent

        self.init_vars()

        date = datetime.datetime.now().strftime('%Y-%m-%d')
        self.calib_path_is = config.locations['logs'] / f'ImageShift_LOGS_{date}'
        self.calib_path = Path('..')

        frame = Frame(self)
        Label(frame, text='Exposure time:').grid(row=1, column=0, sticky='W')
        self.exposure_time = Entry(frame, textvariable=self.var_exposure_time)
        self.exposure_time.grid(row=1, column=1, sticky='W', padx=10)

        Checkbutton(frame, text='Beam unblanker', variable=self.var_unblank_beam).grid(row=1, column=2, sticky='W')

        Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=3, sticky='ew', pady=10)

        Checkbutton(frame, text='Enable image interval', variable=self.var_enable_image_interval, command=self.toggle_interval_buttons).grid(row=5, column=2, sticky='W')
        self.c_toggle_defocus = Checkbutton(frame, text='Toggle defocus', variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=6, column=2, sticky='W')

        Label(frame, text='Image interval:').grid(row=5, column=0, sticky='W')
        self.e_image_interval = Spinbox(frame, textvariable=self.var_image_interval, from_=1, to=9999, increment=1)
        self.e_image_interval.grid(row=5, column=1, sticky='W', padx=10)

        Label(frame, text='Diff defocus:').grid(row=6, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=6, column=1, sticky='W', padx=10)

        Label(frame, text='Exposure (image):').grid(row=7, column=0, sticky='W')
        self.e_image_exposure = Spinbox(frame, textvariable=self.var_exposure_time_image, width=10, from_=0.0, to=100.0, increment=0.01)
        self.e_image_exposure.grid(row=7, column=1, sticky='W', padx=10)

        Label(frame, text='Scan Area (um):').grid(row=8, column=0, sticky='W')
        self.scan_area = Entry(frame, textvariable=self.var_scan_area)
        self.scan_area.grid(row=8, column=1, sticky='W', padx=10)

        Separator(frame, orient=HORIZONTAL).grid(row=12, columnspan=3, sticky='ew', pady=10)

        Label(frame, text='advanced variables').grid(row=13, column=0, sticky='W')

        Label(frame, text='angle activation deadtime (s):').grid(row=14, column=0, sticky='W')
        self.activ_thr = Entry(frame, textvariable=self.var_activ_thr)
        self.activ_thr.grid(row=14, column=1, sticky='W', padx=10)

        Label(frame, text='spread (particle recog):').grid(row=15, column=0, sticky='W')
        self.spread = Entry(frame, textvariable=self.var_spread)
        self.spread.grid(row=15, column=1, sticky='W', padx=10)

        Label(frame, text='offset (particle recog):').grid(row=16, column=0, sticky='W')
        self.offset = Entry(frame, textvariable=self.var_offset)
        self.offset.grid(row=16, column=1, sticky='W', padx=10)

        Label(frame, text='tilt range limit:').grid(row=14, column=2, sticky='W')
        self.rotrangelimit = Entry(frame, textvariable=self.var_rotrange)
        self.rotrangelimit.grid(row=14, column=2, sticky='E', padx=10)

        Label(frame, text='backlash estimation:').grid(row=15, column=2, sticky='W')
        self.backlash_killer = Entry(frame, textvariable=self.var_backlash)
        self.backlash_killer.grid(row=15, column=2, sticky='E', padx=10)

        Label(frame, text='expected rot speed').grid(row=16, column=2, sticky='W')
        self.rot_speed = Entry(frame, textvariable=self.var_rotspeed)
        self.rot_speed.grid(row=16, column=2, sticky='E', padx=10)

        self.acred_status = Checkbutton(frame, text='Enable Auto Tracking', variable=self.var_enable_autotrack, command=self.autotrack)
        self.acred_status.grid(row=7, column=2, sticky='W')

        self.fullacred_status = Checkbutton(frame, text='Enable Full AutocRED Feature', variable=self.var_enable_fullacred, command=self.fullacred)
        self.fullacred_status.grid(row=8, column=2, sticky='W')

        self.fullacred_crystalFinder_status = Checkbutton(frame, text='Enable Full AutocRED + crystal finder Feature', variable=self.var_enable_fullacred_crystalFinder, command=self.fullacred_crystalFinder)
        self.fullacred_crystalFinder_status.grid(row=9, column=2, sticky='W')

        self.zheight = Checkbutton(frame, text='Enable auto z height adjustment', variable=self.var_zheight)
        self.zheight.grid(row=10, column=2, sticky='W')

        self.auto_center_SMV = Checkbutton(frame, text='Enable auto center of SMV files', variable=self.var_autoc)
        self.auto_center_SMV.grid(row=11, column=2, sticky='W')

        frame.grid_columnconfigure(1, weight=1)
        frame.pack(side='top', fill='x', expand=False, padx=10, pady=10)

        frame = Frame(self)

        self.CollectionButton = Button(frame, text='Start Collection', command=self.start_collection)
        self.CollectionButton.grid(row=1, column=0, sticky='EW')

        self.CollectionStopButton = Button(frame, text='Stop Collection', command=self.stop_collection, state=DISABLED)
        self.CollectionStopButton.grid(row=1, column=1, sticky='EW')

        self.ShowCalibBeamshift = Button(frame, text='Stop Rotation', command=self.stop_collection_acred, state=NORMAL)
        self.ShowCalibBeamshift.grid(row=3, column=0, sticky='EW')

        self.ShowCalibBeamshift = Button(frame, text='Show calib_beamshift', command=self.show_calib_beamshift, state=NORMAL)
        self.ShowCalibBeamshift.grid(row=2, column=1, sticky='EW')

        self.acquireTEMStatusButton = Button(frame, text='Show calib_is', command=self.show_calib_is, state=NORMAL)
        self.acquireTEMStatusButton.grid(row=2, column=0, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.pack(side='bottom', fill='x', padx=10, pady=10)

        self.stopEvent = threading.Event()
        self.stopEvent_experiment = threading.Event()

    def init_vars(self):
        self.var_exposure_time = DoubleVar(value=0.5)
        self.var_unblank_beam = BooleanVar(value=True)
        self.var_image_interval = IntVar(value=10)
        self.var_diff_defocus = IntVar(value=1500)
        self.var_enable_image_interval = BooleanVar(value=True)
        self.var_toggle_diff_defocus = BooleanVar(value=False)
        self.var_exposure_time_image = DoubleVar(value=0.01)

        self.var_enable_autotrack = BooleanVar(value=True)
        self.var_enable_fullacred = BooleanVar(value=True)
        self.var_enable_fullacred_crystalFinder = BooleanVar(value=True)
        self.var_scan_area = IntVar(value=0)
        self.var_activ_thr = DoubleVar(value=0.1)
        self.var_spread = DoubleVar(value=2.0)
        self.var_offset = DoubleVar(value=15.0)
        self.var_zheight = BooleanVar(value=False)
        self.var_autoc = BooleanVar(value=True)
        self.var_rotrange = IntVar(value=70)
        self.var_backlash = DoubleVar(value=1.0)
        self.var_rotspeed = DoubleVar(value=0.86)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def start_collection(self):
        self.CollectionStopButton.config(state=NORMAL)
        self.CollectionButton.config(state=DISABLED)
        # self.lb_coll1.config(text="Now you can start to rotate the goniometer at any time.")
        # self.lb_coll2.config(text="Click STOP COLLECTION BEFORE removing your foot from the pedal!")

        self.parent.bind_all('<space>', self.stop_collection)

        params = self.get_params()
        self.q.put(('autocred', params))

        self.triggerEvent.set()

    def stop_collection(self, event=None):
        self.stopEvent_experiment.set()

        self.parent.unbind_all('<space>')

        self.CollectionStopButton.config(state=DISABLED)
        self.CollectionButton.config(state=NORMAL)
        # self.lb_coll1.config(text="")
        # self.lb_coll2.config(text="")

    def stop_collection_acred(self, event=None):
        self.stopEvent.set()

    def get_params(self):
        params = {'exposure_time': self.var_exposure_time.get(),
                  'exposure_time_image': self.var_exposure_time_image.get(),
                  'unblank_beam': self.var_unblank_beam.get(),
                  'enable_image_interval': self.var_enable_image_interval.get(),
                  'enable_autotrack': self.var_enable_autotrack.get(),
                  'enable_fullacred': self.var_enable_fullacred.get(),
                  'enable_fullacred_crystalfinder': self.var_enable_fullacred_crystalFinder.get(),
                  'image_interval': self.var_image_interval.get(),
                  'diff_defocus': self.var_diff_defocus.get(),
                  'scan_area': self.var_scan_area.get(),
                  'stop_event': self.stopEvent,
                  'stop_event_experiment': self.stopEvent_experiment,
                  'zheight': self.var_zheight.get(),
                  'autocenterDP': self.var_autoc.get(),
                  'angle_activation': self.var_activ_thr.get(),
                  'spread': self.var_spread.get(),
                  'offset': self.var_offset.get(),
                  'rotrange': self.var_rotrange.get(),
                  'backlash_killer': self.var_backlash.get(),
                  'rotation_speed': self.var_rotspeed.get()}
        return params

    def toggle_interval_buttons(self):
        enable = self.var_enable_image_interval.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
            self.acred_status.config(state=NORMAL)
            self.fullacred_status.config(state=NORMAL)
            self.fullacred_crystalFinder_status.config(state=NORMAL)
            self.e_image_exposure.config(state=NORMAL)
        else:
            self.e_image_interval.config(state=DISABLED)
            self.e_diff_defocus.config(state=DISABLED)
            self.c_toggle_defocus.config(state=DISABLED)
            self.acred_status.config(state=DISABLED)
            self.fullacred_status.config(state=DISABLED)
            self.fullacred_crystalFinder_status.config(state=DISABLED)
            self.e_image_exposure.config(state=DISABLED)

    def autotrack(self):
        enable = self.var_enable_autotrack.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
        # Focused beam, CC, Calibration for beam shift

    def fullacred(self):
        enable = self.var_enable_fullacred.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
            self.acred_status.config(state=NORMAL)

    def fullacred_crystalFinder(self):
        enable = self.var_enable_fullacred.get()
        if enable:
            self.e_image_interval.config(state=NORMAL)
            self.e_diff_defocus.config(state=NORMAL)
            self.c_toggle_defocus.config(state=NORMAL)
            self.acred_status.config(state=NORMAL)

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()
        difffocus = self.var_diff_defocus.get()

        self.q.put(('toggle_difffocus', {'value': difffocus, 'toggle': toggle}))
        self.triggerEvent.set()

    def show_calib_beamshift(self):
        # TODO: use mpl_frame.ShowMatplotlibFig
        path = self.calib_path / CALIB_BEAMSHIFT
        print(path)
        try:
            c = CalibBeamShift.from_file(path)
        except OSError as e:
            print(e)
        else:
            c.plot()

    def show_calib_is(self):
        idx = input("""Indicate which calibration you want to plot:
        1. IS1 defocused
        2. IS1 focused
        3. IS2 defocused
        4. IS2 focused
        5. Beamshift for DP
        6. Beamshift for DP defocused
        Only input a number and press ENTER>>""")
        idx = int(idx)

        FLIST = {1: CALIB_IS1_DEFOC,
                 2: CALIB_IS1_FOC,
                 3: CALIB_IS2_DEFOC,
                 4: CALIB_IS2_FOC,
                 5: CALIB_BEAMSHIFT_DP,
                 6: CALIB_BEAMSHIFT_DP_DEFOC,
                 }

        path = self.calib_path_is / FLIST[idx]
        print(path)
        try:
            with open(path, 'rb') as f:
                t, c = pickle.load(f)
        except OSError as e:
            print(e)
        else:
            plt.scatter(*c[1].T, marker='>', label='Observed pixel shifts')
            plt.scatter(*c[0].T, marker='<', label='Positions in pixel coords')
            plt.legend()
            plt.title('calibration map')
            plt.show()


def acquire_data_autocRED(controller, **kwargs):
    controller.log.info('Starting automatic cRED experiment')
    from instamatic.experiments import autocRED

    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)

    try:
        diff_defocus = controller.ctrl.difffocus.value + kwargs['diff_defocus']
    except BaseException:
        pass

    # controller.stream.get_module("sed").calib_path = expdir / "calib"

    cexp = autocRED.Experiment(ctrl=controller.ctrl,
                               path=expdir,
                               flatfield=controller.module_io.get_flatfield(),
                               log=controller.log,
                               **kwargs)
    cexp.start_collection()

    stop_event.clear()
    stop_event_experiment.clear()
    controller.log.info('Finish autocRED experiment')


module = BaseModule(name='autocred', display_name='autocRED', tk_frame=ExperimentalautocRED, location='bottom')
commands = {'autocred': acquire_data_autocRED}

if __name__ == '__main__':
    root = Tk()
    ExperimentalautocRED(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
