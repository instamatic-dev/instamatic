import os
import datetime
import logging
import numpy as np
import time
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from skimage.feature import register_translation
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam
from instamatic.calibrate.calibrate_beamshift import calibrate_beamshift
from instamatic.calibrate.calibrate_imageshift12 import Calibrate_Imageshift, Calibrate_Imageshift2, Calibrate_Beamshift_D, Calibrate_Stage
from instamatic.calibrate.center_z import center_z_height, center_z_height_HYMethod
from instamatic.tools import find_defocused_image_center, find_beam_center
from instamatic.processing.flatfield import apply_flatfield_correction
from instamatic.neural_network import predict, preprocess
import pickle
from pathlib import Path
from tqdm import tqdm
from instamatic.calibrate.filenames import CALIB_IS1_DEFOC, CALIB_IS1_FOC, CALIB_IS2_DEFOC, CALIB_IS2_FOC, CALIB_BEAMSHIFT_DP
from instamatic.processing.find_crystals import find_crystals_timepix
import traceback
import socket
import datetime
import shutil
from scipy import ndimage

ACTIVATION_THRESHOLD = 0.2
rotation_speed = 0.86

"""Imgvar can be compared with the first defocused image. If other particles move in, the variance will be at least 50% different"""
imgvar_threshold = 600
"""spread, offset: parameters for find_crystals_timepix"""
spread = 2 # sometimes crystals still are not so isolated using number 0.6 as suggested.
offset = 15 # The number needs to be smaller when the contrast of the crystals is low.

date = datetime.datetime.now().strftime("%Y-%m-%d")
log_rotaterange = config.logs_drc / f"Rotrange_stagepos_{date}.log"
if not os.path.isfile(log_rotaterange):
    with open(log_rotaterange, "a") as f:
        f.write("x\ty\tz\trotation range\n")

s = socket.socket()
dials_host = 'localhost'
dials_port = 8089
try:
    s.connect((dials_host, dials_port))
    print("DIALS server connected for autocRED.")
    s_c = 1
except:
    s_c = 0

def load_IS_Calibrations(imageshift, ctrl, diff_defocus, logger, mode):
    if mode == 'diff' or mode == 'mag1':
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
        elif imageshift == 'S':
            file = "CalibStage.pkl"
    else:
        print("Wrong input. Mode can either be mag1 or diff for calibration!")
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
                transform_imgshift, c = Calibrate_Imageshift(ctrl, diff_defocus, stepsize = 1500, logger = logger, key = 'IS1')
            elif imageshift == 'IS1' and diff_defocus == 0:
                transform_imgshift, c = Calibrate_Imageshift(ctrl, diff_defocus, stepsize = 1000, logger = logger, key = 'IS1')
            elif imageshift == 'IS2':
                transform_imgshift, c = Calibrate_Imageshift2(ctrl, diff_defocus, stepsize = 750, logger = logger)
            elif imageshift == 'BS':
                transform_imgshift, c = Calibrate_Beamshift_D(ctrl, stepsize = 100, logger = logger)
            elif imageshift == 'S':
                transform_imgshift, c = Calibrate_Stage(ctrl, stepsize = 1000, logger = logger)
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
                       zheight,
                       autocenterDP,
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
        self.stagepos_idx = 0

        self.diff_defocus = diff_defocus
        self.image_interval = image_interval
        self.nom_ii = self.image_interval
        self.robust_ii = 2
        self.exposure_time_image = exposure_time_image
        
        self.scan_area = scan_area
        self.auto_zheight = zheight
        self.mode = 0

        self.diff_brightness = self.ctrl.brightness.value
        self.autocenterDP = autocenterDP
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
    
    def check_lens_close_to_limit_warning(self, lensname, lensvalue, MAX = 65535, threshold = 5000):
        warn = 0
        if MAX - lensvalue < threshold or lensvalue < threshold:
            warn = 1
            print("Warning: {} close to limit!".format(lensname))
        return warn
    
    def img_var(self, img, apert_pos):
        apert_pos = [int(apert_pos[0]), int(apert_pos[1])]
        window_size = img.shape[0]
        half_w = int(window_size/2)
        x_range = range(apert_pos[0] - half_w, apert_pos[0] + half_w)
        y_range = range(apert_pos[1] - half_w, apert_pos[1] + half_w)
        
        if not any(x in range(255, 261) for x in x_range) and not any(y in range(255, 261) for y in y_range):
            return np.var(img)
        else:
            if any(x in range(255, 261) for x in x_range):
                indx = []
                for px in range(255, 261):
                    try:
                        indx.append(x_range.index(px))
                    except:
                        pass
            
                img = np.delete(img, indx, 0)
            
            if any(y in range(255, 261) for y in y_range):
                indy = []
                for px in range(255, 261):
                    try:
                        indy.append(y_range.index(px))
                    except:
                        pass
                
                img = np.delete(img, indy, 1)
                
            return np.var(img)
        
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
            #print("Rotation positive!")
            return 0
        else:
            self.ctrl.stageposition.set(a = a_i - 0.5 , wait = True)
            #print("Rotation negative!")
            return 1
        
    def center_particle_ofinterest(self, pos_arr, transform_stagepos):
        """Used to center the particle of interest in the view to minimize usage of lens"""
        transform_stagepos_ = np.linalg.inv(transform_stagepos)
        if pos_arr[0] < 200 or pos_arr[0] > 316 or pos_arr[1] < 200 or pos_arr[1] > 316:

            #print(pos_arr)
            _x0 = self.ctrl.stageposition.x
            _y0 = self.ctrl.stageposition.y
            
            displacement = np.subtract((258,258), pos_arr)
            #print("Displacement should be: {} in pixels".format(displacement))
            mag = self.ctrl.magnification.value
            image_dimensions = config.calibration.mag1_camera_dimensions[mag]
            #print("Image size: {} um".format(image_dimensions))
            s = image_dimensions[0]/516
            #print("scaling facor: {} um per px".format(s))
            mvmt = s * displacement
            #print("Stage movement: {} um in x and y".format(mvmt))
            mvmt_x, mvmt_y = np.dot(1000 * mvmt, transform_stagepos_)

            #print("Stagemovement: {} in x, {} in y".format(mvmt_x,mvmt_y))
            
            self.ctrl.stageposition.set(x = _x0 + mvmt_y, y = _y0 - mvmt_x)
            
        else:
            pass
        
    def center_particle_from_crystalList(self, crystal_positions, transform_stagepos, magnification):
        n_crystals = len(crystal_positions)
        if n_crystals == 0:
            print("No crystal found on image!")
            return (0,0)
        
        else:
            for crystal in crystal_positions:
                if crystal.isolated:
                    self.center_particle_ofinterest((crystal.x, crystal.y), transform_stagepos)
                    crystalsize = crystal.area_pixel
                    #print("crystal size: {}".format(crystalsize))
                    img, h = self.ctrl.getImage(exposure = self.expt, header_keys=None)
                    
                    crystal_positions_new = find_crystals_timepix(img, magnification=self.magnification, spread=spread, offset=offset)
                    
                    n_crystals_new = len(crystal_positions_new)
                    #print(crystal_positions_new)
                    if n_crystals_new == 0:
                        print("No crystal found after centering...")
                        return (0,0)
                    
                    else:
                        #print("Start looping.")
                        for crystal in crystal_positions_new:
                            if crystal.isolated and crystal.area_pixel == crystalsize:
                                print("Crystal that has been centered is found at {}, {}.".format(crystal.x, crystal.y))
                                beamshift_coords = self.calib_beamshift.pixelcoord_to_beamshift((crystal.x, crystal.y))
                                
                                return (beamshift_coords, crystalsize)
                            else:
                                return (0,0)

                else:
                    return (0,0)
            
    def isolated(self, c, crystalpositions,  thresh = 100):
        distances=[]
        if len(crystalpositions) == 1:
            return True
        else:
            for allcryst in crystalpositions:
                distvec = np.subtract(allcryst, (c.x, c.y))
                dist = np.linalg.norm(distvec)
                if dist != 0:
                    distances.append(dist)
                    
            if min(distances) > thresh: ## in pixels
                return True
            else:
                return False
            
    def find_crystal_center(self, img_c, window_size, gauss_window = 4):
        l = np.min(img_c)
        h = np.max(img_c)
        
        sel = (img_c > l + 0.1*(h-l)) & (img_c < h - 0.4*(h-l))
        blurred = ndimage.filters.gaussian_filter(sel.astype(float), gauss_window)
        x, y = np.unravel_index(np.argmax(blurred, axis=None), blurred.shape)
        return (y, x)
    
    def find_crystal_center_fromhist(self, img, bins = 20, plot = False, gauss_window = 5):
        h, b = np.histogram(img, bins)
        sel = (img > b[1]) & (img < b[4])
        
        blurred = ndimage.filters.gaussian_filter(sel.astype(float), gauss_window)
        x, y = np.unravel_index(np.argmax(blurred, axis=None), blurred.shape)
        if plot:
            plt.imshow(sel)
            plt.scatter(y, x)
            plt.show()
        return (y, x)
            
    def tracking_by_particlerecog(self, img, magnification = 2500, spread = 6, offset = 18):
        crystal_pos, r = find_defocused_image_center(img) #find_defocused_image_center crystal position (y,x)
        crystal_pos = crystal_pos[::-1]

        window_size = 0
    
        if window_size == 0:
    
            if r[0] <= r[1]:
                window_size = r[0]*2
            else:
                window_size = r[1]*2
    
            #window_size = int(window_size/1.414)
            if window_size % 2 == 1:
                window_size = window_size + 1
    
        a1 = int(crystal_pos[0]-window_size/2)
        b1 = int(crystal_pos[0]+window_size/2)
        a2 = int(crystal_pos[1]-window_size/2)
        b2 = int(crystal_pos[1]+window_size/2)
    
        img_cropped = img[a1:b1,a2:b2]
        
        #crystalpositions = find_crystals_timepix(img_cropped, magnification = magnification, spread=spread, offset = offset)
        #crystalposition = self.find_crystal_center(img_cropped, window_size)
        crystalposition = self.find_crystal_center_fromhist(img_cropped)
        center = (window_size/2, window_size/2)
        
        #if len(crystalpositions) == 1:
            #crystalxy = (crystalpositions[0].x, crystalpositions[0].y)
        shift = np.subtract(center, crystalposition)
        #elif len(crystalpositions) > 1:
        #    areas = [crystal.area_pixel for crystal in crystalpositions]
        #    idx = areas.index(max(areas))
        #    crystalxy = (crystalpositions[idx].x, crystalpositions[idx].y)
        #    shift = np.subtract(center, crystalxy)
        ##else:
        #    print("Crystal lost.")
        #    shift = np.array((512, 512))
        
        return tuple(shift[::-1])
    
    def setandupdate_bs(self, bs_x0, bs_y0, delta_beamshiftcoord1):
        self.ctrl.beamshift.set(bs_x0 + delta_beamshiftcoord1[0], bs_y0 + delta_beamshiftcoord1[1])
        bs_x0 = bs_x0 + delta_beamshiftcoord1[0]
        bs_y0 = bs_y0 + delta_beamshiftcoord1[1]
        return bs_x0, bs_y0
    
    def defocus_and_image(self, difffocus, exp_t):
        diff_focus_proper = self.ctrl.difffocus.value
        diff_focus_defocused = diff_focus_proper + difffocus
        self.ctrl.difffocus.value = diff_focus_defocused
        
        img0, h = self.ctrl.getImage(exp_t, header_keys=None)
        self.ctrl.difffocus.value = diff_focus_proper
        return img0, h
    
    def print_and_log(self, logger, msg):
        print(msg)
        logger.debug(msg)

    def auto_cred_collection(self, path, pathtiff, pathsmv, pathred, transform_imgshift, transform_imgshift2, transform_imgshift_foc, transform_imgshift2_foc, transform_beamshift_d, calib_beamshift):
        
        """track method
        p: particle recognition
        c: cross correlation"""
        
        trackmethod = "p"
        
        for paths in (path, pathtiff, pathsmv, pathred):
                if not os.path.exists(paths):
                    os.makedirs(paths)

        a = a0 = self.ctrl.stageposition.a
        spotsize = self.ctrl.spotsize
        
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
            
            bs_x0, bs_y0 = self.ctrl.beamshift.get()
            is_x0, is_y0 = self.ctrl.imageshift1.get()
            ds_x0, ds_y0 = self.ctrl.diffshift.get()
            is2_x0, is2_y0 = self.ctrl.imageshift2.get()
            
            is1_init = (is_x0, is_y0)
            is2_init = (is2_x0, is2_y0)
            
            self.logger.debug("Initial Beamshift: {}, {}".format(bs_x0, bs_y0))
            self.logger.debug("Initial Imageshift1: {}, {}".format(is_x0, is_y0))
            self.logger.debug("Initial Imageshift2: {}, {}".format(is2_x0, is2_y0))

            diff_focus_proper = self.ctrl.difffocus.value
            diff_focus_defocused = diff_focus_proper + self.diff_defocus

            img0, h = self.defocus_and_image(difffocus = self.diff_defocus, exp_t = self.exposure_time_image)
                
            if trackmethod == "p":
                shift = self.tracking_by_particlerecog(img0)
                delta_beamshiftcoord = np.matmul(self.calib_beamshift.transform, shift)
                self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                
                bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)
            
                img0, h = self.defocus_and_image(difffocus = self.diff_defocus, exp_t = self.exposure_time_image)

            img0_p = preprocess(img0.astype(np.float))
            scorefromCNN = predict(img0_p)
            self.print_and_log(logger = self.logger, msg = "Score for the DP: {}".format(scorefromCNN))

            crystal_pos, img0_cropped, window_size = self.image_cropper(img = img0, window_size = 0)
            img0var = self.img_var(img0_cropped, crystal_pos)
            appos0 = crystal_pos
            
            self.logger.debug("Tracking method: {}. Initial crystal_pos: {} by find_defocused_image_center.".format(trackmethod, crystal_pos))

        if self.unblank_beam:
            self.ctrl.beamblank = False
            
        if self.mode > 1:
            a_i = self.ctrl.stageposition.a
            
            rotation_range = 70 + abs(a_i)
            rotation_t = rotation_range / rotation_speed
            
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
            time.sleep(0.1)

        i = 1

        numb_robustTrack = 0
        """Turn on and off for crystal movement guess here"""
        self.guess_crystmove = False
        
        """set acquisition time to be around 0.52 s in order to fix the image interval times."""
        acquisition_time = self.expt + 0.02

        self.ctrl.cam.block()
        """To ensure lock got released in the block step."""
        time.sleep(0.1)

        t0 = time.perf_counter()
        self.startangle = a
        
        self.stopEvent.clear()

        while not self.stopEvent.is_set():
            try:
                if i < self.nom_ii:
                    self.image_interval = self.robust_ii
                    numb_robustTrack += 1
                else:
                    self.image_interval = self.nom_ii

                    """If variance changed over 20%, do a robust check to ensure crystal is back"""

                    if imgvar/img0var < 0.5 or imgvar/img0var > 2 or imgscale/imgscale0 > 1.15 or imgscale/imgscale0 < 0.85:
                        self.image_interval = self.robust_ii
                        numb_robustTrack += 1
                    else:
                        self.image_interval = self.nom_ii
                        numb_robustTrack = 0

                if numb_robustTrack > 10:
                    self.image_interval = self.nom_ii
                    img0var = imgvar
                    imgscale0 = imgscale
                    numb_robustTrack = 0

                if i % self.image_interval == 0: ## aim to make this more dynamically adapted...
                    t_start = time.perf_counter()
                    
                    """Guessing the next particle position by simply apply the same beamshift change as previous"""
                    if self.guess_crystmove and i >= self.nom_ii:
                        bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)
    
                    self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper
    
                    image_buffer.append((i, img, h))

                    crystal_pos, img_cropped, _ = self.image_cropper(img = img, window_size = window_size)

                    self.logger.debug("crystal_pos: {} by find_defocused_image_center.".format(crystal_pos))
                    
                    imgvar = self.img_var(img_cropped, crystal_pos)

                    self.logger.debug("Image variance: {}".format(imgvar))
                    
                    """If variance changed over 50%, then the crystal is outside the beam and stop data collection"""
                    if imgvar/img0var < 0.2 or imgvar/img0var > 5:
                        print(imgvar)
                        print("Collection stopping because crystal out of the beam...")
                        self.stopEvent.set()
                    if imgvar < imgvar_threshold:
                        print("Image variance smaller than blank image.")
                        self.stopEvent.set()
                    
                    if trackmethod == "c":
                        
                        cc,err,diffphase = register_translation(img0_cropped,img_cropped)
                        self.logger.debug("Cross correlation result: {}".format(cc))
                        
                        if self.guess_crystmove and i >= self.nom_ii:
                            delta_beamshiftcoord1 = np.matmul(self.calib_beamshift.transform, cc)
                            #print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                            self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord1))
                            bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord1)
                            
                            delta_beamshiftcoord = delta_beamshiftcoord1 + delta_beamshiftcoord
                            
                        else:
                            delta_beamshiftcoord = np.matmul(self.calib_beamshift.transform, cc)
                            #print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                            self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                            bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)
                            
                    elif trackmethod == "p":
                        
                        shift = self.tracking_by_particlerecog(img)
                        delta_beamshiftcoord = np.matmul(self.calib_beamshift.transform, shift)
                        self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                        
                        bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)
                        
                        if shift[0] == 512:
                            self.stopEvent.set()
                            continue
                    
                    if self.check_lens_close_to_limit_warning(lensname="beamshift", lensvalue=bs_x0) or self.check_lens_close_to_limit_warning(lensname="beamshift", lensvalue=bs_y0):
                        self.logger.debug("Beamshift close to limit warning: bs_x0 = {}, bs_y0 = {}".format(bs_x0, bs_y0))
                        self.stopEvent.set()
                    
                    crystal_pos, r = find_defocused_image_center(img)
                    crystal_pos = crystal_pos[::-1]
                    crystal_pos_dif = crystal_pos - appos0
                    apmv = -crystal_pos_dif
                    dpmv = delta_beamshiftcoord @ transform_beamshift_d_
                    R = -transform_imgshift2_foc_ @ transform_imgshift_foc @ transform_imgshift_ + transform_imgshift2_
                    mv = apmv - dpmv @ transform_imgshift_foc @ transform_imgshift_
                    delta_imageshift2coord = np.matmul(mv, np.linalg.inv(R))
                    delta_imageshiftcoord = dpmv @ transform_imgshift_foc - delta_imageshift2coord @ transform_imgshift2_foc_ @ transform_imgshift_foc
                    
                    diff_shift = delta_imageshiftcoord @ transform_imgshift_foc_ + delta_imageshift2coord @ transform_imgshift2_foc_
                    img_shift = delta_imageshiftcoord @ transform_imgshift_ + delta_imageshift2coord @ transform_imgshift2_
                    
                    self.logger.debug("delta imageshiftcoord: {}, delta imageshift2coord: {}".format(delta_imageshiftcoord, delta_imageshift2coord))
                    
                    self.ctrl.imageshift1.set(x = is_x0 - int(delta_imageshiftcoord[0]), y = is_y0 - int(delta_imageshiftcoord[1]))
                    self.ctrl.imageshift2.set(x = is2_x0 - int(delta_imageshift2coord[0]), y = is2_y0 - int(delta_imageshift2coord[1]))
                    
                    is_x0 = is_x0 - int(delta_imageshiftcoord[0])
                    is_y0 = is_y0 - int(delta_imageshiftcoord[1])
                    is2_x0 = is2_x0 - int(delta_imageshift2coord[0])
                    is2_y0 = is2_y0 - int(delta_imageshift2coord[1])
                    
                    if self.check_lens_close_to_limit_warning(lensname="imageshift1", lensvalue=is_x0) or self.check_lens_close_to_limit_warning(lensname="imageshift1", lensvalue=is_y0) or self.check_lens_close_to_limit_warning(lensname="imageshift2", lensvalue=is2_x0) or self.check_lens_close_to_limit_warning(lensname="imageshift2", lensvalue=is2_y0):
                        self.logger.debug("Imageshift close to limit warning: is_x0 = {}, is_y0 = {}, is2_x0 = {}, is2_y0 = {}".format(is_x0, is_y0, is2_x0, is2_y0))
                        self.stopEvent.set()
                    
                    self.logger.debug("Image Interval: {}, Imgvar/Img0var:{}".format(self.image_interval, imgvar/img0var))

                    next_interval = t_start + acquisition_time

                    while time.perf_counter() > next_interval:
                        self.logger.debug("Skipping one image.")
                        next_interval += acquisition_time
                        i += 1

                    diff = next_interval - time.perf_counter()
                    time.sleep(diff)
    
                else:
                    t_start = time.perf_counter()
                    img, h = self.ctrl.getImage(self.expt, header_keys=None)
                    if buffer == []:
                        imgscale0 = np.sum(img)
                    else:
                        imgscale = np.sum(img)
                        self.logger.debug("Image scale variation: {}".format(imgscale/imgscale0))

                    buffer.append((i, img, h))
                    
                    next_interval = t_start + acquisition_time

                    while time.perf_counter() > next_interval:
                        next_interval += acquisition_time
                        self.logger.debug("One image skipped because of too long acquisition or calculation time.")
                        i += 1

                    diff = next_interval - time.perf_counter()
                    time.sleep(diff)
    
                i += 1
                
                if time.perf_counter() - t0 >= rotation_t:
                    self.stopEvent.set()
                    print("Goniometer close to limit!")
                
            except Exception as e:
                print (e)
                self.stopEvent.set()

        t1 = time.perf_counter()

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
        stageposx, stageposy, stageposz, stageposa, stageposb = self.ctrl.stageposition.get()
        rotrange = abs(self.endangle-self.startangle)
        
        print("Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle))
        self.logger.info("Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle))
        
        nframes = i - 1 # i + 1 is not correct since i+=1 was executed before next image is taken???
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collected from {} degree to {} degree.".format(self.startangle, self.endangle))
        self.logger.info("Oscillation angle: {}".format(osangle))
        self.logger.info("Pixel size and actual camera length updated in SMV file headers for DIALS processing.")

        rotation_angle = config.camera.camera_rotation_vs_stage_xy

        self.pixelsize = config.calibration.diffraction_pixeldimensions[camera_length] # px / Angstrom
        self.physical_pixelsize = config.camera.physical_pixelsize # mm
        self.wavelength = config.microscope.wavelength # angstrom
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude
       
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(os.path.join(path, "cRED_log.txt"), "w") as f:
            print(f"Data Collection Time: {now}", file=f)
            print(f"Starting angle: {self.startangle}", file=f)
            print(f"Ending angle: {self.endangle}", file=f)
            print(f"Exposure Time: {self.expt} s", file=f)
            print(f"Spot Size: {spotsize}", file=f)
            print(f"Camera length: {camera_length} mm\n", file=f)
            print(f"Pixelsize: {self.pixelsize} px/Angstrom", file=f)
            print(f"Physical pixelsize: {self.physical_pixelsize} um", file=f)
            print(f"Wavelength: {self.wavelength} Angstrom", file=f)
            print(f"Stretch amplitude: {self.stretch_azimuth} %", file=f)
            print(f"Stretch azimuth: {self.stretch_amplitude} degrees", file=f)
            print(f"Rotation axis: {rotation_angle} radians", file=f)            
            print(f"Oscillation angle: {osangle} degrees", file=f)
            print(f"Number of frames: {len(buffer)}", file=f)
            print(f"Particle found at stage position: x: {stageposx}, y: {stageposy}, z: {stageposz}")

        with open(log_rotaterange, "a") as f:
            f.write("{}\t{}\t{}\t{}\n".format(stageposx, stageposy, stageposz, rotrange))
        
        img_conv = ImgConversion(buffer=buffer, 
                 osc_angle=osangle,
                 start_angle=self.startangle,
                 end_angle=self.endangle,
                 rotation_axis=rotation_angle,
                 acquisition_time=acquisition_time,
                 flatfield=self.flatfield,
                 pixelsize=self.pixelsize,
                 physical_pixelsize=self.physical_pixelsize,
                 wavelength=self.wavelength,
                 stretch_amplitude=self.stretch_amplitude,
                 stretch_azimuth=self.stretch_azimuth
                 )

        img_conv.tiff_writer(pathtiff)
        img_conv.smv_writer(pathsmv)
        img_conv.mrc_writer(pathred)
        img_conv.write_ed3d(pathred)
        img_conv.write_xds_inp(pathsmv)

        img_conv.to_dials(pathsmv)
        msg = {"path": pathsmv,
               "rotrange": rotrange,
               "nframes": nframes,
               "osc": osangle}
        msg_tosend = pickle.dumps(msg)

        if s_c:
            s.send(msg_tosend)
            print("SMVs sent to DIALS for processing.")
        
        self.logger.info("XDS INP file created.")

        if image_buffer:
            drc = os.path.join(path,"tiff_image")
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, "{:05d}.tiff".format(i))
                write_tiff(fn, img, header=h)
        
        self.ctrl.beamblank = False

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

    def update_referencepoint_bs(self, bs, br):
        exposure = 0.01
        binsize = 1
        scale = 1
        self.ctrl.beamshift.set(*bs)
        self.ctrl.brightness.value = br

        img_cent = self.ctrl.getRawImage(exposure=exposure, binsize=binsize)

        if np.mean(img_cent) > 10:

            pixel_cent = np.array(find_beam_center(img_cent)) * binsize / scale

            #print(pixel_cent)

            self.calib_beamshift.reference_shift = bs
            self.calib_beamshift.reference_pixel = pixel_cent

            return self.calib_beamshift.reference_pixel
        else:
            return self.calib_beamshift.reference_pixel

    
    def raster_scan(self):
        from instamatic.experiments.serialed.experiment import get_offsets_in_scan_area
        image_dimensions = config.calibration.mag1_camera_dimensions[self.ctrl.magnification.get()]
        box_x, box_y = image_dimensions
        offsets = get_offsets_in_scan_area(box_x, box_y, self.scan_area, angle = config.camera.camera_rotation_vs_stage_xy)
        self.offsets = offsets * 1000
        
        center_x = self.ctrl.stageposition.x
        center_y = self.ctrl.stageposition.y

        x_zheight = 0
        y_zheight = 0
        
        t = tqdm(self.offsets, desc = "                          ")
        
        for j, (x_offset, y_offset) in enumerate(t):
            x = center_x + x_offset
            y = center_y + y_offset
            
            self.ctrl.stageposition.set(x=x, y=y)
            #print("Stage position: x = {}, y = {}".format(x,y))
            x_change = x - x_zheight
            y_change = y - y_zheight
            dist = np.linalg.norm((x_change, y_change))

            if dist > 50000 or x_zheight*y_zheight == 0 or x_zheight == 999999:
                try:
                    img, h = self.ctrl.getImage(exposure = self.expt, header_keys=None)
                    if img.mean() > 10:
                        self.magnification = self.ctrl.magnification.value
                        crystal_positions = find_crystals_timepix(img, self.magnification, spread=spread, offset=offset)
                        crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                            
                        n_crystals = len(crystal_coords)
                        if n_crystals > 0:
                            print("centering z height...")
                            x_zheight, y_zheight = center_z_height_HYMethod(self.ctrl, spread=spread, offset = offset)
                            if x_zheight != 999999:
                                xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stageposition.get()
                                self.logger.info("Stage position: x = {}, y = {}. Z height adjusted to {}. Tilt angle x {} deg, Tilt angle y {} deg".format(xpoint, ypoint, zpoint, aaa, bbb))
                            else:
                                print("Z height not found.")
                except:
                    print("Something went wrong, unable to adjust height")
                    pass

            self.start_collection_point()
            
            if self.stopEvent_rasterScan.is_set():
                print("Raster Scan stopped manually.")
                break
        
    def start_collection_point(self):
        
        IS1_Neut = self.ctrl.imageshift1.get()
        IS2_Neut = self.ctrl.imageshift2.get()

        path = self.path
        
        if self.scan_area != 0:
            path = path / f"stagepos_{self.stagepos_idx:04d}"
            self.stagepos_idx += 1
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
        #print("Neutral beamshift: from beam_brightness.pkl {}".format(bs))
        self.neutral_diffshift = plastatus
        
        self.calib_beamshift.reference_pixel = self.update_referencepoint_bs(bs, img_brightness)

        #print("Calib_beamshift_referenceshift: {}".format(self.calib_beamshift.reference_shift))
        
        transform_imgshift, c = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = self.diff_defocus, logger = self.logger, mode = 'diff')
        transform_imgshift2, c = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = self.diff_defocus, logger = self.logger, mode = 'diff')
        transform_imgshift_foc, c = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = 0, logger = self.logger, mode = 'diff')
        transform_imgshift2_foc, c = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = 0, logger = self.logger, mode = 'diff')
        transform_beamshift_d, c = load_IS_Calibrations(imageshift = 'BS', ctrl = self.ctrl, diff_defocus= 0, logger = self.logger, mode = 'diff')
        transform_stagepos, c = load_IS_Calibrations(imageshift = 'S', ctrl = self.ctrl, diff_defocus= 0, logger = self.logger, mode = 'mag1')
        
        if self.mode == 3:
            #ready = input("Please make sure that you are in the super user mode and the rotation speed is set via GONIOTOOL! Press ENTER to continue.")
            
            if self.ctrl.mode != 'mag1':
                self.ctrl.mode = 'mag1'
                
            self.ctrl.magnification.value = 2500
            self.ctrl.brightness.value = 65535
            
            header_keys = None

            print("Beamshift reference: {}".format(self.calib_beamshift.reference_shift))
            
            self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])

            #input("Find a good area for investigation. Center the beam using beamshift if beam is not centered. ENTER>>>")
            
            #bs = self.ctrl.beamshift.get()
            #self.calib_beamshift.reference_shift = bs
            #self.neutral_beamshift = bs
            
            self.magnification = self.ctrl.magnification.value

            self.rotation_direction = self.eliminate_backlash_in_tiltx()
            img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
            #img, h = Experiment.apply_corrections(img, h)

            threshold = 10  # ignore black images
            
            if img.mean() > threshold:

                h["exp_magnification"] = 2500

                write_tiff(path / f"Overall_view", img, h)

                crystal_positions = find_crystals_timepix(img, self.magnification, spread=spread, offset=offset)
                crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                
                n_crystals = len(crystal_coords)

                if n_crystals == 0:
                    print("No crystals found in the image. Find another area!")
                    return 0
                
                (beamshiftcoord_0, size_crystal_targeted) = self.center_particle_from_crystalList(crystal_positions, transform_stagepos, self.magnification)
                
                img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
                h["exp_magnification"] = 2500
                write_tiff(path / f"Overall_view", img, h)

                crystal_positions = find_crystals_timepix(img, self.magnification, spread=spread, offset=offset)
                crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                crystal_sizes = [crystal.area_pixel for crystal in crystal_positions]             
                n_crystals = len(crystal_coords)

                if n_crystals == 0:
                    print("No crystals found in the image. Find another area!")
                    return 0
                
                if size_crystal_targeted != 0:
                    try:
                        ind_target = crystal_sizes.index(size_crystal_targeted)
                        crystal_coords[0], crystal_coords[ind_target] = crystal_coords[ind_target], crystal_coords[0]
                        print("Targeted isolated crystal centered is swapped to the first of the list.")
                    except ValueError:
                        print("Lost targeted isolated crystal.")
                        return 0
                
                self.logger.info("{} {} crystals found.".format(datetime.datetime.now(), n_crystals))
                
                k = 0
                
                while not self.stopEvent_rasterScan.is_set():

                    try:
                        self.ctrl.brightness.value = img_brightness

                        #print("{}, {}".format(k, crystal_coords[k]))

                        print("Collecting on crystal {}/{}. Beamshift coordinates: {}".format(k + 1, n_crystals, self.ctrl.beamshift.get()))

                        outfile = path / f"crystal_{k:04d}"
                        comment = "crystal {}".format(k)

                        beamshift_coords = np.array(bs) - np.dot(crystal_coords[k] - self.calib_beamshift.reference_pixel, self.calib_beamshift.transform)
                        self.ctrl.beamshift.set(*beamshift_coords.astype(int))

                        img, h = self.ctrl.getImage(exposure=0.001, comment=comment, header_keys=header_keys)
                        h["exp_magnification"] = 2500
                        write_tiff(path / f"crystal_{k:04d}", img, h)
                        """Sometimes k is out of range error!!!"""

                        if self.isolated(crystal_positions[k], crystal_coords) and crystal_positions[k].isolated and not any(t < 100 for t in crystal_coords[k]) and not any(t > 416 for t in crystal_coords[k]):

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
                            
                            self.rotation_direction = self.eliminate_backlash_in_tiltx()
                            img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
                            h["exp_magnification"] = 2500
                            write_tiff(path / f"Overall_view_{k:04d}", img, h)

                            crystal_positions = find_crystals_timepix(img, self.magnification, spread=spread, offset=offset)
                            crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                            #self.ctrl.brightness.value = img_brightness
                            
                            if n_crystals == 0:
                                print("No crystals found in the image. exitting loop...")
                                break
                            
                            (beamshiftcoord_0, size_crystal_targeted) = self.center_particle_from_crystalList(crystal_positions, transform_stagepos, self.magnification)
                
                            img, h = self.ctrl.getImage(exposure = self.expt, header_keys=header_keys)
                            h["exp_magnification"] = 2500
                            write_tiff(path / f"Overall_view_{k:04d}", img, h)
            
                            crystal_positions = find_crystals_timepix(img, self.magnification, spread=spread, offset=offset)
                            crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                            crystal_sizes = [crystal.area_pixel for crystal in crystal_positions]             
                            n_crystals = len(crystal_coords)
            
                            if n_crystals == 0:
                                print("No crystals found in the image. Find another area!")
                                break
                            
                            if size_crystal_targeted != 0:
                                try:
                                    ind_target = crystal_sizes.index(size_crystal_targeted)
                                    crystal_coords[k+1], crystal_coords[ind_target] = crystal_coords[ind_target], crystal_coords[k+1]
                                    print("{}, {}".format(k+1, crystal_coords[k+1]))
                                    print("Targeted isolated crystal centered is swapped to the next.")
                                except ValueError:
                                    print("Lost targeted isolated crystal.")
                                    break
                            
                        else:
                            print("Crystal {} not isolated: not suitable for cred collection".format(k+1))
                        
                        k = k + 1
                        if k >= n_crystals:
                            break
                    except:
                        traceback.print_exc()
                        self.ctrl.beamblank = False
                        print("Exitting loop...")
                        break
                    
                self.ctrl.mode = 'mag1'
                self.ctrl.brightness.value = 65535
                
                self.ctrl.imageshift1.set(x = IS1_Neut[0], y = IS1_Neut[1])
                self.ctrl.imageshift2.set(x = IS2_Neut[0], y = IS2_Neut[1])
                
                self.ctrl.beamshift.set(x = self.calib_beamshift.reference_shift[0], y = self.calib_beamshift.reference_shift[1])
                
                print("AutocRED with crystal_finder data collection done. Find another area for particles.")

            print(os.listdir(path))
            
            if os.listdir(path) == ['Overall_view.tiff']:
                print("Removing path...")
                shutil.rmtree(path)
                print("Path {} removed since no crystal rotation data was collected.".format(path))
            
            try:
                if len(os.listdir(path)) == 0:
                    os.rmdir(path)
                    print("Path {} removed since it is empty.".format(path))
            except:
                print("Deletion error. Path might have already been deleted.")
                
                    
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
        if self.stopEvent_rasterScan.is_set():
            #print("Raster scan stopper clearing..")
            self.stopEvent_rasterScan.clear()
            
        if self.auto_zheight == False:
            try:
                with open("z-height-adjustment-time.pkl", "rb") as f:
                    t = pickle.load(f)
                    if t - time.clock() > 14400:
                        print("Z-height needs to be updated every session. Readjusting z-height...")
                        x_zheight, y_zheight = center_z_height_HYMethod(self.ctrl, spread=spread, offset = offset)
                        xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stageposition.get()
                        self.logger.info("Stage position: x = {}, y = {}. Z height adjusted to {}. Tilt angle x {} deg, Tilt angle y {} deg".format(xpoint, ypoint, zpoint, aaa, bbb))
                        t = time.clock()
                        with open("z-height-adjustment-time.pkl", "wb") as f:
                            pickle.dump(t, f)
                            
            except:
                input("No z-height adjustment found. Please find an area with particles! Press Enter to continue auto adjustment of z height>>>")
                x_zheight, y_zheight = center_z_height_HYMethod(self.ctrl, spread=spread, offset = offset)
                xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stageposition.get()
                self.logger.info("Stage position: x = {}, y = {}. Z height adjusted to {}. Tilt angle x {} deg, Tilt angle y {} deg".format(xpoint, ypoint, zpoint, aaa, bbb))
                t = time.clock()
                with open("z-height-adjustment-time.pkl", "wb") as f:
                    pickle.dump(t, f)
        else:
            print("Z height adjusting...")
            x_zheight, y_zheight = center_z_height_HYMethod(self.ctrl, spread=spread, offset = offset)
            xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stageposition.get()
            self.logger.info("Stage position: x = {}, y = {}. Z height adjusted to {}. Tilt angle x {} deg, Tilt angle y {} deg".format(xpoint, ypoint, zpoint, aaa, bbb))
            t = time.clock()
            with open("z-height-adjustment-time.pkl", "wb") as f:
                pickle.dump(t, f)
            
        lensPar = self.ctrl.to_dict()
        with open("LensPar.pkl","wb") as f:
            pickle.dump(lensPar, f)

        ## Check DIALS server connection status here

        if self.scan_area == 0:
            self.start_collection_point()
        else:
            self.raster_scan()

        self.stopEvent_rasterScan.clear()

        with open("LensPar.pkl","rb") as f:
            lensPar_i = pickle.load(f)

        self.ctrl.from_dict(lensPar_i)
        self.ctrl.beamblank = True

        print("AutocRED collection done.")
