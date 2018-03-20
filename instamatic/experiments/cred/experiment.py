import os
import datetime
from tkinter import *
import numpy as np
import time
from . import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from pathlib import Path

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2

def Calibrate_Imageshift(ctrl, diff_defocus,stepsize):
    from instamatic.calibrate.fit import fit_affine_transformation
    from instamatic.processing.cross_correlate import cross_correlate

    inp = raw_input("""Calibrate imageshift
-------------------
 1. Go to diffraction mode.
 2. Focus the diffraction spots.
 3. Center the beam with PLA.
    
 >> Press <ENTER> to start >> \n""")
    
    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_defocus 
        ctrl.difffocus.value = diff_focus_defocused
    x0, y0 = ctrl.imageshift.get()
    img_cent, h_cent = ctrl.getImage(exposure=0.01, comment="Beam in center of image")

    shifts = []
    imgpos = []
    stepsize = stepsize
    
    for i in range(0,5):
        for j in range(0,5):
            ctrl.imageshift.set(x= x0 + (i-2)*stepsize, y= y0 + (j-2)*stepsize)
            img, h = ctrl.getImage(exposure = 0.01, comment = "imageshifted image")

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
            imgshift = np.array(((i-2)*stepsize, (j-2)*stepsize))
            imgpos.append(imgshift)
            shifts.append(shift)

    ctrl.imageshift.set(x = x0, y = y0)
    
    r, t = fit_affine_transformation(shifts, imgpos)
    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper
    print "ImageShift calibration done."
    print r

    return r

def Calibrate_Imageshift2(ctrl, diff_defocus,stepsize):
    from instamatic.calibrate.fit import fit_affine_transformation
    from instamatic.processing.cross_correlate import cross_correlate

    inp = raw_input("""Calibrate imageshift2
-------------------
 1. Go to diffraction mode.
 2. Focus the diffraction spots.
 3. Center the beam with PLA.
    
 >> Press <ENTER> to start >> \n""")
    
    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_defocus 
        ctrl.difffocus.value = diff_focus_defocused
    x0, y0 = ctrl.imageshift2.get()
    img_cent, h_cent = ctrl.getImage(exposure=0.01, comment="Beam in center of image")

    shifts = []
    imgpos = []
    stepsize = stepsize
    
    for i in range(0,5):
        for j in range(0,5):
            ctrl.imageshift2.set(x= x0 + (i-2)*stepsize, y= y0 + (j-2)*stepsize)
            img, h = ctrl.getImage(exposure = 0.01, comment = "imageshifted image")

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
            imgshift = np.array(((i-2)*stepsize, (j-2)*stepsize))
            imgpos.append(imgshift)
            shifts.append(shift)

    ctrl.imageshift2.set(x = x0, y = y0)
    
    r, t = fit_affine_transformation(shifts, imgpos)
    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper
    print "ImageShift2 calibration done."
    print r

    return r

def Calibrate_Diffshift(ctrl, diff_defocus, stepsize):
    from instamatic.calibrate.fit import fit_affine_transformation
    from instamatic.processing.cross_correlate import cross_correlate

    inp = raw_input("""Calibrate imageshift
-------------------
 1. Go to diffraction mode.
 2. Focus the diffraction spots.
 3. Center the beam with PLA.
    
 >> Press <ENTER> to start >> \n""")

    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_defocus 
        ctrl.difffocus.value = diff_focus_defocused

    x0, y0 = ctrl.diffshift.get()
    
    img_cent, h_cent = ctrl.getImage(exposure=0.01, comment="Beam in center of image")

    shifts = []
    imgpos = []
    stepsize = stepsize
    
    for i in range(0,5):
        for j in range(0,5):
            ctrl.diffshift.set(x= x0 + (i-2)*stepsize, y= y0 + (j-2)*stepsize)
            img, h = ctrl.getImage(exposure = 0.01, comment = "diffshifted defocused image")

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
            dif_shift = np.array(((i-2)*stepsize, (j-2)*stepsize))
            imgpos.append(dif_shift)
            shifts.append(shift)

    ctrl.diffshift.set(x = x0, y = y0)
    
    r, t = fit_affine_transformation(shifts, imgpos)
    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper
    print "ImageShift calibration done."
    print r

    return r

"""fast_finder is contribution from Dr Jonas Angstrom"""
def fast_finder(image, treshold=1):
    X = np.mean(image, axis=0)
    Y = np.mean(image, axis=1)
    im_mean = np.mean(X)
    rads = np.zeros(2)
    center = np.zeros(2)
    for n, XY in enumerate([X,Y]):
        over = np.where(XY>(im_mean*treshold))[0]
        rads[n] = (over[-1] - over[0])/2
        center[n] = over[0] + rads[n]
    return center, rads

def center_z_height(ctrl):
    """http://www.msg.ucsf.edu/agard/Publications/52-Koster.pdf"""
    print "Finding eucentric height..."
    z0 = ctrl.stageposition.z
    x0 = ctrl.stageposition.x
    z = []
    d = []
    
    for i in range(0,5):
        z1 = ctrl.stageposition.z
        z.append(z1)
        x = ctrl.stageposition.x
        img0 = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        ctrl.stageposition.set(x = x + 2)
        img1 = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        shift = cross_correlate(img0, img1, upsample_factor=10, verbose=False)
        d.append(np.linalg.norm(shift))
        print "Step {}: z = {}, d = {}".format(i, z1, np.linalg.norm(shift))
        ctrl.stageposition.set(z1 + 1)
        time.sleep(1)
        
    p = np.polyfit(z, d, 1)
    z_center = -p[1]/p[0]
    satisfied = raw_input("Found eucentric height: {}. Press ENTER to set the height, x to cancel setting.".format(z_center))
    if satisfied == "x":
        ctrl.stageposition.set(x = x0, z = z0)
        print "Did not find proper eucentric height..."
    else:
        ctrl.stageposition.set(x = x0, z = z_center)
        print "Eucentric height set. Find the crystal again and start data collection!"
    
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
        self.path = Path(path)
        self.expt = exposure_time
        self.unblank_beam = unblank_beam
        self.logger = log
        self.camtype = ctrl.cam.name
        self.stopEvent = stop_event
        self.flatfield = flatfield

        self.diff_defocus = diff_defocus
        self.expt_image = exposure_time_image

        self.write_tiff = write_tiff
        self.write_xds = write_xds
        self.write_dials = write_dials
        self.write_red = write_red

        self.image_interval_enabled = enable_image_interval
        if enable_image_interval:
            self.image_interval = image_interval
            msg = f"Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.expt_image} s)."
            print(msg)
            self.logger.info(msg)
        else:
            self.image_interval = 99999

    def report_status(self):
        self.diff_binsize = self.ctrl.cam.default_binsize
        self.diff_brightness = self.ctrl.brightness.value
        self.diff_spotsize = self.ctrl.spotsize

        print(f"\nOutput directory: {self.path}")
        print(f"Diffraction : binsize = {self.diff_binsize}")
        print(f"              exposure = {self.expt}")
        print(f"              brightness = {self.diff_brightness}")
        print(f"              spotsize = {self.diff_spotsize}")

    def start_collection(self):
        a = a0 = self.ctrl.stageposition.a
        spotsize = self.ctrl.spotsize

        self.tiff_path = self.path / "tiff" if self.write_tiff else None
        self.smv_path  = self.path / "SMV"  if (self.write_xds or self.write_dials) else None
        self.mrc_path  = self.path / "RED"  if self.write_red else None
              
        self.now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.info(f"Data recording started at: {self.now}")
        self.logger.info(f"Data saving path: {self.path}")
        self.logger.info(f"Data collection exposure time: {self.expt} s")
        self.logger.info(f"Data collection spot size: {spotsize}")
        
        # TODO: Mostly above is setup, split off into own function



        if self.ctrl.mode != 'diff':
            self.ctrl.mode = 'diff'

        if self.camtype == "simulate":
            self.start_angle = a
        else:
            print("Waiting for rotation to start...", end=' ')
            while abs(a - a0) < ACTIVATION_THRESHOLD:
                a = self.ctrl.stageposition.a

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

        print self.mode

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
                time.sleep(diff)


            else:
                if i % self.image_interval == 0:
                    t_start = time.clock()
                    acquisition_time = (t_start - t0) / (i-1)
    
                    self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.getImage(self.expt / 5.0, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper
    
                    image_buffer.append((i, img, h))
    
                    next_interval = t_start + acquisition_time
                    # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)
    
                    t = time.clock()
    
                    while time.clock() > next_interval:
                        next_interval += acquisition_time
                        i += 1
                        # print i, "SKIP!  {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time)
    
                    #while time.time() < next_interval:
                        #time.sleep(0.001)
                    diff = next_interval - time.clock()
                    time.sleep(diff)
    
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

        is_moving = bool(self.ctrl.stageposition.is_moving())
        self.logger.info(f"Experiment finished, stage is moving: {is_moving}")

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
        total_angle = abs(self.end_angle-self.start_angle)
        print(f"\nRotated {total_angle:.2f} degrees from {self.start_angle:.2f} to {self.end_angle:.2f} in {nframes} frames (step: {osc_angle:.4f})")

        self.logger.info(f"Data collection camera length: {camera_length} mm")
        self.logger.info(f"Rotated {total_angle:.2f} degrees from {self.start_angle:.2f} to {self.end_angle:.2f} in {nframes} frames (step: {osc_angle:.2f})")
        
        with open(self.path / "cRED_log.txt", "w") as f:
            print(f"Data Collection Time: {self.now}", file=f)
            print(f"Starting angle: {self.start_angle:.2f} degrees", file=f)
            print(f"Ending angle: {self.end_angle:.2f} degrees", file=f)
            print(f"Rotation range: {self.end_angle-self.start_angle:.2f} degrees", file=f)
            print(f"Exposure Time: {self.expt:.3f} s", file=f)
            print(f"Acquisition time: {acquisition_time:.3f} s", file=f)
            print(f"Total time: {total_time:.3f} s", file=f)
            print(f"Spot Size: {spotsize}", file=f)
            print(f"Camera length: {camera_length} mm", file=f)
            print(f"Oscillation angle: {osc_angle:.4f} degrees", file=f)
            print(f"Number of frames: {len(buffer)}", file=f)

            if self.image_interval_enabled:
                print(f"Image interval: every {image_interval} frames an image with defocus {diff_focus_defocused} (t={expt_image} s).", file=f)
                print(f"Number of images: {len(image_buffer)}", file=f)

        if nframes <= 3:
            self.logger.info(f"Not enough frames collected. Data will not be written (nframes={nframes}).")
            print(f"Data collection done. Not enough frames collected (nframes={nframes}).")
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

        img_conv.write_beam_centers(self.path)

        if image_buffer:
            drc = self.path / "tiff_image"
            drc.mkdir(exist_ok=True)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = drc / f"{i:05d}.tiff"
                write_tiff(fn, img, header=h)

        print("Data Collection and Conversion Done.")
        self.stopEvent.clear()
