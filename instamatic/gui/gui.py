from tkinter import *
from tkinter.ttk import *

import os, sys
import traceback
from instamatic.formats import *

import time
import logging

import threading
import queue

import datetime

from instamatic.camera.videostream import VideoStream
from .modules import MODULES

job_dict = {}


class DataCollectionController(object):
    """docstring for DataCollectionController"""
    def __init__(self, tem_ctrl=None, stream=None, beam_ctrl=None, log=None):
        super(DataCollectionController, self).__init__()
        self.ctrl = tem_ctrl
        self.stream = stream
        self.beam_ctrl = beam_ctrl

        self.log = log

        self.q = queue.LifoQueue(maxsize=1)
        self.triggerEvent = threading.Event()
        
        self.module_io = self.stream.get_module("io")

        for name, module in self.stream.modules.items():
            try:
                module.set_trigger(trigger=self.triggerEvent, q=self.q)
            except AttributeError:
                pass  # module does not need/accept a trigger
        
        self.exitEvent = threading.Event()
        self.stream._atexit_funcs.append(self.exitEvent.set)
        self.stream._atexit_funcs.append(self.triggerEvent.set)

        self.wait_for_event()

    def wait_for_event(self):
        while True:
            self.triggerEvent.wait()
            self.triggerEvent.clear()

            if self.exitEvent.is_set():
                self.ctrl.close()  # TODO: make part of atexit?
                sys.exit()

            job, kwargs = self.q.get()

            try:
                func = job_dict[job]
            except KeyError:
                print("Unknown job: {}".format(job))
                print("Kwargs:\n{}".format(kwargs))
                continue

            try:
                func(self, **kwargs)
            except Exception as e:
                traceback.print_exc()
                self.log.debug("Error caught -> {} while running '{}' with {}".format(repr(e), job, kwargs))
                self.log.exception(e)


class DataCollectionGUI(VideoStream):
    """docstring for DataCollectionGUI"""
    def __init__(self, *args, **kwargs):
        super(DataCollectionGUI, self).__init__(*args, **kwargs)
        self.modules = {}
        self._modules_have_loaded = False

    def load_modules(self, master):
        frame = Frame(master)
        frame.pack(side="right", fill="both", expand="yes")

        make_notebook = any(module.tabbed for module in MODULES)
        if make_notebook:
            self.nb = Notebook(frame, padding=10)

        for module in MODULES:
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

    def saveImage(self):
        module_io = self.get_module("io")

        drc = module_io.get_experiment_directory()
        drc.mkdir(exist_ok=True, parents=True)

        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        outfile = drc / outfile

        try:
            from instamatic.processing.flatfield import apply_flatfield_correction
            flatfield, h = read_tiff(module_io.get_flatfield())
            frame = apply_flatfield_correction(self.frame, flatfield)
        except:
            frame = self.frame
        write_tiff(outfile, frame)
        print(" >> Wrote file:", outfile)


def main():
    from instamatic.utils import high_precision_timers
    high_precision_timers.enable()  # sleep timers with 1 ms resolution
    
    # enable faster switching between threads
    sys.setswitchinterval(0.001)  # seconds

    from instamatic import config

    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_{date}.log"

    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)

    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    log.info("Instamatic.gui started")
    
    from instamatic import TEMController

    # Work-around for race condition (errors) that occurs when 
    # DataCollectionController tries to access them

    tem_ctrl = TEMController.initialize(camera=DataCollectionGUI)
    
    while not tem_ctrl.cam._modules_have_loaded:
        time.sleep(0.1)

    experiment_ctrl = DataCollectionController(tem_ctrl=tem_ctrl, stream=tem_ctrl.cam, beam_ctrl=None, log=log)

    tem_ctrl.close()


if __name__ == '__main__':
    main()