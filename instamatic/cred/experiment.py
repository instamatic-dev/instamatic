import os
import datetime
import logging
from Tkinter import *
import numpy as np
import glob
import time
import ImgConversion
from instamatic.TEMController import config


class Experiment(object):
    def __init__(self, ctrl, expt, stopEvent, path=None, log=None, flatfield=None):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = path
        self.expt = expt
        self.logger = log
        self.camtype = ctrl.cam.name
        self.stopEvent = stopEvent
        self.flatfield = flatfield
        
    def report_status(self):
        self.image_binsize = self.ctrl.cam.default_binsize
        self.magnification = self.ctrl.magnification.value
        self.image_spotsize = self.ctrl.spotsize
        
        self.diff_binsize = self.image_binsize
        self.diff_exposure = self.expt
        self.diff_brightness = self.ctrl.brightness.value
        self.diff_spotsize = self.image_spotsize
        print ("Output directory:\n{}".format(self.path))
        print "Imaging     : binsize = {}".format(self.image_binsize)
        print "              exposure = {}".format(self.expt)
        print "              magnification = {}".format(self.magnification)
        print "              spotsize = {}".format(self.image_spotsize)
        print "Diffraction : binsize = {}".format(self.diff_binsize)
        print "              exposure = {}".format(self.diff_exposure)
        print "              brightness = {}".format(self.diff_brightness)
        print "              spotsize = {}".format(self.diff_spotsize)        
        
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
        
        camera_length = int(self.ctrl.magnification.get())

        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collection spot size: {}".format(self.ctrl.spotsize))
        
        buffer = []
        if self.camtype != "simulate":
            while abs(a - a0) < 0.5:
                a = self.ctrl.stageposition.a
                if abs(a - a0) > 0.5:
                    break
            print "Data Recording started."
            self.startangle = a
            
            self.ctrl.cam.block()
            t0 = time.time()
            while not self.stopEvent.is_set():
                img, h = self.ctrl.getImage(self.expt, header_keys=None)
                buffer.append((img, h))

            t1 = time.time()

            self.ctrl.cam.unblock()
            self.endangle = self.ctrl.stageposition.a
                
        else:
            self.startangle = a
            camera_length = 300

            self.ctrl.cam.block()
            t0 = time.time()
            while not self.stopEvent.is_set():
                img, h = self.ctrl.getImage(self.expt, header_keys=None)
                buffer.append((img, h))
                
                print("Generating random images... {}".format(img.mean()))

            t1 = time.time()

            self.ctrl.cam.unblock()
            self.endangle = self.startangle + np.random.random()*50


        pxd = config.diffraction_pixeldimensions

        nframes = len(buffer)
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

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
                 flatfield=self.flatfield)
        
        img_conv.writeTiff(self.pathtiff)
        img_conv.writeIMG(self.pathsmv)
        img_conv.ED3DCreator(self.pathred, rotation_angle)
        img_conv.MRCCreator(self.pathred)
        img_conv.XDSINPCreator(self.pathsmv, rotation_angle)
        self.logger.info("XDS INP file created as usual.")

        print "Data Collection and Conversion Done."
