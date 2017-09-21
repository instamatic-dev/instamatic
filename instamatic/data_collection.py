import os, sys
import numpy as np
import json
from formats import *

import time
import logging

import threading


class GUI(object):
    """docstring for GUI"""
    def __init__(self, ctrl, log=None):
        super(GUI, self).__init__()
        self.ctrl = ctrl
        self.camera = ctrl.cam.name
        self.log = log

        self.stopEvent_cRED = threading.Event()
        self.startEvent_cRED = threading.Event()
        
        self.stopEvent_SED = threading.Event()
        self.startEvent_SED = threading.Event()
        self.exitEvent = threading.Event()

        self.triggerEvent = threading.Event()

        self.ctrl.cam.set_cred_events(startEvent=self.startEvent_cRED, 
                                      stopEvent=self.stopEvent_cRED,
                                      exitEvent=self.exitEvent)

        self.ctrl.cam.set_sed_events(startEvent=self.startEvent_SED, 
                                      stopEvent=self.stopEvent_SED,
                                      exitEvent=self.exitEvent)

        self.ctrl.cam.set_trigger(trigger=self.triggerEvent)


        self.wait_for_event()


    def wait_for_event(self):
        while True:
            self.triggerEvent.wait()
            self.triggerEvent.clear()

            if self.exitEvent.is_set():
                print "exiting..."
                self.ctrl.close()
                sys.exit()
            
            if self.startEvent_cRED.is_set():
                self.startEvent_cRED.clear()
                self.acquire_data_cRED()
            
            if self.startEvent_SED.is_set():
                self.startEvent_SED.clear()
                self.acquire_data_SED()

    def acquire_data_cRED(self):
        i = 0
        while not self.stopEvent_cRED.is_set():
            img = self.ctrl.cam.getImage()
            print i, img.shape
            i += 1
        self.stopEvent_cRED.clear()

    def acquire_data_SED(self):
        from experiment import Experiment

        expdir = self.get_experiment_directory()
        workdir = self.get_working_directory()

        # expdir = "C:/Users/VALUEDGATANCUSTOMER/Documents/Stef/portable/work/test1/"
        # workdir = "C:/Users/VALUEDGATANCUSTOMER/Documents/Stef/portable/work/"

        params = os.path.join(workdir, "params.json")
        params = json.load(open(params,"r"))

        exp = Experiment(self.ctrl, params, expdir=expdir, log=self.log)
        exp.report_status()
        exp.run()

        self.stopEvent_SED.clear()

    def get_working_directory(self):
        return self.ctrl.cam.get_working_directory()

    def get_experiment_directory(self):
        return self.ctrl.cam.get_experiment_directory()

def main():
    import TEMController

    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename="instamatic.log", 
                        level=logging.DEBUG)
    
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    ctrl = TEMController.initialize()

    gui = GUI(ctrl, log=log)

    ctrl.close()


if __name__ == '__main__':
    main()