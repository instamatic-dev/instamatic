import threading
from pathlib import Path
from tkinter import *
from tkinter import filedialog
from tkinter.ttk import *

from .base_module import BaseModule
from instamatic import config
from instamatic.utils.spinbox import Spinbox

barrier = threading.Barrier(2, timeout=60)


class ExperimentalTVIPS(LabelFrame):
    """GUI panel for doing cRED / SerialRED experiments on a TVIPS camera."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Continuous rotation electron diffraction (TVIPS)')
        self.parent = parent

        sbwidth = 10

        self.init_vars()

        frame = Frame(self)

        Label(frame, text='Target angle (degrees):').grid(row=4, column=0, sticky='W')
        self.e_target_angle = Spinbox(frame, textvariable=self.var_target_angle, width=sbwidth, from_=-80.0, to=80.0, increment=5.0, state=NORMAL)
        self.e_target_angle.grid(row=4, column=1, sticky='W', padx=10)

        self.InvertAngleButton = Button(frame, text='Invert', command=self.invert_angle)
        self.InvertAngleButton.grid(row=4, column=2, sticky='EW')

        self.c_toggle_manual_control = Checkbutton(frame, text='Manual rotation control', variable=self.var_toggle_manual_control, command=self.toggle_manual_control)
        self.c_toggle_manual_control.grid(row=4, column=3, sticky='W')

        # defocus button
        Label(frame, text='Diff defocus:').grid(row=6, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=sbwidth, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=6, column=1, sticky='W', padx=10)

        Label(frame, text='Exposure (ms):').grid(row=7, column=0, sticky='W')
        self.e_exposure = Spinbox(frame, textvariable=self.var_exposure, width=sbwidth, from_=0, to=10000, increment=100)
        self.e_exposure.grid(row=7, column=1, sticky='W', padx=10)

        Label(frame, text='Mode:').grid(row=8, column=0, sticky='W')
        self.o_mode = OptionMenu(frame, self.var_mode, 'diff', 'diff', 'mag1', 'mag2', 'lowmag', 'samag')
        self.o_mode.grid(row=8, column=1, sticky='W', padx=10)

        if config.settings.use_goniotool:
            Label(frame, text='Rot. Speed', width=20).grid(row=10, column=0, sticky='W')
            self.o_goniotool_tx = OptionMenu(frame, self.var_goniotool_tx, 1, *list(range(1, 13)))
            self.o_goniotool_tx.grid(row=10, column=1, sticky='W', padx=10)

        self.b_reset_defocus = Button(frame, text='Reset', command=self.reset_diff_defocus, state=DISABLED)
        self.b_reset_defocus.grid(row=6, column=2, sticky='EW')

        self.c_toggle_defocus = Checkbutton(frame, text='Toggle defocus', variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=6, column=3, sticky='W')

        self.c_toggle_diffraction = Checkbutton(frame, text='Toggle DIFF', variable=self.var_toggle_diff_mode, command=self.toggle_diff_mode)
        self.c_toggle_diffraction.grid(row=7, column=3, sticky='W')

        self.c_toggle_screen = Checkbutton(frame, text='Toggle screen', variable=self.var_toggle_screen, command=self.toggle_screen)
        self.c_toggle_screen.grid(row=8, column=3, sticky='W')

        self.b_start_liveview = Button(frame, text='Start live view', command=self.start_liveview)
        self.b_start_liveview.grid(row=7, column=2, sticky='EW')

        self.b_stop_liveview = Button(frame, text='Stop live view', command=self.stop_liveview)
        self.b_stop_liveview.grid(row=8, column=2, sticky='EW')

        self.c_toggle_beamblank = Checkbutton(frame, text='Toggle beamblank', variable=self.var_toggle_beamblank, command=self.toggle_beamblank)
        self.c_toggle_beamblank.grid(row=10, column=3, sticky='W')

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)

        self.SearchButton = Button(frame, text='Search', command=self.search)
        self.SearchButton.grid(row=1, column=0, sticky='EW')

        self.FocusButton = Button(frame, text='Focus', command=self.focus)
        self.FocusButton.grid(row=1, column=1, sticky='EW')

        self.GetImageButton = Button(frame, text='Get image', command=self.get_image)
        self.GetImageButton.grid(row=1, column=2, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        frame.pack(fill='x', padx=10, pady=10)

        frame = Frame(self)

        self.e_instructions = Entry(frame, width=50, textvariable=self.var_instruction_file)
        self.e_instructions.grid(row=4, column=1, sticky='EW')
        self.BrowseTrackButton = Button(frame, text='Browse..', command=self.browse_instructions)
        self.BrowseTrackButton.grid(row=4, column=2, sticky='EW')
        Label(frame, text='Instruction file:').grid(row=4, column=0, sticky='W')

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)

        self.SerialButton = Button(frame, text='Start serial acquisition', width=25, command=self.serial_collection)
        self.SerialButton.grid(row=1, column=0, sticky='EW')

        frame.pack(fill='x', padx=10, pady=10)

        frame = Frame(self)
        self.GetReadyButton = Button(frame, text='Get Ready', command=self.prime_collection)
        self.GetReadyButton.grid(row=1, column=0, sticky='EW')

        self.AcquireButton = Button(frame, text='Acquire', command=self.start_collection, state=DISABLED)
        self.AcquireButton.grid(row=1, column=1, sticky='EW')

        self.FinalizeButton = Button(frame, text='Finalize', command=self.stop_collection, state=DISABLED)
        self.FinalizeButton.grid(row=1, column=2, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        frame.pack(side='bottom', fill='x', padx=10, pady=10)

        from instamatic import TEMController
        self.ctrl = TEMController.get_instance()

    def init_vars(self):
        self.var_target_angle = DoubleVar(value=40.0)
        self.var_exposure = IntVar(value=400)

        self.var_save_tiff = BooleanVar(value=True)
        self.var_save_red = BooleanVar(value=True)

        self.var_diff_defocus = IntVar(value=1500)
        self.var_toggle_diff_defocus = BooleanVar(value=False)

        self.var_toggle_beamblank = BooleanVar(value=False)
        self.var_toggle_diff_mode = BooleanVar(value=False)
        self.var_toggle_screen = BooleanVar(value=False)
        self.var_toggle_manual_control = BooleanVar(value=False)

        self.var_instruction_file = StringVar(value='')
        self.var_mode = StringVar(value='diff')

        self.var_goniotool_tx = IntVar(value=1)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def invert_angle(self):
        angle = self.var_target_angle.get()
        self.var_target_angle.set(-angle)

    def disable_ui(self):
        self.InvertAngleButton.config(state=DISABLED)
        self.GetReadyButton.config(state=DISABLED)
        self.AcquireButton.config(state=DISABLED)
        self.FinalizeButton.config(state=NORMAL)
        self.SerialButton.config(state=DISABLED)
        self.e_target_angle.config(state=DISABLED)
        self.SearchButton.config(state=DISABLED)
        self.FocusButton.config(state=DISABLED)
        self.GetImageButton.config(state=DISABLED)
        self.b_start_liveview.config(state=DISABLED)
        self.b_stop_liveview.config(state=DISABLED)

    def enable_ui(self):
        self.InvertAngleButton.config(state=NORMAL)
        self.GetReadyButton.config(state=NORMAL)
        self.AcquireButton.config(state=DISABLED)
        self.FinalizeButton.config(state=DISABLED)
        self.SerialButton.config(state=NORMAL)
        if not self.var_toggle_manual_control.get():
            self.e_target_angle.config(state=NORMAL)
        self.SearchButton.config(state=NORMAL)
        self.FocusButton.config(state=NORMAL)
        self.GetImageButton.config(state=NORMAL)
        self.b_start_liveview.config(state=NORMAL)
        self.b_stop_liveview.config(state=NORMAL)

    def prime_collection(self):
        self.disable_ui()
        # self.e_target_angle.config(state=DISABLED)
        params = self.get_params(task='get_ready')
        self.q.put(('cred_tvips', params))
        self.triggerEvent.set()

        def worker(button=None, state=None):
            barrier.wait()  # wait for experiment to be primed
            button.config(state=state)

        t = threading.Thread(target=worker, kwargs={'button': self.AcquireButton, 'state': NORMAL})
        t.start()

    def start_collection(self):
        self.AcquireButton.config(state=DISABLED)
        params = self.get_params(task='acquire')
        self.q.put(('cred_tvips', params))
        self.triggerEvent.set()

    def stop_collection(self):
        self.enable_ui()
        params = self.get_params(task='stop')
        self.q.put(('cred_tvips', params))
        self.triggerEvent.set()

    def serial_collection(self):
        self.disable_ui()
        params = self.get_params(task='serial')
        self.q.put(('cred_tvips', params))
        self.triggerEvent.set()

    def browse_instructions(self):
        fn = filedialog.askopenfilename(parent=self.parent, initialdir=None, title='Select instruction file')
        if not fn:
            return
        fn = Path(fn).absolute()
        self.var_instruction_file.set(fn)
        return fn

    def get_params(self, task=None):
        params = {'target_angle': self.var_target_angle.get(),
                  'instruction_file': self.var_instruction_file.get(),
                  'exposure': self.var_exposure.get(),
                  'mode': self.var_mode.get(),
                  'rotation_speed': self.var_goniotool_tx.get(),
                  'manual_control': self.var_toggle_manual_control.get(),
                  'task': task}
        return params

    def toggle_manual_control(self):
        toggle = self.var_toggle_manual_control.get()

        if toggle:
            self.e_target_angle.config(state=DISABLED)
        else:
            self.e_target_angle.config(state=NORMAL)

    def toggle_diff_mode(self):
        toggle = self.var_toggle_diff_mode.get()

        if toggle:
            self.ctrl.mode.set('diff')
        else:
            self.ctrl.mode.set('mag1')

    def toggle_beamblank(self):
        toggle = self.var_toggle_beamblank.get()

        if toggle:
            self.ctrl.beam.blank()
        else:
            self.ctrl.beam.unblank()

    def toggle_screen(self):
        toggle = self.var_toggle_screen.get()

        if toggle:
            self.ctrl.screen.up()
        else:
            self.ctrl.screen.down()

    def start_liveview(self):
        self.q.put(('ctrl', {'task': 'cam.start_liveview'}))
        self.triggerEvent.set()

    def stop_liveview(self):
        self.q.put(('ctrl', {'task': 'cam.stop_liveview'}))
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

    def reset_diff_defocus(self):
        self.ctrl.difffocus.refocus()
        self.var_toggle_diff_defocus.set(False)

    def search(self):
        self.ctrl.run_script('search_mode.py')

    def focus(self):
        self.ctrl.run_script('focus_mode.py')

    def get_image(self):
        self.ctrl.cam.acquireImage()


def acquire_data_CRED_TVIPS(controller, **kwargs):
    controller.log.info('Start cRED (TVIPS) experiment')
    from instamatic.experiments import cRED_tvips

    task = kwargs['task']

    target_angle = kwargs['target_angle']
    instruction_file = kwargs['instruction_file']
    exposure = kwargs['exposure']
    manual_control = kwargs['manual_control']
    rotation_speed = kwargs['rotation_speed']
    mode = kwargs['mode']

    if task == 'get_ready':
        expdir = controller.module_io.get_new_experiment_directory()
        expdir.mkdir(exist_ok=True, parents=True)

        controller.cred_tvips_exp = cRED_tvips.Experiment(ctrl=controller.ctrl, path=expdir,
                                                          log=controller.log, mode=mode,
                                                          track=instruction_file, exposure=exposure,
                                                          rotation_speed=rotation_speed)
        controller.cred_tvips_exp.get_ready()

        barrier.wait()  # synchronize with GUI
    elif task == 'acquire':
        controller.cred_tvips_exp.start_collection(target_angle=target_angle,
                                                   manual_control=manual_control)
    elif task == 'serial':
        expdir = controller.module_io.get_new_experiment_directory()
        expdir.mkdir(exist_ok=True, parents=True)

        cred_tvips_exp = cRED_tvips.SerialExperiment(ctrl=controller.ctrl, path=expdir,
                                                     log=controller.log, mode=mode,
                                                     instruction_file=instruction_file, exposure=exposure,
                                                     target_angle=target_angle, rotation_speed=rotation_speed)
        cred_tvips_exp.run()
    elif task == 'stop':
        pass


module = BaseModule(name='tvips', display_name='TVIPS', tk_frame=ExperimentalTVIPS, location='bottom')
commands = {'cred_tvips': acquire_data_CRED_TVIPS}


if __name__ == '__main__':
    root = Tk()
    ExperimentalTVIPS(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
