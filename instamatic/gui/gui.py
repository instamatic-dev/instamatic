from tkinter import *
from tkinter.ttk import *

from instamatic.formats import *
import atexit
import queue
import sys
import threading
import traceback

from .modules import MODULES

job_dict = {}


class DataCollectionController(threading.Thread):
    """docstring for DataCollectionController"""

    def __init__(self, ctrl=None, stream=None, beam_ctrl=None, app=None, log=None):
        super(DataCollectionController, self).__init__()
        self.ctrl = ctrl
        self.stream = stream
        self.beam_ctrl = beam_ctrl
        self.app = app
        self.daemon = True

        self.use_indexing_server = False

        self.log = log

        self.q = queue.LifoQueue(maxsize=1)
        self.triggerEvent = threading.Event()

        self.module_io = self.app.get_module("io")

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
                func = job_dict[job]
            except KeyError:
                print(f"Unknown job: {job}")
                print(f"Kwargs:\n{kwargs}")
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


class ModuleFrame(Frame):
    """docstring for DataCollectionGUI"""

    def __init__(self, parent, modules=()):
        super().__init__()
        # super(DataCollectionGUI, self).__init__(cam=cam)
        self._modules = modules
        self._modules_have_loaded = False
        self.modules = {}

        self.parent = parent

        self.load_modules(parent)

    def load_modules(self, master):
        frame = Frame(master)
        frame.pack(side="right", fill="both", expand="yes")

        make_notebook = any(module.tabbed for module in self._modules)
        if make_notebook:
            self.nb = Notebook(frame, padding=10)

        for module in self._modules:
            if module.tabbed:
                page = Frame(self.nb)
                module_frame = module.tk_frame(page)
                module_frame.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
                self.modules[module.name] = module_frame
                self.nb.add(page, text=module.display_name)
            else:
                module_frame = module.tk_frame(frame)
                module_frame.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
                self.modules[module.name] = module_frame
            job_dict.update(module.commands)

        if make_notebook:
            self.nb.pack(fill="both", expand="yes")

        self._modules_have_loaded = True

    def get_module(self, module):
        return self.modules[module]


class MainFrame(object):
    """docstring for MainFrame"""

    def __init__(self, root, cam, modules=()):
        super(MainFrame, self).__init__()

        self.root = root

        self.app = ModuleFrame(root, modules=modules)
        self.app.pack(side="top", fill="both", expand=True)

        if cam and cam.streamable:
            from .videostream_frame import VideoStreamFrame

            self.stream_frame = VideoStreamFrame(root, stream=cam, app=self.app)
            self.stream_frame.pack(side="top", fill="both", expand=True)

        from instamatic import version

        self.root.wm_title(version.__long_title__)
        self.root.wm_protocol("WM_DELETE_WINDOW", self.close)

        self.root.bind('<Escape>', self.close)

    def close(self):
        try:
            self.stream_frame.close()
        except AttributeError:
            pass
        sys.exit()


def start_gui(ctrl, log=None):
    """Function to start the gui, to be imported and run elsewhere when ctrl is initialized
    Requires the `ctrl` object to be passed.
    """
    root = Tk()

    gui = MainFrame(root, cam=ctrl.cam, modules=MODULES)

    experiment_ctrl = DataCollectionController(ctrl=ctrl, stream=ctrl.cam, beam_ctrl=None, app=gui.app, log=log)
    experiment_ctrl.start()

    root.mainloop()


if __name__ == '__main__':
    main()
