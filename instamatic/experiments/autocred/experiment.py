import os
import datetime
import logging
import numpy as np
import time
from instamatic.processing import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from skimage.feature import register_translation
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam
from instamatic.calibrate.calibrate_beamshift import calibrate_beamshift
from instamatic.calibrate.calibrate_imageshift12 import Calibrate_Imageshift, Calibrate_Imageshift2, Calibrate_Beamshift_D
from instamatic.calibrate.center_z import center_z_height
from instamatic.tools import find_defocused_image_center
import pickle
from pathlib import Path
from tqdm import tqdm
from instamatic.calibrate.filenames import CALIB_IS1_DEFOC, CALIB_IS1_FOC, CALIB_IS2_DEFOC, CALIB_IS2_FOC, CALIB_BEAMSHIFT_DP, CALIB_IS1_SAMAG, CALIB_IS2_SAMAG
from instamatic.TEMController.server_microscope import TraceVariable
from instamatic.formats import write_tiff
import traceback

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2
rotation_range = 100
PORT = 8088

"""When TEM changes modes:
from mag1 to diff: does not actually change IS states
from SAMAG to diff: does not change IS states
from mag1 to SAMAG: CHANGES IS states"""

def load_IS_Calibrations(imageshift, ctrl, diff_defocus, logger, mode):
    if mode == 'diff':
        if imageshift == 'IS1' and diff_defocus != 0:
            file = CALIB_IS1_DEFOC
        elif imageshift == 'IS2' and diff_defocus != 0:
            file = CALIB_IS2_DEFOC
        elif imageshift == 'IS1' and diff_defocus == 0:
            file = CALIB_IS1_FOC
        elif imageshift == 'IS2' and diff_defocus == 0:
            file = CALIB_IS2_FOC
        elif imageshift == 'BS':
            file = CALIB_BEAMSHIFT_DP
    elif mode == 'samag':
        if imageshift == 'IS1':
            file = CALIB_IS1_SAMAG
        elif imageshift == 'IS2':
            file = CALIB_IS2_SAMAG
    else:
        print("Wrong input. Input either IS1 or IS2.")
        return 0
    
    try:
        with open(file,'rb') as f:
            transform_imgshift, c = pickle.load(f)
    except:
        print("No {}, defocus = {} calibration found. Choose the desired defocus value.".format(imageshift, diff_defocus))
        inp = input("Press ENTER when ready.")
        if ctrl.mode != mode:
            ctrl.mode = mode
        satisfied = "x"
        while satisfied == "x":
            if imageshift == 'IS1' and diff_defocus != 0:
                transform_imgshift, c = Calibrate_Imageshift(ctrl, diff_defocus, stepsize = 5000, logger = logger, key = 'IS1')
            elif imageshift == 'IS1' and diff_defocus == 0:
                transform_imgshift, c = Calibrate_Imageshift(ctrl, diff_defocus, stepsize = 3000, logger = logger, key = 'IS1')
            elif imageshift == 'IS2':
                transform_imgshift, c = Calibrate_Imageshift2(ctrl, diff_defocus, stepsize = 2000, logger = logger)
            elif imageshift == 'BS':
                transform_imgshift, c = Calibrate_Beamshift_D(ctrl, stepsize = 100, logger = logger)
            with open(file, 'wb') as f:
                pickle.dump([transform_imgshift, c], f)
            satisfied = input(f"{imageshift}, defocus = {diff_defocus} calibration done. \nPress Enter to continue. Press x to redo calibration.")
            
    return transform_imgshift, c

class Experiment(object):
    def __init__(self, ctrl, 
                       exposure_time, 
                       exposure_time_image, 
                       stop_event, 
                       stop_event_experiment,
                       enable_image_interval, 
                       enable_autotrack, 
                       enable_fullacred, 
                       enable_fullacred_crystalfinder,
                       scan_area,
                       unblank_beam=False, 
                       path=None, 
                       log=None, 
                       flatfield=None, 
                       image_interval=99999, 
                       diff_defocus=0):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = path
        self.expt = exposure_time
        self.unblank_beam = unblank_beam
        self.logger = log
        self.camtype = ctrl.cam.name
        self.stopEvent = stop_event
        self.stopEvent_rasterScan = stop_event_experiment
        self.flatfield = flatfield

        self.diff_defocus = diff_defocus
        self.image_interval = image_interval
        self.exposure_time_image = exposure_time_image
        
        self.scan_area = scan_area
        
        self.mode = 0

        self.diff_brightness = self.ctrl.brightness.value
        
        self.image_interval_enabled = enable_image_interval
        if enable_image_interval:
            self.image_interval = image_interval
            msg = f"Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.exposure_time_image} s)."
            print(msg)
            self.logger.info(msg)
        else:
            self.image_interval = 99999
            
        self.enable_autotrack = enable_autotrack
        self.enable_fullacred = enable_fullacred
        self.enable_fullacred_crystalfinder = enable_fullacred_crystalfinder
        
        if enable_fullacred_crystalfinder:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            print("Full autocRED feature with auto crystal finder enabled: every {} frames an image with defocus value {} will be displayed.".format(image_interval, diff_defocus))
            self.mode = 3
        
        elif enable_fullacred:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            print("Full autocRED feature enabled: every {} frames an image with defocus value {} will be displayed.".format(image_interval, diff_defocus))
            self.mode = 2
            
        elif enable_autotrack:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            print("Image autotrack enabled: every {} frames an image with defocus value {} will be displayed.".format(image_interval, diff_defocus))
            self.mode = 1
    
    def image_cropper(self, img, window_size = 0):
        crystal_pos, r = find_defocused_image_center(img) #find_defocused_image_center crystal position (y,x)
        crystal_pos = crystal_pos[::-1]
        
        if window_size == 0:
        
            if r[0] <= r[1]:
                window_size = r[0]*2
            else:
                window_size = r[1]*2
                
            window_size = int(window_size/1.414)
            if window_size % 2 == 1:
                window_size = window_size + 1
        
        a1 = int(crystal_pos[0]-window_size/2)
        b1 = int(crystal_pos[0]+window_size/2)
        a2 = int(crystal_pos[1]-window_size/2)
        b2 = int(crystal_pos[1]+window_size/2)
            
        img_cropped = img[a1:b1,a2:b2]
        return crystal_pos, img_cropped, window_size
    
    def check_lens_close_to_limit_warning(self, lensname, lensvalue, MAX = 65535, threshold = 1000):
        warn = 0
        if abs(lensvalue - MAX) < threshold:
            warn = 1
            print("Warning: {} close to limit!".format(lensname))
        return warn
    
    def check_rotation_went_too_far(self, img1, img2):
        hist1, _ = np.histogram(img1, bins = 256)
        hist2, _ = np.histogram(img2, bins = 256)
        
        cc = np.corrcoef(hist1, hist2)
        if cc[0,1] < 0.8:
            return 1
        else:
            return 0
        
    def img_scale_calculator(self, img):
        return sum(sum(img))
    
    def check_img_outsidebeam_byscale(self, img1_scale, img2_scale):
        """img1 is the original image for reference, img2 is the new image."""
        if img2_scale/img1_scale < 0.5 or img2_scale/img1_scale > 2:
            return 1
        else:
            return 0

    def eliminate_backlash_in_tiltx(self):
        a_i = self.ctrl.stageposition.a
        if a_i < 0:
            self.ctrl.stageposition.set(a = a_i + 0.5 , wait = True)
            return 0
        else:
            self.ctrl.stageposition.set(a = a_i - 0.5 , wait = True)
            return 1

    def auto_cred_collection(self, path, pathtiff, pathsmv, pathred, transform_imgshift, transform_imgshift2, transform_imgshift_foc, transform_imgshift2_foc, transform_beamshift_d, calib_beamshift):
        
        for paths in (path, pathtiff, pathsmv, pathred):
                if not os.path.exists(paths):
                    os.makedirs(paths)

        a = a0 = self.ctrl.stageposition.a
        spotsize = self.ctrl.spotsize
        
        #tracer = TraceVariable(self.ctrl.stageposition.y, interval=2.0, name="stagepositionY", verbose=False)
        #tracer.start()
        
        if self.mode == 1:
            self.logger.info("AutocRED experiment starting...")
        elif self.mode == 2:
            self.logger.info("Full AutocRED experiment starting...")
        elif self.mode == 3:
            self.logger.info("Full AutocRED with auto crystal finder experiment starting...")
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection spot size: {}".format(spotsize))
        # TODO: Mostly above is setup, split off into own function

        buffer = []
        image_buffer = []
            
        if self.mode > 0:

            print("Auto tracking feature activated. Please remember to bring sample to proper Z height in order for autotracking to be effective.")
            
            transform_imgshift_ = np.linalg.inv(transform_imgshift)
            transform_imgshift2_ = np.linalg.inv(transform_imgshift2)
            transform_imgshift_foc_ = np.linalg.inv(transform_imgshift_foc)
            transform_imgshift2_foc_ = np.linalg.inv(transform_imgshift2_foc)
            
            transform_beamshift_d_ = np.linalg.inv(transform_beamshift_d)
        
            self.logger.debug("Transform_imgshift: {}".format(transform_imgshift))
            self.logger.debug("Transform_imgshift_foc: {}".format(transform_imgshift_foc))
            self.logger.debug("Transform_imgshift2: {}".format(transform_imgshift2))
            self.logger.debug("Transform_imgshift2_foc: {}".format(transform_imgshift2_foc))
            
            if self.ctrl.mode != 'diff':
                self.ctrl.mode = 'samag'
                self.ctrl.mode = 'diff'
                
            diff_focus_proper = self.ctrl.difffocus.value
            diff_focus_defocused = diff_focus_proper + self.diff_defocus 
            self.ctrl.difffocus.value = diff_focus_defocused
            
            img0, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
            self.ctrl.difffocus.value = diff_focus_proper
            
            bs_x0, bs_y0 = self.ctrl.beamshift.get()
            is_x0, is_y0 = self.ctrl.imageshift1.get()
            ds_x0, ds_y0 = self.ctrl.diffshift.get()
            is2_x0, is2_y0 = self.ctrl.imageshift2.get()
            
            is1_init = (is_x0, is_y0)
            is2_init = (is2_x0, is2_y0)
            
            self.logger.debug("Initial Beamshift: {}, {}".format(bs_x0, bs_y0))
            self.logger.debug("Initial Imageshift1: {}, {}".format(is_x0, is_y0))
            self.logger.debug("Initial Imageshift2: {}, {}".format(is2_x0, is2_y0))
            
            crystal_pos, img0_cropped, window_size = self.image_cropper(img = img0, window_size = 0)
            
            appos0 = crystal_pos
            self.logger.debug("Initial crystal_pos: {} by find_defocused_image_center.".format(crystal_pos))
            
        if self.mode > 1:
            a_i = self.ctrl.stageposition.a
            try:
                if self.rotation_direction == 0:
                    self.ctrl.stageposition.set(a = a_i + rotation_range , wait = False)
                else:
                    self.ctrl.stageposition.set(a = a_i - rotation_range , wait = False)
            except:
                if a_i < 0:
                    self.ctrl.stageposition.set(a = a_i + rotation_range , wait = False)
                else:
                    self.ctrl.stageposition.set(a = a_i - rotation_range , wait = False)
        
        if self.camtype == "simulate":
            self.startangle = a
        else:
            while abs(a - a0) < ACTIVATION_THRESHOLD:
                a = self.ctrl.stageposition.a
                if abs(a - a0) > ACTIVATION_THRESHOLD:
                    break
            print("Data Recording started.")
            self.startangle = a

        if self.unblank_beam:
            print("Unblanking beam")
            self.ctrl.beamblank = False

        i = 1

        self.ctrl.cam.block()

        t0 = time.clock()

        self.stopEvent.clear()

        while not self.stopEvent.is_set():
            try:
                if i % self.image_interval == 0: ## aim to make this more dynamically adapted...
                    t_start = time.clock()
                    acquisition_time = (t_start - t0) / (i-1)
    
                    self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper
    
                    image_buffer.append((i, img, h))
                    
                    crystal_pos, img_cropped, _ = self.image_cropper(img = img, window_size = window_size)
                    self.logger.debug("crystal_pos: {} by find_defocused_image_center.".format(crystal_pos))
                    
                    cc,err,diffphase = register_translation(img0_cropped,img_cropped)
                    self.logger.debug("Cross correlation result: {}".format(cc))
                    
                    delta_beamshiftcoord = np.matmul(calib_beamshift.transform, cc)
                    #print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                    self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                    self.ctrl.beamshift.set(bs_x0 + delta_beamshiftcoord[0], bs_y0 + delta_beamshiftcoord[1])
                    bs_x0 = bs_x0 + delta_beamshiftcoord[0]
                    bs_y0 = bs_y0 + delta_beamshiftcoord[1]
                    
                    if self.check_lens_close_to_limit_warning(lensname="bemashift", lensvalue=bs_x0) or self.check_lens_close_to_limit_warning(lensname="bemashift", lensvalue=bs_y0):
                        self.logger.debug("Beamshift close to limit warning: bs_x0 = {}, bs_y0 = {}".format(bs_x0, bs_y0))
                        self.stopEvent.set()
                    
                    """Retake a defocused image to check the impact of beam shift on defocused DP (and DP???)"""
                    """self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper"""
                    
                    crystal_pos, r = find_defocused_image_center(img)
                    crystal_pos = crystal_pos[::-1]
                    #print("crystalpos:{}".format(crystal_pos))
                    
                    crystal_pos_dif = crystal_pos - appos0
                    apmv = -crystal_pos_dif
                    dpmv = delta_beamshiftcoord @ transform_beamshift_d_

                    #print("aperture movement: {}".format(apmv))
                    
                    """beam shift effect on diffraction pattern considered in dpmv."""
                    R = -transform_imgshift2_foc_ @ transform_imgshift_foc @ transform_imgshift_ + transform_imgshift2_
                    mv = apmv - dpmv @ transform_imgshift_foc @ transform_imgshift_
                    delta_imageshift2coord = np.matmul(mv, np.linalg.inv(R))
                    delta_imageshiftcoord = dpmv @ transform_imgshift_foc - delta_imageshift2coord @ transform_imgshift2_foc_ @ transform_imgshift_foc
                    
                    #print("delta imageshiftcoord: {}, delta imageshift2coord: {}".format(delta_imageshiftcoord, delta_imageshift2coord))
                    diff_shift = delta_imageshiftcoord @ transform_imgshift_foc_ + delta_imageshift2coord @ transform_imgshift2_foc_
                    img_shift = delta_imageshiftcoord @ transform_imgshift_ + delta_imageshift2coord @ transform_imgshift2_

                    #print("diff_shift: ", diff_shift, "image_shift: ", img_shift, "apmv: ", apmv)
                    
                    self.logger.debug("delta imageshiftcoord: {}, delta imageshift2coord: {}".format(delta_imageshiftcoord, delta_imageshift2coord))
                    
                    self.ctrl.imageshift1.set(x = is_x0 - int(delta_imageshiftcoord[0]), y = is_y0 - int(delta_imageshiftcoord[1]))
                    self.ctrl.imageshift2.set(x = is2_x0 - int(delta_imageshift2coord[0]), y = is2_y0 - int(delta_imageshift2coord[1]))
                    ## the two steps can take ~60 ms per step
                    
                    is_x0 = is_x0 - int(delta_imageshiftcoord[0])
                    is_y0 = is_y0 - int(delta_imageshiftcoord[1])
                    is2_x0 = is2_x0 - int(delta_imageshift2coord[0])
                    is2_y0 = is2_y0 - int(delta_imageshift2coord[1])
                    
                    if self.check_lens_close_to_limit_warning(lensname="imageshift1", lensvalue=is_x0) or self.check_lens_close_to_limit_warning(lensname="imageshift1", lensvalue=is_y0) or self.check_lens_close_to_limit_warning(lensname="imageshift2", lensvalue=is2_x0) or self.check_lens_close_to_limit_warning(lensname="imageshift2", lensvalue=is2_y0):
                        self.logger.debug("Imageshift close to limit warning: is_x0 = {}, is_y0 = {}, is2_x0 = {}, is2_y0 = {}".format(is_x0, is_y0, is2_x0, is2_y0))
                        self.stopEvent.set()
                        
                    """self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper"""
    
                    next_interval = t_start + acquisition_time
                    # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)
    
                    t = time.clock()
    
                    while time.clock() > next_interval:
                        next_interval += acquisition_time
                        i += 1

                    diff = next_interval - time.clock()
                    time.sleep(diff)
    
                else:
                    img, h = self.ctrl.getImage(self.expt, header_keys=None)
                    buffer.append((i, img, h))
                    if i == 1:
                        img1_scale = self.img_scale_calculator(img)
                    else:
                        img2_scale = self.img_scale_calculator(img)
                        if self.check_img_outsidebeam_byscale(img1_scale, img2_scale):
                            print("Crystal outside beam. Collection stopped...")
                            self.stopEvent.set()
    
                i += 1
                
                if self.mode > 1:
                    recv = self.ctrl.stageposition.get()
                    if abs(recv[3]) > 60:
                        self.stopEvent.set()
                
            except Exception as e:
                print (e)
                self.stopEvent.set()

        t1 = time.clock()

        self.ctrl.cam.unblock()
        if self.mode > 1:
            self.ctrl.stageposition.stop()

        if self.camtype == "simulate":
            self.endangle = self.startangle + np.random.random()*50
            camera_length = 300
        else:
            self.endangle = self.ctrl.stageposition.a
            camera_length = int(self.ctrl.magnification.get())

        if self.unblank_beam:
            print("Blanking beam")
            self.ctrl.beamblank = True

        self.stopEvent.clear()
            
        self.ctrl.imageshift1.set(x = is1_init[0], y = is1_init[1])
        self.ctrl.imageshift2.set(x = is2_init[0], y = is2_init[1])

        #stage_positions = tracer.stop()

        print("Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle))
        self.logger.info("Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle))
        
        nframes = i + 1 # len(buffer) can lie in case of frame skipping
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collected from {} degree to {} degree.".format(self.startangle, self.endangle))
        self.logger.info("Oscillation angle: {}".format(osangle))
        self.logger.info("Pixel size and actual camera length updated in SMV file headers for DIALS processing.")
        
        with open(os.path.join(path, "cRED_log.txt"), "w") as f:
            f.write("Data Collection Time: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("Starting angle: {}\n".format(self.startangle))
            f.write("Ending angle: {}\n".format(self.endangle))
            f.write("Exposure Time: {} s\n".format(self.expt))
            f.write("Spot Size: {}\n".format(spotsize))
            f.write("Camera length: {} mm\n".format(camera_length))
            f.write("Oscillation angle: {} degrees\n".format(osangle))
            f.write("Number of frames: {}\n".format(len(buffer)))
            
        #with open(os.path.join(path, "IS1_Log.txt"), "w") as ff:
        #    ff.write("{}".format(stage_positions))

        rotation_angle = config.camera.camera_rotation_vs_stage_xy

        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=camera_length,
                 osc_angle=osangle,
                 start_angle=self.startangle,
                 end_angle=self.endangle,
                 rotation_axis=rotation_angle,
                 acquisition_time=acquisition_time,
                 flatfield=self.flatfield)
        
        img_conv.tiff_writer(pathtiff)
        img_conv.smv_writer(pathsmv)
        img_conv.write_ed3d(pathred)
        img_conv.mrc_writer(pathred)
        img_conv.write_xds_inp(pathsmv)
        self.logger.info("XDS INP file created.")

        if image_buffer:
            drc = os.path.join(path,"tiff_image")
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, "{:05d}.tiff".format(i))
                write_tiff(fn, img, header=h)

        print("Data Collection and Conversion Done.")
            
    def write_BrightnessStates(self):
        print("Go to your desired magnification and camera length. Now recording lens states...")
        self.ctrl.mode = 'mag1'
        input("Please partially converge the beam in MAG1 to around 1 um in diameter, press ENTER when ready")
        
        img_brightness = self.ctrl.brightness.value
        bs = self.ctrl.beamshift.get()
        
        self.ctrl.mode = 'samag'
        self.ctrl.mode = 'diff'
        input("Please go to diffraction mode and focus the diffraction spots, press ENTER when ready")
        dp_focus = self.ctrl.difffocus.value
        is1status = self.ctrl.imageshift1.get()
        is2status = self.ctrl.imageshift2.get()
        plastatus = self.ctrl.diffshift.get()
        with open("beam_brightness.pkl",'wb') as f:
            pickle.dump([img_brightness, bs, dp_focus, is1status, is2status, plastatus], f)
        
        print("Brightness recorded.")
        return [img_brightness, bs, dp_focus, is1status, is2status, plastatus]
    
    def raster_scan(self):
        from instamatic.experiments.serialed.experiment import get_offsets_in_scan_area
        image_dimensions = config.calibration.mag1_camera_dimensions[self.ctrl.magnification.get()]
        box_x, box_y = image_dimensions
        offsets = get_offsets_in_scan_area(box_x, box_y, self.scan_area, angle = config.camera.camera_rotation_vs_stage_xy)
        self.offsets = offsets * 1000
        
        center_x = self.ctrl.stageposition.x
        center_y = self.ctrl.stageposition.y
        
        t = tqdm(self.offsets, desc = "                          ")
        
        for j, (x_offset, y_offset) in enumerate(t):
            x = center_x + x_offset
            y = center_y + y_offset
            
            self.ctrl.stageposition.set(x=x, y=y)
            print("Stage position: x = {}, y = {}".format(x,y))
            
            self.start_collection_point()

            if self.stopEvent_rasterScan.is_set():
                break
        
    def start_collection_point(self):
        
        IS1_Neut = self.ctrl.imageshift1.get()
        IS2_Neut = self.ctrl.imageshift2.get()
        
        stagex = self.ctrl.stageposition.x
        stagey = self.ctrl.stageposition.y
        
        path = self.path
        
        if self.scan_area != 0:
            stagex = int(stagex)
            stagey = int(stagey)
            path = path / f"stagepos_{stagex:06d}_{stagey:06d}"
            if not os.path.exists(path):
                os.makedirs(path)
        
        try:
            with open("beam_brightness.pkl",'rb') as f:
                [img_brightness, bs, dp_focus, is1status, is2status, plastatus] = pickle.load(f)
        except IOError:
            [img_brightness, bs, dp_focus, is1status, is2status, plastatus] = self.write_BrightnessStates()
        
        try:
            self.calib_beamshift = CalibBeamShift.from_file()
            self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])

        except IOError:
            print("No beam shift calibration result found. Running instamatic.calibrate_beamshift first...\n")
            print("Going to MAG1, 2500*, and desired brightness. DO NOT change brightness!")
            if self.ctrl.mode != 'mag1':
                self.ctrl.mode = 'mag1'
                self.ctrl.magnification.value = 2500
                self.ctrl.brightness.value = img_brightness
                
            calib_file = "x"
            while calib_file == "x":
                print("Find a clear area, toggle the beam to the desired defocus value.")
                self.calib_beamshift = calibrate_beamshift(ctrl = self.ctrl)
                #mag1foc_brightness = self.ctrl.brightness.value
                print("Beam shift calibration done.")
                calib_file = input("Find your particle, go back to diffraction mode, and press ENTER when ready to continue. Press x to REDO the calibration.")
                
        self.logger.debug("Transform_beamshift: {}".format(self.calib_beamshift.transform))
        
        try:
            self.calib_directbeam = CalibDirectBeam.from_file()
            with open('diff_par.pkl','rb') as f:
                self.diff_brightness, self.diff_difffocus = pickle.load(f)
        except IOError:
            if not self.ctrl.mode == 'diff':
                self.ctrl.mode = 'samag'
                self.ctrl.imageshift1.set(x=is1status[0], y=is1status[1])
                self.ctrl.imageshift2.set(x=is2status[0], y=is2status[1])
                self.ctrl.mode = 'diff'
            self.ctrl.difffocus.value = dp_focus
            
            self.calib_directbeam = CalibDirectBeam.live(self.ctrl, outdir='.')
            self.diff_brightness = self.ctrl.brightness.value
            self.diff_difffocus = self.ctrl.difffocus.value
            with open('diff_par.pkl','wb') as f:
                pickle.dump([self.diff_brightness, self.diff_difffocus], f)
        
        self.neutral_beamshift = bs
        self.neutral_diffshift = plastatus
        
        self.calib_beamshift.reference_shift = bs
        
        transform_imgshift, c = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = self.diff_defocus, logger = self.logger, mode = 'diff')
        transform_imgshift2, c = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = self.diff_defocus, logger = self.logger, mode = 'diff')
        transform_imgshift_foc, c = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = 0, logger = self.logger, mode = 'diff')
        transform_imgshift2_foc, c = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = 0, logger = self.logger, mode = 'diff')
        transform_beamshift_d, c = load_IS_Calibrations(imageshift = 'BS', ctrl = self.ctrl, diff_defocus= 0, logger = self.logger, mode = 'diff')
        
        if self.mode == 3:
            #ready = input("Please make sure that you are in the super user mode and the rotation speed is set via GONIOTOOL! Press ENTER to continue.")
                
            from instamatic.processing.find_crystals import find_crystals_timepix
            if self.ctrl.mode != 'mag1':
                self.ctrl.mode = 'mag1'
                
            self.ctrl.magnification.value = 2500
            self.ctrl.brightness.value = 65535
            
            header_keys = None

            print("Beamshift reference: {}".format(self.calib_beamshift.reference_shift))
            
            self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])

            #input("Find a good area for investigation. Center the beam using beamshift if beam is not centered. ENTER>>>")
            
            bs = self.ctrl.beamshift.get()
            self.calib_beamshift.reference_shift = bs
            self.neutral_beamshift = bs
            
            self.magnification = self.ctrl.magnification.value
            #self.rotation_direction = self.eliminate_backlash_in_tiltx()
            img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
            #img, h = Experiment.apply_corrections(img, h)

            threshold = 10  # ignore black images
            if img.mean() > threshold:

                write_tiff(path / f"Overall_view", img)

                crystal_positions = find_crystals_timepix(img, self.magnification, spread = 0.6)
                crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                
                n_crystals = len(crystal_coords)

                if n_crystals == 0:
                    print("No crystals found in the image. Find another area!")
                    return 0
                
                self.logger.info("{} {} crystals found.".format(datetime.datetime.now(), n_crystals))

                self.ctrl.brightness.value = img_brightness
                k = 0
                
                while True:

                    try:
                        
                        print("Collecting on crystal {}/{}. Beamshift coordinates: {}".format(k + 1, n_crystals, self.ctrl.beamshift.get()))

                        outfile = path / f"crystal_{k:04d}"
                        comment = "crystal {}".format(k)
                        #img, h = self.ctrl.getImage(exposure=self.expt, comment=comment, header_keys=header_keys)
                        #img, h = Experiment.apply_corrections(img, h)

                        beamshift_coords = self.calib_beamshift.pixelcoord_to_beamshift(crystal_coords[k])

                        self.ctrl.beamshift.set(*beamshift_coords)

                        img, h = self.ctrl.getImage(exposure=0.001, comment=comment, header_keys=header_keys)
                        write_tiff(path / f"crystal_{k:04d}", img)
                        """Sometimes k is out of range error!!!"""

                        if crystal_positions[k].isolated:

                            self.ctrl.mode = 'samag'
                            self.ctrl.mode = "diff"
                            self.ctrl.imageshift1.set(x=is1status[0], y=is1status[1])
                            self.ctrl.imageshift2.set(x=is2status[0], y=is2status[1])
                            self.ctrl.diffshift.set(x=plastatus[0], y=plastatus[1])
                            
                            # compensate beamshift
                            beamshift_offset = beamshift_coords - self.neutral_beamshift
                            pixelshift = self.calib_directbeam.beamshift2pixelshift(beamshift_offset)
                        
                            diffshift_offset = self.calib_directbeam.pixelshift2diffshift(pixelshift)
                            diffshift = self.neutral_diffshift - diffshift_offset
                        
                            self.ctrl.diffshift.set(*diffshift.astype(int))
                            
                            pathtiff = outfile / "tiff"
                            pathsmv = outfile / "SMV"
                            pathred = outfile / "RED"
                            
                            self.auto_cred_collection(outfile, pathtiff, pathsmv, pathred, transform_imgshift, transform_imgshift2, transform_imgshift_foc, transform_imgshift2_foc, transform_beamshift_d, self.calib_beamshift)
                            
                            self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])
                            self.ctrl.mode = 'mag1'
                            self.ctrl.brightness.value = 65535
                            time.sleep(0.5)
                            #self.rotation_direction = self.eliminate_backlash_in_tiltx()
                            img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
                            write_tiff(path / f"Overall_view_{k:04d}", img)

                            crystal_positions = find_crystals_timepix(img, self.magnification, spread = 0.6)
                            crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                            self.ctrl.brightness.value = img_brightness
                            
                            if n_crystals == 0:
                                print("No crystals found in the image. exitting loop...")
                                break
                            
                        else:
                            print("Crystal {} not isolated: not suitable for cred collection".format(k+1))
                        
                        k = k + 1
                        if k >= n_crystals:
                            break
                    except:
                        traceback.print_exc()
                        print("Exitting...")
                        break
                    
                self.ctrl.mode = 'mag1'
                self.ctrl.brightness.value = 65535
                
                self.ctrl.imageshift1.set(x = IS1_Neut[0], y = IS1_Neut[1])
                self.ctrl.imageshift2.set(x = IS2_Neut[0], y = IS2_Neut[1])
                
                self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])
                
                print("AutocRED with crystal_finder data collection done. Find another area for particles.")
            
        elif self.mode == 1 or self.mode == 2:
            self.pathtiff = Path(self.path) / "tiff"
            self.pathsmv = Path(self.path) / "SMV"
            self.pathred = Path(self.path) / "RED"
            
            for path in (self.path, self.pathtiff, self.pathsmv, self.pathred):
                if not os.path.exists(path):
                    os.makedirs(path)
            self.auto_cred_collection(self.path, self.pathtiff, self.pathsmv, self.pathred, transform_imgshift, transform_imgshift2, transform_imgshift_foc, transform_imgshift2_foc, transform_beamshift_d, self.calib_beamshift)
        
        else:
            print("Choose cRED tab for data collection with manual/blind tracking.")
            return 0
        
    def start_collection(self):
        ready = input("Please make sure that you have adjusted Goniotool if you are using full autocRED!")
        
        lensPar = self.ctrl.to_dict()
        with open("LensPar.pkl","wb") as f:
            pickle.dump(lensPar, f)

        if self.scan_area == 0:
            self.start_collection_point()
        else:
            self.raster_scan()

        self.stopEvent_rasterScan.clear()

        with open("LensPar.pkl","rb") as f:
            lensPar_i = pickle.load(f)

        self.ctrl.from_dict(lensPar_i)
        print("AutocRED collection done.")