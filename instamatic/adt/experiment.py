import os
import datetime
import logging
import numpy as np
import glob
import time
from instamatic.TEMController import config
from instamatic.formats import write_hdf5
import tqdm


class Experiment(object):
    def __init__(self, ctrl, path=None, log=None, flatfield=None):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = path
        self.logger = log
        self.camtype = ctrl.cam.name
        self.flatfield = flatfield
        self.offset = 0
        self.current_angle = None
        
    def start_collection(self, expt, tilt_range, stepsize):
        path = self.path

        if not os.path.exists(path):
            os.makedirs(path)
        
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(path))
        self.logger.info("Data collection exposure time: {} s".format(expt))
        self.logger.info("Data collection spot size: {}".format(self.ctrl.spotsize))
        self.logger.info("Data collection spot size: {}".format(tilt_range))
        self.logger.info("Data collection spot size: {}".format(stepsize))

        ctrl = self.ctrl

        if not self.current_angle:
            startangle = ctrl.stageposition.a
        else:
            startangle = self.current_angle + stepsize

        tilt_positions = np.arange(startangle, startangle+tilt_range, stepsize)
        print "Startangle", startangle
        print "Angles:", tilt_positions

        ctrl.cam.block()
        # for i, a in enumerate(tilt_positions):
        for i, angle in enumerate(tqdm.tqdm(tilt_positions)):
            ctrl.stageposition.a = angle

            j = i + self.offset

            img, h = self.ctrl.getImage(expt)

            fn = os.path.join(path, "{:05d}.h5".format(j))

            write_hdf5(fn, img, header=h)
            # print fn

        self.offset += len(tilt_positions)

        endangle = ctrl.stageposition.a

        ctrl.cam.unblock()

        camera_length = int(self.ctrl.magnification.get())
    
        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collected from {} degree to {} degree.".format(startangle, endangle))
        
        self.current_angle = angle
        print "Current angle", self.current_angle
        print "Data Collection Done\n"

    def finalize(self):
        print "ADT data collection finalized"
