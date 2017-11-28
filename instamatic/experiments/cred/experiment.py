import os
import datetime
import logging
from Tkinter import *
import numpy as np
import glob
import time
import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff

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

    def report_status(self):
        self.diff_binsize = self.ctrl.cam.default_binsize
        self.diff_exposure = self.expt
        self.diff_brightness = self.ctrl.brightness.value
        self.diff_spotsize = self.ctrl.spotsize

        print "\nOutput directory: {}".format(self.path)
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
        spotsize = self.ctrl.spotsize
        
        self.pathtiff = os.path.join(self.path, "tiff")
        self.pathsmv = os.path.join(self.path, "SMV")
        self.pathmrc = os.path.join(self.path, "RED")
              
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection spot size: {}".format(spotsize))
        
        # TODO: Mostly above is setup, split off into own function

        buffer = []
        image_buffer = []

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
        
        diff_focus_proper = self.ctrl.difffocus.value
        diff_focus_defocused = self.diff_defocus

        i = 1

        self.ctrl.cam.block()

        t0 = time.time()

        while not self.stopEvent.is_set():
            if i % self.image_interval == 0:
                t_start = time.time()
                acquisition_time = (t_start - t0) / (i-1)

                self.ctrl.difffocus.value = diff_focus_defocused
                img, h = self.ctrl.getImage(self.expt / 5.0, header_keys=None)
                self.ctrl.difffocus.value = diff_focus_proper

                image_buffer.append((i, img, h))

                next_interval = t_start + acquisition_time
                # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)

                while time.time() > next_interval:
                    next_interval += acquisition_time
                    i += 1
                    # print i, "SKIP!  {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time)

                while time.time() < next_interval:
                    time.sleep(0.001)

            else:
                img, h = self.ctrl.getImage(self.expt, header_keys=None)
                # print i, "Image!"
                buffer.append((i, img, h))

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

        # TODO: all the rest here is io+logistics, split off in to own function

        nframes = i + 1 # len(buffer) can lie in case of frame skipping
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes
        print "\nRotated {:.2f} degrees from {:.2f} to {:.2f} in {} frames (step: {:.2f})".format(abs(self.endangle-self.startangle), self.startangle, self.endangle, nframes, osangle)

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Rotated {:.2f} degrees from {:.2f} to {:.2f} in {} frames (step: {:.4f})".format(abs(self.endangle-self.startangle), self.startangle, self.endangle, nframes, osangle))
        
        with open(os.path.join(self.path, "cRED_log.txt"), "w") as f:
            f.write("Data Collection Time: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("Starting angle: {:.2f}\n".format(self.startangle))
            f.write("Ending angle: {:.2f}\n".format(self.endangle))
            f.write("Rotation range: {:.2f}\n".format(self.endangle-self.startangle))
            f.write("Exposure Time: {} s\n".format(self.expt))
            f.write("Spot Size: {}\n".format(spotsize))
            f.write("Camera length: {} mm\n".format(camera_length))
            f.write("Oscillation angle: {:.4f} degrees\n".format(osangle))
            f.write("Number of frames: {}\n".format(len(buffer)))

        if nframes <= 3:
            self.logger.info("Not enough frames collected. Data will not be written (nframes={}).".format(nframes))
            print "Data collection done. Not enough frames collected (nframes={}).".format(nframes)
            return

        rotation_angle = config.microscope.camera_rotation_vs_stage_xy

        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=camera_length,
                 osangle=osangle,
                 startangle=self.startangle,
                 endangle=self.endangle,
                 rotation_angle=rotation_angle,
                 acquisition_time=acquisition_time,
                 resolution_range=(20, 0.8),
                 flatfield=self.flatfield)
        

        print "Writing files..."

        img_conv.threadpoolwriter(tiff_path=self.pathtiff,
                                  mrc_path=self.pathmrc,
                                  smv_path=self.pathsmv,
                                  workers=8)
        
        # img_conv.tiff_writer(self.pathtiff)
        # img_conv.smv_writer(self.pathsmv)
        # img_conv.mrc_writer(self.pathmrc)

        img_conv.write_ed3d(self.pathmrc)
        img_conv.write_xds_inp(self.pathsmv)

        if image_buffer:
            drc = os.path.join(self.path, "tiff_image")
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, "{:05d}.tiff".format(i))
                write_tiff(fn, img, header=h)

        print "Data Collection and Conversion Done."
