import os
import datetime
import logging
import numpy as np
import time
from instamatic.processing import ImgConversion
from instamatic import config
from instamatic.formats import write_tiff
from skimage.feature import register_translation
from instamatic.calibrate import CalibBeamShift
from instamatic.calibrate.calibrate_beamshift import calibrate_beamshift
from instamatic.calibrate.calibrate_imageshift12 import Calibrate_Imageshift, Calibrate_Imageshift2
from instamatic.calibrate.center_z import center_z_height
from instamatic.tools import find_defocused_image_center
import pickle
from pathlib import Path
import socket

# degrees to rotate before activating data collection procedure
ACTIVATION_THRESHOLD = 0.2


def load_IS_Calibrations(imageshift, ctrl, diff_defocus = 0):
    if imageshift == 'IS1':
        file = 'ISCalib.pkl'
    elif imageshift == 'IS2':
        file = 'IS2Calib.pkl'
    else:
        print("Wrong input. Input either IS1 or IS2.")
        return 0
    
    try:
        with open(file,'rb') as f:
            transform_imgshift = pickle.load(f)
    except IOError:
        print("No {}, defocus = {} calibration found. Choose the desired defocus value.".format(imageshift, diff_defocus))
        inp = input("Press ENTER when ready.")
        satisfied = "x"
        while satisfied == "x":
            if imageshift == 'IS1':
                transform_imgshift = Calibrate_Imageshift(ctrl, diff_defocus, stepsize = 3000)
            elif imageshift == 'IS2':
                transform_imgshift = Calibrate_Imageshift2(ctrl, diff_defocus, stepsize = 2000)
            with open(file, 'wb') as f:
                pickle.dump(transform_imgshift, f)
            satisfied = input(f"{imageshift}, defocus = {diff_defocus} calibration done. \nPress Enter to continue. Press x to redo calibration.")
            
    return transform_imgshift


class Experiment(object):
    def __init__(self, ctrl, 
                       exposure_time, 
                       exposure_time_image, 
                       stop_event, 
                       enable_image_interval, 
                       enable_autotrack, 
                       enable_fullacred, 
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
        self.flatfield = flatfield

        self.diff_defocus = diff_defocus
        self.image_interval = image_interval
        self.exposure_time_image = exposure_time_image
        
        self.mode = "initial"
        
        self.image_interval_enabled = enable_image_interval
        if enable_image_interval:
            self.image_interval = image_interval
            msg = f"Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.exposure_time_image} s)."
            print(msg)
            self.logger.info(msg)
        else:
            self.image_interval = 99999
            
        self.enable_autotrack = enable_autotrack
        if enable_autotrack:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            print("Image autotrack enabled: every {} frames an image with defocus value {} will be displayed.".format(image_interval, diff_defocus))
            self.mode = "auto"
        
        self.enable_fullacred = enable_fullacred
        if enable_fullacred:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            print("Full autocRED feature enabled: every {} frames an image with defocus value {} will be displayed.".format(image_interval, diff_defocus))
            self.mode = "auto_full"
        
    def start_collection(self):
        a = a0 = self.ctrl.stageposition.a
        spotsize = self.ctrl.spotsize
        
        self.pathtiff = Path(self.path) / "tiff"
        self.pathsmv = Path(self.path) / "SMV"
        self.pathred = Path(self.path) / "RED"
        
        for path in (self.path, self.pathtiff, self.pathsmv, self.pathred):
            if not os.path.exists(path):
                os.makedirs(path)
        
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        self.logger.info("Data collection spot size: {}".format(spotsize))
        
        # TODO: Mostly above is setup, split off into own function

        try:
            self.calib_beamshift = CalibBeamShift.from_file()
        except IOError:
            print("No beam shift calibration result found. Running instamatic.calibrate_beamshift first...\n")
            calib_file = "x"
            while calib_file == "x":
                print("Find a clear area, toggle the beam to the desired defocus value.")
                self.calib_beamshift = calibrate_beamshift(ctrl = self.ctrl)
                print("Beam shift calibration done.")
                calib_file = input("Find your particle, go back to diffraction mode, and press ENTER when ready to continue. Press x to REDO the calibration.")
        self.logger.debug("Transform_beamshift: {}".format(self.calib_beamshift.transform))
        
        buffer = []
        image_buffer = []
        
        clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        clientsocket.connect(('localhost',8090))
        
        print("cREDEXP_Client connected.")
            
        if self.mode == "auto" or self.mode == "auto_full":

            print("Auto tracking feature activated. Please remember to bring sample to proper Z height in order for autotracking to be effective.")
            
            if self.mode == "auto_full":
                ready = input("Please make sure that you are in the super user mode and the rotation speed is set! Press ENTER to continue.")
                
                set_zheight = input("Do you want to try automatic z-height adjustment? y for yes or n for no.\n")
                if set_zheight == "y":
                    center_z_height(self.ctrl)
                    ready = input("Press Enter to start data collection.")
            
            transform_imgshift = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = self.diff_defocus)
            transform_imgshift2 = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = self.diff_defocus)
            transform_imgshift_foc = load_IS_Calibrations(imageshift = 'IS1', ctrl = self.ctrl, diff_defocus = 0)
            transform_imgshift2_foc = load_IS_Calibrations(imageshift = 'IS2', ctrl = self.ctrl, diff_defocus = 0)
            
            ## Since it was right multiplication in matrix fitting, need to use inverse transpose to be able to use np.linalg.solve standard format: Ax = b. x^T A^T = b^T
            transform_imgshift = np.transpose(np.linalg.inv(transform_imgshift))
            transform_imgshift2 = np.transpose(np.linalg.inv(transform_imgshift2))
            transform_imgshift_foc = np.transpose(np.linalg.inv(transform_imgshift_foc))
            transform_imgshift2_foc = np.transpose(np.linalg.inv(transform_imgshift2_foc))
                
            self.logger.debug("Transform_imgshift: {}".format(transform_imgshift))
            self.logger.debug("Transform_imgshift_foc: {}".format(transform_imgshift_foc))
            self.logger.debug("Transform_imgshift2: {}".format(transform_imgshift2))
            self.logger.debug("Transform_imgshift2_foc: {}".format(transform_imgshift2_foc))

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
            
            print("Beamshift: {}, {}".format(bs_x0, bs_y0))
            print("Imageshift1: {}, {}".format(is_x0, is_y0))
            print("Imageshift2: {}, {}".format(is2_x0, is2_y0))
            
            crystal_pos, r = find_defocused_image_center(img0) #find_defocused_image_center crystal position (y,x)
            crystal_pos = crystal_pos[::-1]
            if r[0] <= r[1]:
                window_size = r[0]*2
            else:
                window_size = r[1]*2
                
            window_size = int(window_size/1.414)
            if window_size % 2 == 1:
                window_size = window_size + 1
            
            appos0 = crystal_pos
            print("appos0:{}".format(appos0))
            self.logger.debug("crystal_pos: {} by find_defocused_image_center.".format(crystal_pos))
            
            a1 = int(crystal_pos[0]-window_size/2)
            b1 = int(crystal_pos[0]+window_size/2)
            a2 = int(crystal_pos[1]-window_size/2)
            b2 = int(crystal_pos[1]+window_size/2)
            img0_cropped = img0[a1:b1,a2:b2]
            
        
        if self.mode == "auto_full":
            a_i = self.ctrl.stageposition.a
            self.ctrl.stageposition.set_no_waiting(a = a_i + 40)
            
        
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

        t0 = time.perf_counter()

        while not self.stopEvent.is_set():
            try:
                if self.mode == "auto" or self.mode == "auto_full":
                    if i % self.image_interval == 0: ## aim to make this more dynamically adapted...
                        t_start = time.perf_counter()
                        acquisition_time = (t_start - t0) / (i-1)
        
                        self.ctrl.difffocus.value = diff_focus_defocused
                        img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                        self.ctrl.difffocus.value = diff_focus_proper
        
                        image_buffer.append((i, img, h))
                        print("{} saved to image_buffer".format(i))
    
                        crystal_pos, r = find_defocused_image_center(img)
                        crystal_pos = crystal_pos[::-1]
                        
                        self.logger.debug("crystal_pos: {} by find_defocused_image_center.".format(crystal_pos))
                        print(crystal_pos)
                        a1 = int(crystal_pos[0]-window_size/2)
                        b1 = int(crystal_pos[0]+window_size/2)
                        a2 = int(crystal_pos[1]-window_size/2)
                        b2 = int(crystal_pos[1]+window_size/2)
                        img_cropped = img[a1:b1,a2:b2]
    
                        cc,err,diffphase = register_translation(img0_cropped,img_cropped)
                        print(cc)
                        self.logger.debug("Cross correlation result: {}".format(cc))
                        
                        delta_beamshiftcoord = np.matmul(self.calib_beamshift.transform, cc)
                        print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                        self.logger.debug("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                        self.ctrl.beamshift.set(bs_x0 + delta_beamshiftcoord[0], bs_y0 + delta_beamshiftcoord[1])
                        bs_x0 = bs_x0 + delta_beamshiftcoord[0]
                        bs_y0 = bs_y0 + delta_beamshiftcoord[1]
                        
                        """Retake a defocused image to check the impact of beam shift on defocused DP"""
                        self.ctrl.difffocus.value = diff_focus_defocused
                        img, h = self.ctrl.getImage(self.exposure_time_image, header_keys=None)
                        self.ctrl.difffocus.value = diff_focus_proper
                        
                        crystal_pos, r = find_defocused_image_center(img)
                        crystal_pos = crystal_pos[::-1]
                        print("crystalpos:{}".format(crystal_pos))
                        
                        ##Solve linear equations so that defocused image shift equals 0, as well as focused DP shift equals 0:
                        ##MIS1(DEF) deltaIS1 + MIS2(DEF) deltaIS2 = apmv (the defocused image movement should be apmv so that defocused image comes back to center)
                        ##MIS1 deltaIS1 + MIS2 deltaIS2 = 0 (the focused DP should stay at the same position)
                        ##IMPORTANT!! The optimization result is array*r, so right multiply!!
                        
                        a = np.concatenate((transform_imgshift,transform_imgshift2), axis = 1)
                        b = np.concatenate((transform_imgshift_foc, transform_imgshift2_foc), axis = 1)
                        A = np.concatenate((a,b), axis = 0)
    
                        crystal_pos_dif = crystal_pos - appos0
                        print(crystal_pos_dif)
                        apmv = -crystal_pos_dif
    
                        print("aperture movement: {}".format(apmv))
                        
                        x = np.linalg.solve(A,(apmv[0],apmv[1],0,0))
                        
                        delta_imageshiftcoord = (x[0], x[1])
                        delta_imageshift2coord = (x[2],x[3])
                        
                        print("delta imageshiftcoord: {}, delta imageshift2coord: {}".format(delta_imageshiftcoord, delta_imageshift2coord))
                        
                        self.logger.debug("delta imageshiftcoord: {}, delta imageshift2coord: {}".format(delta_imageshiftcoord, delta_imageshift2coord))
                        
                        self.ctrl.imageshift1.set(x = is_x0 - int(delta_imageshiftcoord[0]), y = is_y0 - int(delta_imageshiftcoord[1]))
                        self.ctrl.imageshift2.set(x = is2_x0 - int(delta_imageshift2coord[0]), y = is2_y0 - int(delta_imageshift2coord[1]))
                        ## the two steps can take ~60 ms per step
                        
                        is_x0 = is_x0 - int(delta_imageshiftcoord[0])
                        is_y0 = is_y0 - int(delta_imageshiftcoord[1])
                        is2_x0 = is2_x0 - int(delta_imageshift2coord[0])
                        is2_y0 = is2_y0 - int(delta_imageshift2coord[1])
                        appos0 = crystal_pos
        
                        next_interval = t_start + acquisition_time
                        # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)
        
                        t = time.perf_counter()
        
                        while time.perf_counter() > next_interval:
                            next_interval += acquisition_time
                            i += 1

                        diff = next_interval - time.perf_counter()
                        time.sleep(diff)
        
                    else:
                        img, h = self.ctrl.getImage(self.expt, header_keys=None)
                        # print i, "Image!"
                        buffer.append((i, img, h))
                        print("{} saved to buffer".format(i))
        
                    i += 1
                
                else:
                    if i % self.image_interval == 0:
                        t_start = time.perf_counter()
                        acquisition_time = (t_start - t0) / (i-1)
        
                        self.ctrl.difffocus.value = diff_focus_defocused
                        img, h = self.ctrl.getImage(self.expt / 5.0, header_keys=None)
                        self.ctrl.difffocus.value = diff_focus_proper
        
                        image_buffer.append((i, img, h))
        
                        next_interval = t_start + acquisition_time
                        # print i, "BLOOP! {:.3f} {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time, t_start-t0)
        
                        t = time.perf_counter()
        
                        while time.perf_counter() > next_interval:
                            next_interval += acquisition_time
                            i += 1
                            # print i, "SKIP!  {:.3f} {:.3f}".format(next_interval-t_start, acquisition_time)
        
                        #while time.time() < next_interval:
                            #time.sleep(0.001)
                        diff = next_interval - time.perf_counter()
                        time.sleep(diff)
        
                    else:
                        img, h = self.ctrl.getImage(self.expt, header_keys=None)
                        # print i, "Image!"
                        buffer.append((i, img, h))
        
                    i += 1
                    
                clientsocket.send("s".encode())
                buf = clientsocket.recv(1024)
                receiving = pickle.loads(buf)
                print(receiving)
                if abs(receiving[3]) > 60:
                    self.stopEvent.set()
                
            except Exception as e:
                print (e)
                self.stopEvent.set()

        t1 = time.perf_counter()

        self.ctrl.cam.unblock()
        if self.mode == "auto_full":
            self.ctrl.stageposition.stop_stagemovement()
            
        if self.camtype == "simulate":
            self.endangle = self.startangle + np.random.random()*50
            camera_length = 300
        else:
            self.endangle = self.ctrl.stageposition.a
            camera_length = int(self.ctrl.magnification.get())

        if self.unblank_beam:
            print("Blanking beam")
            self.ctrl.beamblank = True
            
        self.ctrl.imageshift1.set(x = is1_init[0], y = is1_init[1])
        self.ctrl.imageshift2.set(x = is2_init[0], y = is2_init[1])

        # TODO: all the rest here is io+logistics, split off in to own function

        print("Rotated {:.2f} degrees from {:.2f} to {:.2f}".format(abs(self.endangle-self.startangle), self.startangle, self.endangle))
        #self.ctrl.stageposition.set_no_waiting(a = a_i)
        nframes = i + 1 # len(buffer) can lie in case of frame skipping
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

        self.logger.info("Data collection camera length: {} mm".format(camera_length))
        self.logger.info("Data collected from {} degree to {} degree.".format(self.startangle, self.endangle))
        self.logger.info("Oscillation angle: {}".format(osangle))
        self.logger.info("Pixel size and actual camera length updated in SMV file headers for DIALS processing.")
        
        with open(os.path.join(self.path, "cRED_log.txt"), "w") as f:
            f.write("Data Collection Time: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("Starting angle: {}\n".format(self.startangle))
            f.write("Ending angle: {}\n".format(self.endangle))
            f.write("Exposure Time: {} s\n".format(self.expt))
            f.write("Spot Size: {}\n".format(spotsize))
            f.write("Camera length: {} mm\n".format(camera_length))
            f.write("Oscillation angle: {} degrees\n".format(osangle))
            f.write("Number of frames: {}\n".format(len(buffer)))

        rotation_angle = config.microscope.camera_rotation_vs_stage_xy

        img_conv = ImgConversion.ImgConversion(buffer=buffer, 
                 camera_length=camera_length,
                 osc_angle=osangle,
                 start_angle=self.startangle,
                 end_angle=self.endangle,
                 rotation_axis=rotation_angle,
                 acquisition_time=acquisition_time,
                 resolution_range=(20, 0.8),
                 flatfield=self.flatfield)
        
        img_conv.tiff_writer(self.pathtiff)
        img_conv.smv_writer(self.pathsmv)
        img_conv.write_ed3d(self.pathred)
        img_conv.mrc_writer(self.pathred)
        img_conv.write_xds_inp(self.pathsmv)
        self.logger.info("XDS INP file created.")

        if image_buffer:
            drc = os.path.join(self.path,"tiff_image")
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, "{:05d}.tiff".format(i))
                write_tiff(fn, img, header=h)

        print("Data Collection and Conversion Done.")
