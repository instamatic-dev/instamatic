import atexit
import queue
import sys
import threading
import traceback
from tkinter import *
from tkinter.ttk import *

import instamatic
from .modules import JOBS
from .modules import MODULES
from instamatic.formats import *


class DataCollectionController(threading.Thread):
    """Event loop for the GUI.

    This class interfaces between the GUI and the underlying
    experiments. It runs in a separate thread and uses a queue to
    communicate tasks from the GUI to the instrument interface. This is
    important to keep the GUI responsive for long-running experiments.
    """

    def __init__(self, ctrl=None, stream=None, beam_ctrl=None, app=None, log=None):
        super().__init__()
        self.ctrl = ctrl
        self.stream = stream
        self.beam_ctrl = beam_ctrl
        self.app = app
        self.daemon = True

        self.use_indexing_server = False

        self.log = log

        self.q = queue.LifoQueue(maxsize=1)
        self.triggerEvent = threading.Event()

        self.module_io = self.app.get_module('io')

        for name, module in self.app.modules.items():
            try:
                module.set_trigger(trigger=self.triggerEvent, q=self.q)
            except AttributeError:
                pass  # module does not need/accept a trigger

        self.exitEvent = threading.Event()
        atexit.register(self.triggerEvent.set)
        atexit.register(self.exitEvent.set)
        atexit.register(self.close)

    def run(self):
        while True:
            self.triggerEvent.wait()
            self.triggerEvent.clear()

            if self.exitEvent.is_set():
                self.close()
                sys.exit()

            job, kwargs = self.q.get()

            try:
                func = JOBS[job]
            except KeyError:
                print(f'Unknown job: {job}')
                print(f'Kwargs:\n{kwargs}')
                continue

            try:
                func(self, **kwargs)
            except Exception as e:
                traceback.print_exc()
                self.log.debug(f"Error caught -> {repr(e)} while running '{job}' with {kwargs}")
                self.log.exception(e)

    def close(self):
        for item in (self.ctrl, self.stream, self.beam_ctrl, self.app):
            try:
                item.close()
            except AttributeError:
                pass


class AppLoader:
    """Loader for the main App.

    Initializes all the modules specified in `settings.yaml`
    """

    def __init__(self):
        super().__init__()
        self.modules = {}
        self.locations = ['left', 'top', 'bottom', 'right']

    def load(self, modules, master):

        panels = {}

        for location in self.locations:
            selected_modules = [module for module in modules if module.location == location]

            is_group = len(selected_modules) > 1

            if is_group:
                if location in panels:
                    nb = panels[location]
                else:
                    nb = Notebook(master, padding=10)
                    nb.pack(side=location, fill='both', expand='yes')
                    panels[location] = nb

            for module in selected_modules:
                if is_group:
                    page = Frame(nb)
                    nb.add(page, text=module.display_name)
                    parent = page
                else:
                    parent = master

                module_frame = module.initialize(parent)
                module_frame.pack(side=location, fill='both', expand='yes', padx=10, pady=10)
                self.modules[module.name] = module_frame

    def get_module(self, module):
        return self.modules[module]


class MainFrame:
    """This class defines the main GUI panel.

    Modules are loaded as defined through the `modules` variable.
    """

    def __init__(self, root, cam, modules: list = []):
        super().__init__()
        # the stream window is a special case, because it needs access
        # to the cam module
        if cam and cam.streamable:
            from .videostream_frame import module as stream_module
            stream_module.set_kwargs(stream=cam)
            modules.insert(0, stream_module)

        self.root = root

        self.module_frame = Frame(root)
        self.module_frame.pack(side='top', fill='both', expand=True)

        self.app = AppLoader()
        self.app.load(modules, self.module_frame)

        self.root.wm_title(instamatic.__long_title__)
        self.root.wm_protocol('WM_DELETE_WINDOW', self.close)

        self.root.bind('<Escape>', self.close)

    def close(self):
        try:
            self.stream_frame.close()
        except AttributeError:
            pass
        sys.exit()


def start_gui(ctrl, log=None):
    """Function to start the gui, to be imported and run elsewhere when ctrl is
    initialized Requires the `ctrl` object to be passed."""
    root = Tk()

    gui = MainFrame(root, cam=ctrl.cam, modules=MODULES)

    experiment_ctrl = DataCollectionController(ctrl=ctrl, stream=ctrl.cam, beam_ctrl=None, app=gui.app, log=log)
    experiment_ctrl.start()

    root.mainloop()


if __name__ == '__main__':
    from instamatic import TEMController
    ctrl = TEMController.initialize()
    start_gui(ctrl)
