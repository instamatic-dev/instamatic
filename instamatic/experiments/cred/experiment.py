import os
import datetime
from tkinter import *
import numpy as np
import time
from instamatic.processing import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from pathlib import Path

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2


def print_and_log(msg, logger=None):
    print(msg)
    if logger:
        logger.info(msg)


class Experiment(object):
    """mode: str, 'simulate', 'footfree', None (default)"""
    def __init__(self, ctrl, 
        path=None, 
        log=None, 
        flatfield=None,
        exposure_time=0.5,
        unblank_beam=False,
        mode=None,
        footfree_rotate_to=60.0,
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
        self.path = Path(path)
        self.exposure = exposure_time
        self.unblank_beam = unblank_beam
        self.logger = log
        self.mode = mode
        if ctrl.cam.name == "simulate":
            self.mode = "simulate"
        self.stopEvent = stop_event
        self.flatfield = flatfield

        self.footfree_rotate_to = footfree_rotate_to

        self.diff_defocus = diff_defocus
        self.exposure_image = exposure_time_image

        self.write_tiff = write_tiff
        self.write_xds = write_xds
        self.write_dials = write_dials
        self.write_red = write_red
        self.write_pets = write_tiff  # TODO

        self.image_interval_enabled = enable_image_interval
        if enable_image_interval:
            self.image_interval = image_interval
            print_and_log(f"Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.exposure_image} s).", logger=self.logger)
        else:
            self.image_interval = 99999

        self.relax_beam_before_experiment = self.image_interval_enabled and config.cfg.cred_relax_beam_before_experiment

        self.track_stage_position = config.cfg.cred_track_stage_positions
        self.stage_positions = []

    def log_start_status(self):
        self.now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.info(f"Data recording started at: {self.now}")
        self.logger.info(f"Data collection exposure time: {self.exposure} s")
        self.logger.info(f"Data saving path: {self.path}")

    def log_end_status(self):
        start_xy = np.array(self.start_position[0:2])
        end_xy = np.array(self.end_position[0:2])

        print_and_log(f"Rotated {self.total_angle:.2f} degrees from {self.start_angle:.2f} to {self.end_angle:.2f} in {self.nframes} frames (step: {self.osc_angle:.4f})", logger=self.logger)
        fmt = lambda arr: f"[{arr[0]:.0f} {arr[1]:.0f}]"
        print_and_log(f"Stage moved from {fmt(start_xy)} to {fmt(end_xy)}, drift: {fmt(start_xy - end_xy)}", logger=self.logger)
        self.logger.info(f"Start stage position: {self.start_position}")
        self.logger.info(f"End stage position: {self.end_position}")
        self.logger.info(f"Data collection camera length: {self.camera_length} mm")
        self.logger.info(f"Data collection spot size: {self.spotsize}")

        self.logger.info(self.stage_positions)

        with open(self.path / "cRED_log.txt", "w") as f:
            print(f"Data Collection Time: {self.now}", file=f)
            print(f"Starting angle: {self.start_angle:.2f} degrees", file=f)
            print(f"Ending angle: {self.end_angle:.2f} degrees", file=f)
            print(f"Rotation range: {self.end_angle-self.start_angle:.2f} degrees", file=f)
            print(f"Exposure Time: {self.exposure:.3f} s", file=f)
            print(f"Acquisition time: {self.acquisition_time:.3f} s", file=f)
            print(f"Total time: {self.total_time:.3f} s", file=f)
            print(f"Spot Size: {self.spotsize}", file=f)
            print(f"Camera length: {self.camera_length} mm", file=f)
            print(f"Rotation axis: {self.rotation_axis} radians", file=f)
            print(f"Oscillation angle: {self.osc_angle:.4f} degrees", file=f)
            print(f"Number of frames: {self.nframes_diff}", file=f)
            print("Stage start: X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:5.2f} | B {:5.2f}".format(*self.start_position), file=f)
            print("Stage end:   X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:5.2f} | B {:5.2f}".format(*self.end_position), file=f)

            if self.image_interval_enabled:
                print(f"Image interval: every {self.image_interval} frames an image with defocus {self.diff_focus_defocused} (t={self.exposure_image} s).", file=f)
                print(f"Number of images: {self.nframes_image}", file=f)

    def setup_paths(self):
        print(f"\nOutput directory: {self.path}")
        self.tiff_path = self.path / "tiff" if self.write_tiff else None
        self.smv_path  = self.path / "SMV"  if (self.write_xds or self.write_dials) else None
        self.mrc_path  = self.path / "RED"  if self.write_red else None

    def start_rotation(self):
        self.start_position = self.ctrl.stageposition.get()
        self.stage_positions.append((0, self.start_position))
        a = self.start_position[3]

        if self.mode == "simulate":
            start_angle = a
            print("Data Recording started.")
        
        elif self.mode == "footfree":
            rotate_to = self.footfree_rotate_to

            start_angle = self.ctrl.stageposition.a
            self.ctrl.stageposition.set(a=rotate_to, wait=False)
        
        else:
            print("Waiting for rotation to start...", end=' ')
            a0 = a
            while abs(a - a0) < ACTIVATION_THRESHOLD:
                if self.stopEvent.is_set():
                    break
                
                a = self.ctrl.stageposition.a

            print("Data Recording started.")
            start_angle = a

        if self.unblank_beam:
            print("Unblanking beam")
            self.ctrl.beamblank = False        

        return start_angle

    def relax_beam(self, n_cycles=5):
        print(f"Relaxing beam ({n_cycles} cycles)", end='')

        for i in range(n_cycles):
            self.ctrl.difffocus.set(self.diff_focus_defocused)
            time.sleep(0.5)
            print(f".", end='')
            self.ctrl.difffocus.set(self.diff_focus_proper)
            time.sleep(0.5)
            print(f".", end='')

        print("Done.")

    def start_collection(self):
        self.setup_paths()
        self.log_start_status()
        
        buffer = []
        image_buffer = []

        if self.ctrl.mode != 'diff':
            self.ctrl.mode = 'diff'

        self.diff_focus_proper = self.ctrl.difffocus.value
        self.diff_focus_defocused = self.diff_defocus + self.diff_focus_proper
        exposure_image = self.exposure_image

        if self.relax_beam_before_experiment:
            self.relax_beam()

        self.start_angle = self.start_rotation()
        self.ctrl.cam.block()

        i = 1

        t0 = time.clock()

        while not self.stopEvent.is_set():
            if i % self.image_interval == 0:
                t_start = time.clock()
                acquisition_time = (t_start - t0) / (i-1)

                self.ctrl.difffocus.set(self.diff_focus_defocused, confirm_mode=False)
                img, h = self.ctrl.getImage(exposure_image, header_keys=None)
                self.ctrl.difffocus.set(self.diff_focus_proper, confirm_mode=False)

                image_buffer.append((i, img, h))

                next_interval = t_start + acquisition_time
                # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)

                while time.clock() > next_interval:
                    next_interval += acquisition_time
                    i += 1
                    # print i, "SKIP!  {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time)

                diff = next_interval - time.clock() # seconds

                if self.track_stage_position and diff > 0.1:
                    self.stage_positions.append((i, self.ctrl.stageposition.get()))

                time.sleep(diff)

            else:
                img, h = self.ctrl.getImage(self.exposure, header_keys=None)
                # print i, "Image!"
                buffer.append((i, img, h))

            i += 1

        t1 = time.clock()

        if self.mode == "footfree":
            self.ctrl.stageposition.stop()

        self.stopEvent.clear()

        self.ctrl.cam.unblock()

        if self.mode == "simulate":
            # simulate somewhat realistic end numbers
            self.ctrl.stageposition.x += np.random.randint(-5000, 5000)
            self.ctrl.stageposition.y += np.random.randint(-5000, 5000)
            self.ctrl.stageposition.a += np.random.randint(-100, 100)
            self.ctrl.magnification.set(300)

        self.end_position = self.ctrl.stageposition.get()
        self.end_angle = self.end_position[3]
        self.camera_length = int(self.ctrl.magnification.get())
        self.stage_positions.append((99999, self.end_position))

        is_moving = bool(self.ctrl.stageposition.is_moving())
        self.logger.info(f"Experiment finished, stage is moving: {is_moving}")

        if self.unblank_beam:
            print("Blanking beam")
            self.ctrl.beamblank = True

        # in case something went wrong starting data collection, return gracefully
        if i == 1:
            print_and_log(f"Data collection interrupted", logger=self.logger)
            return False

        self.spotsize = self.ctrl.spotsize
        self.nframes = i-1 # len(buffer) can lie in case of frame skipping
        self.osc_angle = abs(self.end_angle - self.start_angle) / self.nframes
        self.total_time = t1 - t0
        self.acquisition_time = self.total_time / self.nframes
        self.total_angle = abs(self.end_angle - self.start_angle)
        self.rotation_axis = config.camera.camera_rotation_vs_stage_xy

        self.nframes_diff = len(buffer)
        self.nframes_image = len(image_buffer)

        self.log_end_status()

        if self.nframes <= 3:
            print_and_log(f"Not enough frames collected. Data will not be written (nframes={self.nframes})", logger=self.logger)
            return False

        self.write_data(buffer)
        self.write_image_data(image_buffer)

        print("Data Collection and Conversion Done.")
        return True

    def write_data(self, buffer):
        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=self.camera_length,
                 osc_angle=self.osc_angle,
                 start_angle=self.start_angle,
                 end_angle=self.end_angle,
                 rotation_axis=self.rotation_axis,
                 acquisition_time=self.acquisition_time,
                 flatfield=self.flatfield)
        
        print("Writing data files...")
        img_conv.threadpoolwriter(tiff_path=self.tiff_path,
                                  mrc_path=self.mrc_path,
                                  smv_path=self.smv_path,
                                  workers=8)
        
        print("Writing input files...")
        if self.write_dials:
            img_conv.to_dials(self.smv_path, interval=self.image_interval_enabled)
        if self.write_red:
            img_conv.write_ed3d(self.mrc_path)
        if self.write_xds or self.write_dials:
            img_conv.write_xds_inp(self.smv_path)
        if self.write_pets:
            img_conv.write_pets_inp(self.path)

        img_conv.write_beam_centers(self.path)

    def write_image_data(self, buffer):
        if buffer:
            drc = self.path / "tiff_image"
            drc.mkdir(exist_ok=True)
            while len(buffer) != 0:
                i, img, h = buffer.pop(0)
                fn = drc / f"{i:05d}.tiff"
                write_tiff(fn, img, header=h)
