import os
import datetime
import logging
from Tkinter import *
import numpy as np
import glob
import time
import ImgConversion
from instamatic.TEMController import config

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2


class Experiment(object):
    def __init__(self, ctrl, expt, stopEvent, unblank_beam=False, path=None, log=None, flatfield=None):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = path
        self.expt = expt
        self.unblank_beam = unblank_beam
        self.logger = log
        self.camtype = ctrl.cam.name
        self.stopEvent = stopEvent
        self.flatfield = flatfield

        self.diff_defocus = 0
        self.image_interval = 99999

        self.excludes = []
        
    def report_status(self):
        self.image_binsize = self.ctrl.cam.default_binsize
        self.magnification = self.ctrl.magnification.value
        self.image_spotsize = self.ctrl.spotsize
        
        self.diff_binsize = self.image_binsize
        self.diff_exposure = self.expt
        self.diff_brightness = self.ctrl.brightness.value
        self.diff_spotsize = self.image_spotsize
        print "Output directory:\n{}".format(self.path)
        print "Imaging     : binsize = {}".format(self.image_binsize)
        print "              exposure = {}".format(self.expt)
        print "              magnification = {}".format(self.magnification)
        print "              spotsize = {}".format(self.image_spotsize)
        print "Diffraction : binsize = {}".format(self.diff_binsize)
        print "              exposure = {}".format(self.diff_exposure)
        print "              brightness = {}".format(self.diff_brightness)
        print "              spotsize = {}".format(self.diff_spotsize)        
    
    def enable_image_interval(self, interval, defocus):
        self.diff_defocus = defocus
        self.image_interval = interval
        print "Image interval enabled: every {} frames an image with defocus value {} will be displayed.".format(interval, defocus)

    def start_collection(self):
        a = a0 = self.ctrl.stageposition.a
        
        self.pathtiff = os.path.join(self.path,"tiff")
        self.pathsmv = os.path.join(self.path,"SMV")
        self.pathred = os.path.join(self.path,"RED")
        
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        if not os.path.exists(self.pathtiff):
            os.makedirs(self.pathtiff)
        if not os.path.exists(self.pathsmv):
            os.makedirs(self.pathsmv)
        if not os.path.exists(self.pathred):
            os.makedirs(self.pathred)
        
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection spot size: {}".format(self.ctrl.spotsize))
        
        buffer = []
        if self.camtype == "simulate":
            self.startangle = a
        else:
            while abs(a - a0) < ACTIVATION_THRESHOLD:
                a = self.ctrl.stageposition.a
                if abs(a - a0) > ACTIVATION_THRESHOLD:
                    break
            print "Data Recording started."
            self.startangle = a

        if self.unblank_beam:
            print "Unblanking beam"
            self.ctrl.beamblank = False
        
        self.ctrl.cam.block()
        t0 = time.time()

        i = 1

        diff_focus_proper = self.ctrl.difffocus.value
        diff_focus_defocused = self.diff_defocus

        while not self.stopEvent.is_set():

            if i % self.image_interval == 0:
                t_start = time.time()
                acquisition_time = (t_start - t0) / len(buffer)

                self.ctrl.difffocus.value = diff_focus_defocused
                img, h = self.ctrl.getImage(self.expt / 5.0, header_keys=None)
                # print i, "BLOOP!"
                self.ctrl.difffocus.value = diff_focus_proper

                self.excludes.append(i-1)

                while True:
                    dt = time.time() - t_start
                    # print "Waiting while {:.2f} < {:.2f}".format(dt, acquisition_time)
                    if dt >= acquisition_time:
                        break
                    time.sleep(0.001)

            else:
                img, h = self.ctrl.getImage(self.expt, header_keys=None)
                # print i, "Image!"
            
            buffer.append((img, h))

            i += 1

        t1 = time.time()

        self.ctrl.cam.unblock()

        if self.camtype == "simulate":
            self.endangle = self.startangle + np.random.random()*50
            camera_length = 300
        else:
            self.endangle = self.ctrl.stageposition.a
            camera_length = int(self.ctrl.magnification.get())

        if self.unblank_beam:
            print "Blanking beam"
            self.ctrl.beamblank = True

        print "Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle)
        nframes = len(buffer)
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collected from {} degree to {} degree.".format(self.startangle, self.endangle))
        self.logger.info("Oscillation angle: {}".format(osangle))
        self.logger.info("Pixel size and actual camera length updated in SMV file headers for DIALS processing.")
        
        rotation_angle = config.camera_rotation_vs_stage_xy

        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=camera_length,
                 osangle=osangle,
                 startangle=self.startangle,
                 endangle=self.endangle,
                 rotation_angle=rotation_angle,
                 acquisition_time=acquisition_time,
                 resolution_range=(20, 0.8),
                 excludes=self.excludes,
                 flatfield=self.flatfield)
        
        img_conv.writeTiff(self.pathtiff)
        img_conv.writeIMG(self.pathsmv)
        img_conv.ED3DCreator(self.pathred)
        img_conv.MRCCreator(self.pathred)
        img_conv.XDSINPCreator(self.pathsmv)
        self.logger.info("XDS INP file created.")

        with open(os.path.join(self.path, "cRED_log.txt"), "w") as f:
            f.write("Data Collection Time: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("Starting angle: {}\n".format(self.startangle))
            f.write("Ending angle: {}\n".format(self.endangle))
            f.write("Exposure Time: {} s\n".format(self.expt))
            f.write("Spot Size: {}\n".format(self.ctrl.spotsize))
            f.write("Camera length: {} mm\n".format(camera_length))

        print "Data Collection and Conversion Done."
