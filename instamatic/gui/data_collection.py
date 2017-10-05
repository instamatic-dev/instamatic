import os, sys
import numpy as np
import json
from instamatic.formats import *

import time
import logging

import threading

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
        self.start_calib_directbeam = threading.Event()
        self.stop_calib_directbeam = threading.Event()
        self.start_calib_beamshift = threading.Event()
        self.stop_calib_beamshift = threading.Event()
        
        self.triggerEvent = threading.Event()
        
        self.module_io = self.stream.get_module("io")
        self.module_sed = self.stream.get_module("sed")
        self.module_cred = self.stream.get_module("cred")

        self.module_sed.set_trigger(trigger=self.triggerEvent)
        self.module_cred.set_trigger(trigger=self.triggerEvent)

        self.module_cred.set_events(startEvent=self.startEvent_cRED, 
                                    stopEvent=self.stopEvent_cRED)
        self.module_sed.set_events(startEvent=self.startEvent_SED, 
                                   stopEvent=self.stopEvent_SED,
                                   start_calib_directbeam=self.start_calib_directbeam, 
                                   stop_calib_directbeam=self.stop_calib_directbeam,
                                   start_calib_beamshift=self.start_calib_beamshift, 
                                   stop_calib_beamshift=self.stop_calib_beamshift)

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

            if self.start_calib_directbeam.is_set():
                self.start_calib_directbeam.clear()
                self.acquire_directbeam_calibration()
                print "calib directbeam"

            if self.start_calib_beamshift.is_set():
                self.start_calib_beamshift.clear()
                self.acquire_beamshift_calibration()
                print "calib beamshift"

    def acquire_data_cRED(self):
        from instamatic.experiments import cRED
        
        expdir = self.module_io.get_experiment_directory()
        workdir = self.module_io.get_working_directory()

        if not os.path.exists(expdir):
            os.makedirs(expdir)

        if not os.path.exists(workdir):
            os.makedirs(workdir)
        
        expt = self.module_cred.get_expt()

        cexp = cRED.Experiment(ctrl=self.ctrl, path=expdir, expt=expt, log=self.log, stopEvent=self.stopEvent_cRED, flatfield=self.module_io.get_flatfield())
        cexp.report_status()
        cexp.start_collection()
        
        self.stopEvent_cRED.clear()

    def acquire_beamshift_calibration(self):
        from instamatic.calibrate.calibrate_beamshift import calibrate_beamshift
        from instamatic.calibrate.filenames import CALIB_BEAMSHIFT

        workdir = self.module_io.get_working_directory()
        expdir = os.path.join(workdir, "calib")
        if not os.path.exists(expdir):
            os.mkdir(expdir)

        calib = calibrate_beamshift(ctrl=self.ctrl, outdir=expdir, confirm=False)
        fn = os.path.join(expdir, CALIB_BEAMSHIFT)
        self.module_sed.beamshift_fn = fn

        self.stop_calib_beamshift.set()
        self.module_sed.beamshift_calibration = calib

    def acquire_directbeam_calibration(self):
        from instamatic.calibrate.calibrate_directbeam import calibrate_directbeam
        from instamatic.calibrate.filenames import CALIB_DIRECTBEAM

        workdir = self.module_io.get_working_directory()
        expdir = os.path.join(workdir, "calib")
        if not os.path.exists(expdir):
            os.mkdir(expdir)

        calib = calibrate_directbeam(ctrl=self.ctrl, outdir=expdir, confirm=False)
        fn = os.path.join(expdir, CALIB_DIRECTBEAM)
        self.module_sed.directbeam_fn = fn

        self.stop_calib_directbeam.set()
        self.module_sed.directbeam_calibration = calib

    def acquire_data_SED(self):
        from instamatic.experiments import serialED

        expdir = self.module_io.get_experiment_directory()
        workdir = self.module_io.get_working_directory()

        # expdir = "C:/Users/VALUEDGATANCUSTOMER/Documents/Stef/portable/work/test1/"
        # workdir = "C:/Users/VALUEDGATANCUSTOMER/Documents/Stef/portable/work/"

        params = os.path.join(workdir, "params.json")
        params = json.load(open(params,"r"))

        scan_area = self.module_sed.get_scan_area()

        exp = serialED.Experiment(self.ctrl, params, expdir=expdir, log=self.log,
            calib_directbeam=self.module_sed.directbeam_calibration,
            calib_beamshift=self.module_sed.beamshift_calibration,
            scan_area=scan_area)
        exp.report_status()
        exp.run()

        self.stopEvent_SED.clear()

    def get_working_directory(self):
        return self.module_io.get_working_directory()

    def get_experiment_directory(self):
        return self.module_io.get_experiment_directory()


class DataCollectionGUI(VideoStream):
    """docstring for DataCollectionGUI"""
    def __init__(self):
        super(DataCollectionGUI, self).__init__()
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
        btn.pack(side="bottom", fill="both", expand="yes", padx=10, pady=10)

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

    def SaveImage(self):
        drc = self.get_directory()
        if not os.path.exists(drc):
            os.mkdir(drc)
        outfile = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ".tiff"
        outfile = os.path.join(drc, outfile)
        write_tiff(outfile, self.frame)
        print " >> Wrote file:", outfile


def main():
    from instamatic import TEMController

    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename="instamatic.log", 
                        level=logging.DEBUG)
    
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    data_collection_gui = DataCollectionGUI()
    tem_ctrl = TEMController.initialize(camera=data_collection_gui)

    experiment_ctrl = DataCollectionController(tem_ctrl, log=log)

    tem_ctrl.close()


if __name__ == '__main__':
    main()