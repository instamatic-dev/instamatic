import os, sys
import numpy as np
import json
from instamatic.formats import *

import time
import logging

import threading

import datetime

from instamatic.camera.videostream import VideoStream
from SEDframe import *
from cREDframe import *
from IOFrame import *


class DataCollectionController(object):
    """docstring for DataCollectionController"""
    def __init__(self, ctrl, log=None):
        super(DataCollectionController, self).__init__()
        self.ctrl = ctrl
        self.stream = ctrl.cam
        self.camera = ctrl.cam.name
        self.log = log

        self.stopEvent_cRED = threading.Event()
        self.startEvent_cRED = threading.Event()
        
        self.stopEvent_SED = threading.Event()
        self.startEvent_SED = threading.Event()
        
        self.triggerEvent = threading.Event()
        
        self.module_io = self.stream.get_module("io")
        self.module_sed = self.stream.get_module("sed")
        self.module_cred = self.stream.get_module("cred")

        self.module_sed.set_trigger(trigger=self.triggerEvent)
        self.module_cred.set_trigger(trigger=self.triggerEvent)

        self.module_cred.set_events(startEvent=self.startEvent_cRED, 
                                    stopEvent=self.stopEvent_cRED)
        self.module_sed.set_events(startEvent=self.startEvent_SED, 
                                   stopEvent=self.stopEvent_SED)

        self.exitEvent = threading.Event()
        self.stream._atexit_funcs.append(self.exitEvent.set)
        self.stream._atexit_funcs.append(self.triggerEvent.set)

        self.wait_for_event()

    def wait_for_event(self):
        while True:
            self.triggerEvent.wait()
            self.triggerEvent.clear()

            if self.exitEvent.is_set():
                self.ctrl.close()
                sys.exit()
            
            if self.startEvent_cRED.is_set():
                self.startEvent_cRED.clear()
                self.acquire_data_cRED()
            
            if self.startEvent_SED.is_set():
                self.startEvent_SED.clear()
                self.acquire_data_SED()

    def acquire_data_cRED(self):
        from instamatic.experiments import cRED
        
        expdir = self.module_io.get_new_experiment_directory()

        if not os.path.exists(expdir):
            os.makedirs(expdir)
        
        expt = self.module_cred.get_expt()
        unblank_beam = self.module_cred.get_unblank_beam()

        cexp = cRED.Experiment(ctrl=self.ctrl, path=expdir, expt=expt, unblank_beam=unblank_beam, 
                               log=self.log, stopEvent=self.stopEvent_cRED, 
                               flatfield=self.module_io.get_flatfield())
        cexp.report_status()
        cexp.start_collection()
        
        self.stopEvent_cRED.clear()

    def acquire_data_SED(self):
        from instamatic.experiments import serialED

        workdir = self.module_io.get_working_directory()
        expdir = self.module_io.get_new_experiment_directory()

        if not os.path.exists(expdir):
            os.makedirs(expdir)

        params = os.path.join(workdir, "params.json")
        params = json.load(open(params,"r"))
        params.update(self.module_sed.get_params())
        params["flatfield"] = self.module_io.get_flatfield()

        scan_radius = self.module_sed.get_scan_area()

        self.module_sed.calib_path = os.path.join(expdir, "calib")

        exp = serialED.Experiment(self.ctrl, params, expdir=expdir, log=self.log, 
            scan_radius=scan_radius, begin_here=True)
        exp.report_status()
        exp.run()

        self.stopEvent_SED.clear()

    def get_working_directory(self):
        return self.module_io.get_working_directory()

    def get_experiment_directory(self):
        return self.module_io.get_experiment_directory()


class DataCollectionGUI(VideoStream):
    """docstring for DataCollectionGUI"""
    def __init__(self, *args, **kwargs):
        super(DataCollectionGUI, self).__init__(*args, **kwargs)
        self.modules = {}

    def buttonbox(self, master):
        frame = LabelFrame(master, text="Experiment control")
        frame.pack(side="right", fill="both", expand="yes", padx=10, pady=10)

        self.module_io = self.module_io(frame)
        self.modules["io"] = self.module_io 
        self.module_cred = self.module_cred(frame)
        self.modules["cred"] = self.module_cred
        self.module_sed = self.module_sed(frame)
        self.modules["sed"] = self.module_sed

        btn = Button(master, text="Save image",
            command=self.saveImage)
        btn.pack(side="bottom", fill="both", padx=10, pady=10)

    def module_io(self, parent):
        module = IOFrame(parent)
        module.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
        return module

    def module_cred(self, parent):
        module = ExperimentalcRED(parent)
        module.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
        return module

    def module_sed(self, parent):
        module = ExperimentalSED(parent)
        module.pack(side="top", fill="both", expand="yes", padx=10, pady=10)
        return module

    def get_module(self, module):
        return self.modules[module]

    def saveImage(self):
        drc = self.module_io.get_experiment_directory()
        if not os.path.exists(drc):
            os.makedirs(drc)
        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        outfile = os.path.join(drc, outfile)
        write_tiff(outfile, self.frame)
        print " >> Wrote file:", outfile


def main():
    from instamatic import TEMController
    if "simulate" in sys.argv[1:]:
        cam = "simulate"
    else:
        cam = "timepix"

    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename="instamatic.log", 
                        level=logging.DEBUG)
    
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    data_collection_gui = DataCollectionGUI(cam="simulate")

    tem_ctrl = TEMController.initialize(camera=data_collection_gui)

    experiment_ctrl = DataCollectionController(tem_ctrl, log=log)

    tem_ctrl.close()


if __name__ == '__main__':
    main()