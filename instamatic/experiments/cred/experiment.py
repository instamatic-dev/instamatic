import os
import datetime
from tkinter import *
import numpy as np
import time
from . import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from .timer import wait

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2


class Experiment(object):
    def __init__(self, ctrl, 
        path=None, 
        log=None, 
        flatfield=None,
        exposure_time=0.5,
        unblank_beam=False,
        enable_image_interval=False,
        image_interval=99999,
        diff_defocus=0,
        exposure_time_image=0.01,
        write_tiff=True,
        write_xds=True,
        write_dials=True,
        write_red=True,
        stop_event=None,
        ):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = path
        self.expt = exposure_time
        self.unblank_beam = unblank_beam
        self.logger = log
        self.camtype = ctrl.cam.name
        self.stopEvent = stop_event
        self.flatfield = flatfield

        self.image_interval_enabled = enable_image_interval
        self.image_interval = image_interval
        self.diff_defocus = diff_defocus
        self.expt_image = exposure_time_image

        self.write_tiff = write_tiff
        self.write_xds = write_xds
        self.write_dials = write_dials
        self.write_red = write_red

        if enable_image_interval:
            msg = f"Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.expt_image} s)."
            print(msg)
            self.logger.info(msg)

    def report_status(self):
        self.diff_binsize = self.ctrl.cam.default_binsize
        self.diff_exposure = self.expt
        self.diff_brightness = self.ctrl.brightness.value
        self.diff_spotsize = self.ctrl.spotsize

        print("\nOutput directory: {}".format(self.path))
        print("Diffraction : binsize = {}".format(self.diff_binsize))
        print("              exposure = {}".format(self.diff_exposure))
        print("              brightness = {}".format(self.diff_brightness))
        print("              spotsize = {}".format(self.diff_spotsize))        

    def start_collection(self):
        a = a0 = self.ctrl.stageposition.a
        spotsize = self.ctrl.spotsize
        
        self.tiff_path = os.path.join(self.path, "tiff") if self.write_tiff else None
        self.smv_path = os.path.join(self.path, "SMV") if (self.write_xds or self.write_dials) else None
        self.mrc_path = os.path.join(self.path, "RED") if self.write_red else None
              
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection spot size: {}".format(spotsize))
        
        # TODO: Mostly above is setup, split off into own function

        buffer = []
        image_buffer = []

        if self.ctrl.mode != 'diff':
            self.ctrl.mode = 'diff'

        if self.camtype == "simulate":
            self.start_angle = a
        else:
            while abs(a - a0) < ACTIVATION_THRESHOLD:
                a = self.ctrl.stageposition.a
                if abs(a - a0) > ACTIVATION_THRESHOLD:
                    break
            print("Data Recording started.")
            self.start_angle = a

        if self.unblank_beam:
            print("Unblanking beam")
            self.ctrl.beamblank = False
        
        diff_focus_proper = self.ctrl.difffocus.value
        diff_focus_defocused = self.diff_defocus + diff_focus_proper
        image_interval = self.image_interval
        expt_image = self.expt_image

        i = 1

        self.ctrl.cam.block()

        t0 = time.clock()

        while not self.stopEvent.is_set():
            if i % self.image_interval == 0:
                t_start = time.clock()
                acquisition_time = (t_start - t0) / (i-1)

                self.ctrl.difffocus.value = diff_focus_defocused
                img, h = self.ctrl.getImage(expt_image, header_keys=None)
                self.ctrl.difffocus.value = diff_focus_proper

                image_buffer.append((i, img, h))

                next_interval = t_start + acquisition_time
                # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)

                while time.clock() > next_interval:
                    next_interval += acquisition_time
                    i += 1
                    # print i, "SKIP!  {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time)

                diff = next_interval - time.clock() # seconds
                wait(int(diff * 1000))              # milliseconds

            else:
                img, h = self.ctrl.getImage(self.expt, header_keys=None)
                # print i, "Image!"
                buffer.append((i, img, h))

            i += 1

        t1 = time.clock()

        self.ctrl.cam.unblock()

        if self.camtype == "simulate":
            self.end_angle = self.start_angle + np.random.random()*50
            camera_length = 300
        else:
            self.end_angle = self.ctrl.stageposition.a
            camera_length = int(self.ctrl.magnification.get())

        if self.unblank_beam:
            print("Blanking beam")
            self.ctrl.beamblank = True

        # in case something went wrong starting data collection, return gracefully
        if i == 1:
            return

        # TODO: all the rest here is io+logistics, split off in to own function

        nframes = i-1 # len(buffer) can lie in case of frame skipping
        osc_angle = abs(self.end_angle - self.start_angle) / nframes
        total_time = t1 - t0
        acquisition_time = total_time / nframes
        print("\nRotated {:.2f} degrees from {:.2f} to {:.2f} in {} frames (step: {:.2f})".format(abs(self.end_angle-self.start_angle), self.start_angle, self.end_angle, nframes, osc_angle))

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Rotated {:.2f} degrees from {:.2f} to {:.2f} in {} frames (step: {:.4f})".format(abs(self.end_angle-self.start_angle), self.start_angle, self.end_angle, nframes, osc_angle))
        
        with open(os.path.join(self.path, "cRED_log.txt"), "w") as f:
            f.write("Data Collection Time: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("Starting angle: {:.2f} degrees\n".format(self.start_angle))
            f.write("Ending angle: {:.2f} degrees\n".format(self.end_angle))
            f.write("Rotation range: {:.2f} degrees\n".format(self.end_angle-self.start_angle))
            f.write("Exposure Time: {:.3f} s\n".format(self.expt))
            f.write("Acquisition time: {:.3f} s\n".format(acquisition_time))
            f.write("Total time: {:.3f} s\n".format(total_time))
            f.write("Spot Size: {}\n".format(spotsize))
            f.write("Camera length: {} mm\n".format(camera_length))
            f.write("Oscillation angle: {:.4f} degrees\n".format(osc_angle))
            f.write("Number of frames: {}\n".format(len(buffer)))

            if self.image_interval_enabled:
                f.write("Image interval: every {} frames an image with defocus {} (t={} s).\n".format(image_interval, diff_focus_defocused, expt_image))
                f.write("Number of images: {}\n".format(len(image_buffer)))

        if nframes <= 3:
            self.logger.info("Not enough frames collected. Data will not be written (nframes={}).".format(nframes))
            print("Data collection done. Not enough frames collected (nframes={}).".format(nframes))
            return

        rotation_axis = config.microscope.camera_rotation_vs_stage_xy

        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=camera_length,
                 osc_angle=osc_angle,
                 start_angle=self.start_angle,
                 end_angle=self.end_angle,
                 rotation_axis=rotation_axis,
                 acquisition_time=acquisition_time,
                 resolution_range=(20, 0.8),
                 flatfield=self.flatfield)
        
        print("Writing files...")

        img_conv.threadpoolwriter(tiff_path=self.tiff_path,
                                  mrc_path=self.mrc_path,
                                  smv_path=self.smv_path,
                                  workers=8)
        
        if self.write_dials:
            print("Writing files for DIALS")
            img_conv.to_dials(self.smv_path)

        if self.write_red:
            img_conv.write_ed3d(self.mrc_path)
        if self.write_xds or self.write_dials:
            img_conv.write_xds_inp(self.smv_path)

        if image_buffer:
            drc = os.path.join(self.path, "tiff_image")
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, "{:05d}.tiff".format(i))
                write_tiff(fn, img, header=h)

        print("Data Collection and Conversion Done.")
        self.stopEvent.clear()
