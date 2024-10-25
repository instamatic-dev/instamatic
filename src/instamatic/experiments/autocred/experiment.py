from __future__ import annotations

import datetime
import json
import os
import pickle
import shutil
import socket
import time
import traceback
from pathlib import Path

import numpy as np
from scipy import ndimage
from skimage.registration import phase_cross_correlation
from tqdm.auto import tqdm

from instamatic import config
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam
from instamatic.calibrate.calibrate_beamshift import calibrate_beamshift
from instamatic.calibrate.calibrate_imageshift12 import (
    Calibrate_Beamshift_D,
    Calibrate_Beamshift_D_Defoc,
    Calibrate_Imageshift,
    Calibrate_Imageshift2,
    Calibrate_Stage,
)
from instamatic.calibrate.center_z import center_z_height_HYMethod
from instamatic.calibrate.filenames import *
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.formats import write_tiff
from instamatic.neural_network import predict, preprocess
from instamatic.processing.find_crystals import find_crystals_timepix
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion
from instamatic.tools import find_beam_center, find_defocused_image_center

# SerialRED:
#  Currently only working if live view can be read directly from camera via Python API
#  Extensively tested on a JEOL 2100 LaB6 TEM with a Timepix camera.
#  Imgvar can be compared with the first defocused image.
#  If other particles move in, the variance will be at least 50% different

# spread, offset: parameters for find_crystals_timepix
# spread = 2  # sometimes crystals still are not so isolated using number 0.6 as suggested.
# offset = 15  # The number needs to be smaller when the contrast of the crystals is low.
# imgvar_threshold = 600

date = datetime.datetime.now().strftime('%Y-%m-%d')
log_rotaterange = config.locations['logs'] / f'Rotrange_stagepos_{date}.log'
log_iscalibs = config.locations['logs'] / f'ImageShift_LOGS_{date}'
log_iscalibs.mkdir(exist_ok=True)

if not os.path.isfile(log_rotaterange):
    with open(log_rotaterange, 'a') as f:
        f.write('x\ty\tz\trotation range\n')

use_dials = config.settings.use_indexing_server_exe
use_vm = config.settings.use_VM_server_exe


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
        elif imageshift == 'BS' and diff_defocus == 0:
            file = CALIB_BEAMSHIFT_DP
        elif imageshift == 'BS' and diff_defocus != 0:
            file = CALIB_BEAMSHIFT_DP_DEFOC
        elif imageshift == 'S':
            file = CALIB_STAGE
    else:
        print('Wrong input. Mode can either be mag1 or diff for calibration!')
        return 0

    try:
        if imageshift == 'S':
            with open(config.locations['logs'] / file, 'rb') as f:
                transform_imgshift, c = pickle.load(f)
        else:
            with open(log_iscalibs / file, 'rb') as f:
                transform_imgshift, c = pickle.load(f)
    except BaseException:
        print(
            f'No {imageshift}, defocus = {diff_defocus} calibration found. Choose the desired defocus value.'
        )
        inp = input('Press ENTER when ready.')
        if ctrl.mode != mode:
            ctrl.mode.set(mode)
        satisfied = 'x'
        while satisfied == 'x':
            if imageshift == 'IS1' and diff_defocus != 0:
                mag_calib = ctrl.magnification.value
                s_calib = int(200.0 / mag_calib * 1500)
                transform_imgshift, c = Calibrate_Imageshift(
                    ctrl, diff_defocus, stepsize=s_calib, logger=logger, key='IS1'
                )
            elif imageshift == 'IS1' and diff_defocus == 0:
                mag_calib = ctrl.magnification.value
                s_calib = int(200.0 / mag_calib * 1000)
                transform_imgshift, c = Calibrate_Imageshift(
                    ctrl, diff_defocus, stepsize=s_calib, logger=logger, key='IS1'
                )
            elif imageshift == 'IS2':
                mag_calib = ctrl.magnification.value
                s_calib = int(200.0 / mag_calib * 750)
                transform_imgshift, c = Calibrate_Imageshift2(
                    ctrl, diff_defocus, stepsize=s_calib, logger=logger
                )
            elif imageshift == 'BS' and diff_defocus == 0:
                mag_calib = ctrl.magnification.value
                s_calib = int(250.0 / mag_calib * 100)
                transform_imgshift, c = Calibrate_Beamshift_D(
                    ctrl, stepsize=s_calib, logger=logger
                )
            elif imageshift == 'BS' and diff_defocus != 0:
                mag_calib = ctrl.magnification.value
                s_calib = int(250.0 / mag_calib * 100)
                transform_imgshift, c = Calibrate_Beamshift_D_Defoc(
                    ctrl, diff_defocus, stepsize=s_calib, logger=logger
                )

            elif imageshift == 'S':
                mag_calib = ctrl.magnification.value
                s_calib = int(2500.0 / mag_calib * 1000)
                transform_imgshift, c = Calibrate_Stage(ctrl, stepsize=s_calib, logger=logger)
            with open(log_iscalibs / file, 'wb') as f:
                pickle.dump([transform_imgshift, c], f)
            satisfied = input(
                f'{imageshift}, defocus = {diff_defocus} calibration done. \nPress Enter to continue. Press x to redo calibration.'
            )

    return transform_imgshift, c


class Experiment(ExperimentBase):
    def __init__(
        self,
        ctrl,
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
        angle_activation,
        spread,
        offset,
        rotrange,
        backlash_killer,
        rotation_speed,
        unblank_beam=False,
        path=None,
        log=None,
        flatfield=None,
        image_interval=99999,
        diff_defocus=0,
    ):
        super().__init__()
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
        # self.autocenterDP = autocenterDP
        self.angle_activation = angle_activation
        self.spread = spread
        self.offset = offset
        self.rotrangelimit = rotrange
        self.backlash_killer = backlash_killer
        self.rotation_speed = rotation_speed

        self.calibdir = self.path.parent / 'calib'

        self.verbose = False
        self.number_crystals_scanned = 0
        self.number_exp_performed = 0

        if not os.path.exists(self.calibdir):
            os.makedirs(self.calibdir)

        self.image_interval_enabled = enable_image_interval
        if enable_image_interval:
            self.image_interval = image_interval
            msg = f'Image interval enabled: every {self.image_interval} frames an image with defocus {self.diff_defocus} will be displayed (t={self.exposure_time_image} s).'
            if self.verbose:
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
            msg = f'Full autocRED feature with auto crystal finder enabled: every {image_interval} frames an image with defocus value {diff_defocus} will be displayed.'
            self.mode = 3

        elif enable_fullacred:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            msg = f'Full autocRED feature enabled: every {image_interval} frames an image with defocus value {diff_defocus} will be displayed.'
            self.mode = 2

        elif enable_autotrack:
            self.diff_defocus = diff_defocus
            self.image_interval = image_interval
            msg = f'Image autotrack enabled: every {image_interval} frames an image with defocus value {diff_defocus} will be displayed.'
            self.mode = 1

        if self.verbose:
            print(msg)

        if use_dials:
            self.s = socket.socket()
            dials_host = config.settings.indexing_server_host
            dials_port = config.settings.indexing_server_port
            try:
                self.s.connect((dials_host, dials_port))
                print('DIALS server connected for autocRED.')
                self.s_c = 1
            except BaseException:
                print('Is DIALS server running? Connection failed.')
                self.s_c = 0

        if use_vm:
            self.s2 = socket.socket()
            vm_host = config.settings.VM_server_host
            vm_port = config.settings.VM_server_port
            try:
                self.s2.connect((vm_host, vm_port))
                print('VirtualBox server connected for autocRED.')
                self.s2_c = 1
            except BaseException:
                print('Is VM server running? Connection failed.')
                self.s2_c = 0

    def image_cropper(self, img, window_size=0):
        crystal_pos, r = find_defocused_image_center(
            img
        )  # find_defocused_image_center crystal position (y,x)
        crystal_pos = crystal_pos[::-1]

        if window_size == 0:
            if r[0] <= r[1]:
                window_size = r[0] * 2
            else:
                window_size = r[1] * 2

            window_size = int(window_size / 1.414)
            if window_size % 2 == 1:
                window_size = window_size + 1

        a1 = int(crystal_pos[0] - window_size / 2)
        b1 = int(crystal_pos[0] + window_size / 2)
        a2 = int(crystal_pos[1] - window_size / 2)
        b2 = int(crystal_pos[1] + window_size / 2)

        img_cropped = img[a1:b1, a2:b2]
        return crystal_pos, img_cropped, window_size

    def hysteresis_check(self, n_cycle=4):
        print('Relaxing beam...')
        modes = ['mag1', 'samag', 'diff']
        current_mode = self.ctrl.mode.get()
        mode_index = modes.index(current_mode)

        for i in range(n_cycle):
            self.ctrl.mode.set(modes[(mode_index + 1) % 3])
            time.sleep(0.5)
            self.ctrl.mode.set(modes[(mode_index + 2) % 3])
            time.sleep(0.5)
            self.ctrl.mode.set(modes[mode_index])
            time.sleep(0.5)

        print('Beam relaxing done.')

    def check_lens_close_to_limit_warning(self, lensname, lensvalue, MAX=65535, threshold=5000):
        warn = 0
        if MAX - lensvalue < threshold or lensvalue < threshold:
            warn = 1
            if self.verbose:
                print(f'Warning: {lensname} close to limit!')
        return warn

    def img_var(self, img, apert_pos):
        apert_pos = [int(apert_pos[0]), int(apert_pos[1])]
        window_size = img.shape[0]
        half_w = int(window_size / 2)
        x_range = range(apert_pos[0] - half_w, apert_pos[0] + half_w)
        y_range = range(apert_pos[1] - half_w, apert_pos[1] + half_w)

        if not any(x in range(255, 261) for x in x_range) and not any(
            y in range(255, 261) for y in y_range
        ):
            return np.var(img)
        else:
            if any(x in range(255, 261) for x in x_range):
                indx = []
                for px in range(255, 261):
                    try:
                        indx.append(x_range.index(px))
                    except BaseException:
                        pass

                img = np.delete(img, indx, 0)

            if any(y in range(255, 261) for y in y_range):
                indy = []
                for px in range(255, 261):
                    try:
                        indy.append(y_range.index(px))
                    except BaseException:
                        pass

                img = np.delete(img, indy, 1)

            return np.var(img)

    def check_img_outsidebeam_byscale(self, img1_scale, img2_scale):
        """`img1` is the original image for reference, `img2` is the new
        image."""
        if img2_scale / img1_scale < 0.5 or img2_scale / img1_scale > 2:
            return 1
        else:
            return 0

    def eliminate_backlash_in_tiltx(self):
        a_i = self.ctrl.stage.a
        if a_i < 0:
            self.ctrl.stage.set(a=a_i + self.backlash_killer, wait=True)
            # print("Rotation positive!")
            return 0
        else:
            self.ctrl.stage.set(a=a_i - self.backlash_killer, wait=True)
            # print("Rotation negative!")
            return 1

    def center_particle_ofinterest(self, pos_arr, transform_stagepos):
        """Used to center the particle of interest in the view to minimize
        usage of lens."""
        transform_stagepos_ = np.linalg.inv(transform_stagepos)
        if pos_arr[0] < 200 or pos_arr[0] > 316 or pos_arr[1] < 200 or pos_arr[1] > 316:
            _x0 = self.ctrl.stage.x
            _y0 = self.ctrl.stage.y

            displacement = np.subtract((258, 258), pos_arr)
            mag = self.ctrl.magnification.value

            s = config.calibration['mag1']['pixelsize'][mag] / 1000  # nm -> um
            # print("scaling facor: {} um per px".format(s))

            mvmt = s * displacement
            mvmt_x, mvmt_y = np.dot(1000 * mvmt, transform_stagepos_)

            self.ctrl.stage.set(x=_x0 + mvmt_y, y=_y0 - mvmt_x)

        else:
            pass

    def center_particle_from_crystalList(
        self, crystal_positions, transform_stagepos, magnification, beamsize
    ):
        n_crystals = len(crystal_positions)
        if n_crystals == 0:
            self.print_and_del('No crystal found on image!')
            return (0, 0)

        else:
            beam_area = beamsize**2

            for crystal in crystal_positions:
                if crystal.isolated:
                    self.center_particle_ofinterest((crystal.x, crystal.y), transform_stagepos)
                    crystalsize = crystal.area_pixel
                    # print("crystal size: {}".format(crystalsize))
                    img, h = self.ctrl.get_image(exposure=self.expt, header_keys=None)

                    crystal_positions_new = find_crystals_timepix(
                        img,
                        magnification=self.magnification,
                        spread=self.spread,
                        offset=self.offset,
                    )

                    n_crystals_new = len(crystal_positions_new)
                    # print(crystal_positions_new)
                    if n_crystals_new == 0:
                        self.print_and_del('No crystal found after centering...')
                        return (0, 0)

                    else:
                        # print("Start looping.")
                        for crystal in crystal_positions_new:
                            if (
                                crystal.isolated
                                and crystalsize * 0.9 <= crystal.area_pixel <= crystalsize * 1.1
                            ):
                                self.print_and_del(
                                    f'Crystal that has been centered is found at {crystal.x}, {crystal.y}.'
                                )
                                beamshift_coords = self.calib_beamshift.pixelcoord_to_beamshift(
                                    (crystal.x, crystal.y)
                                )

                                return (beamshift_coords, crystalsize)
                            else:
                                return (0, 0)

                else:
                    return (0, 0)

    def isolated(self, c, crystalpositions, thresh=100):
        distances = []
        if len(crystalpositions) == 1:
            return True
        else:
            for allcryst in crystalpositions:
                distvec = np.subtract(allcryst, (c.x, c.y))
                dist = np.linalg.norm(distvec)
                if dist != 0:
                    distances.append(dist)

            if min(distances) > thresh:  # in pixels
                return True
            else:
                return False

    def find_crystal_center(self, img_c, window_size, gauss_window=4):
        mn = np.min(img_c)
        mx = np.max(img_c)

        sel = (img_c > l + 0.1 * (mx - mn)) & (img_c < mx - 0.4 * (h - mn))
        blurred = ndimage.filters.gaussian_filter(sel.astype(float), gauss_window)
        x, y = np.unravel_index(np.argmax(blurred, axis=None), blurred.shape)
        return (y, x)

    def find_crystal_center_fromhist(self, img, bins=20, plot=False, gauss_window=5):
        h, b = np.histogram(img, bins)
        sel = (img > b[1]) & (img < b[8])

        blurred = ndimage.filters.gaussian_filter(sel.astype(float), gauss_window)
        x, y = np.unravel_index(np.argmax(blurred, axis=None), blurred.shape)
        if plot:
            plt.imshow(sel)
            plt.scatter(y, x)
            plt.show()
        return (y, x)

    def tracking_by_particlerecog(self, img, magnification=2500, spread=6, offset=18):
        crystal_pos, r = find_defocused_image_center(
            img
        )  # find_defocused_image_center crystal position (y,x)
        crystal_pos = crystal_pos[::-1]

        window_size = 0

        if window_size == 0:
            if r[0] <= r[1]:
                window_size = r[0] * 2
            else:
                window_size = r[1] * 2

            # window_size = int(window_size/1.414)
            if window_size % 2 == 1:
                window_size = window_size + 1

        a1 = int(crystal_pos[0] - window_size / 2)
        b1 = int(crystal_pos[0] + window_size / 2)
        a2 = int(crystal_pos[1] - window_size / 2)
        b2 = int(crystal_pos[1] + window_size / 2)

        img_cropped = img[a1:b1, a2:b2]

        # crystalpositions = find_crystals_timepix(img_cropped, magnification = magnification, spread=spread, offset = offset)
        # crystalposition = self.find_crystal_center(img_cropped, window_size)
        crystalposition = self.find_crystal_center_fromhist(img_cropped)
        center = (window_size / 2, window_size / 2)

        # if len(crystalpositions) == 1:
        # crystalxy = (crystalpositions[0].x, crystalpositions[0].y)
        shift = np.subtract(center, crystalposition)
        # elif len(crystalpositions) > 1:
        #    areas = [crystal.area_pixel for crystal in crystalpositions]
        #    idx = areas.index(max(areas))
        #    crystalxy = (crystalpositions[idx].x, crystalpositions[idx].y)
        #    shift = np.subtract(center, crystalxy)
        # else:
        #    print("Crystal lost.")
        #    shift = np.array((512, 512))

        return tuple(shift[::-1])

    def setandupdate_bs(self, bs_x0, bs_y0, delta_beamshiftcoord1):
        self.ctrl.beamshift.set(
            bs_x0 + delta_beamshiftcoord1[0], bs_y0 + delta_beamshiftcoord1[1]
        )
        bs_x0 = bs_x0 + delta_beamshiftcoord1[0]
        bs_y0 = bs_y0 + delta_beamshiftcoord1[1]
        return bs_x0, bs_y0

    def defocus_and_image(self, difffocus, exp_t):
        diff_focus_proper = self.ctrl.difffocus.value
        diff_focus_defocused = diff_focus_proper + difffocus
        self.ctrl.difffocus.value = diff_focus_defocused

        img0, h = self.ctrl.get_image(exp_t, header_keys=None)
        self.ctrl.difffocus.value = diff_focus_proper
        return img0, h

    def print_and_log(self, logger, msg):
        print(msg)
        logger.debug(msg)

    def print_and_del(self, msg):
        print('\033[k', msg, end='\r')

    def imagevar_blank_estimator(self, brightness, cycle=3):
        # previous_mode = self.ctrl.mode.get()
        self.ctrl.mode.set('mag1')
        self.ctrl.brightness.value = brightness

        input(
            'Please move your stage to a blank area for image variance calculation. Do not change brightness. Press ENTER when ready.'
        )
        img_var_est = []
        beamsize_est = []
        for i in range(0, cycle):
            img, h = self.ctrl.get_image(self.exposure_time_image, header_keys=None)
            crystal_pos, img0_cropped, window_size = self.image_cropper(img=img, window_size=0)
            v = self.img_var(img0_cropped, crystal_pos)
            print(f'blank image variance: {v}')
            img_var_est.append(v)
            beamsize_est.append(window_size)

        image_var = np.average(img_var_est)
        beamsize_avg = np.average(window_size)

        self.ctrl.mode.set('samag')
        self.ctrl.mode.set('diff')
        return image_var, beamsize_avg

    def auto_cred_collection(
        self,
        path,
        pathtiff,
        pathsmv,
        pathred,
        transform_imgshift,
        transform_imgshift2,
        transform_imgshift_foc,
        transform_imgshift2_foc,
        transform_beamshift_d,
        transform_beamshift_d_defoc,
        calib_beamshift,
    ):
        """track method
        p: particle recognition
        c: cross correlation"""

        trackmethod = 'p'

        for paths in (path, pathtiff, pathsmv, pathred):
            if not os.path.exists(paths):
                os.makedirs(paths)

        a = a0 = self.ctrl.stage.a
        spotsize = self.ctrl.spotsize

        if self.mode == 1:
            self.logger.info('AutocRED experiment starting...')
        elif self.mode == 2:
            self.logger.info('Full AutocRED experiment starting...')
        elif self.mode == 3:
            self.logger.info('Full AutocRED with auto crystal finder experiment starting...')
        self.logger.info(
            'Data recording started at: {}'.format(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        )
        self.logger.info(f'Data saving path: {path}')
        self.logger.info(f'Data collection exposure time: {self.expt} s')
        self.logger.info(f'Data collection spot size: {spotsize}')
        # TODO: Mostly above is setup, split off into own function

        buffer = []
        image_buffer = []

        if self.mode > 0:
            if self.verbose:
                print(
                    'Auto tracking feature activated. Please remember to bring sample to proper Z height in order for autotracking to be effective.'
                )

            transform_imgshift_ = np.linalg.inv(transform_imgshift)
            transform_imgshift2_ = np.linalg.inv(transform_imgshift2)
            transform_imgshift_foc_ = np.linalg.inv(transform_imgshift_foc)
            transform_imgshift2_foc_ = np.linalg.inv(transform_imgshift2_foc)

            transform_beamshift_d_ = np.linalg.inv(transform_beamshift_d)

            self.logger.debug(f'Transform_imgshift: {transform_imgshift}')
            self.logger.debug(f'Transform_imgshift_foc: {transform_imgshift_foc}')
            self.logger.debug(f'Transform_imgshift2: {transform_imgshift2}')
            self.logger.debug(f'Transform_imgshift2_foc: {transform_imgshift2_foc}')

            if self.ctrl.mode != 'diff':
                self.ctrl.mode.set('samag')
                self.ctrl.mode.set('diff')

            bs_x0, bs_y0 = self.ctrl.beamshift.get()
            is_x0, is_y0 = self.ctrl.imageshift1.get()
            ds_x0, ds_y0 = self.ctrl.diffshift.get()
            is2_x0, is2_y0 = self.ctrl.imageshift2.get()

            is1_init = (is_x0, is_y0)
            is2_init = (is2_x0, is2_y0)

            self.logger.debug(f'Initial Beamshift: {bs_x0}, {bs_y0}')
            self.logger.debug(f'Initial Imageshift1: {is_x0}, {is_y0}')
            self.logger.debug(f'Initial Imageshift2: {is2_x0}, {is2_y0}')

            diff_focus_proper = self.ctrl.difffocus.value
            diff_focus_defocused = diff_focus_proper + self.diff_defocus

            img0, h = self.defocus_and_image(
                difffocus=self.diff_defocus, exp_t=self.exposure_time_image
            )

            img0_p = preprocess(img0.astype(float))
            scorefromCNN = predict(img0_p)
            # self.print_and_log(logger = self.logger, msg = "Score for the DP: {}".format(scorefromCNN))
            self.logger.debug(f'Score for the DP: {scorefromCNN}')

            crystal_pos, img0_cropped, window_size = self.image_cropper(img=img0, window_size=0)
            img0var = self.img_var(img0_cropped, crystal_pos)
            appos0 = crystal_pos

            self.logger.debug(
                f'Tracking method: {trackmethod}. Initial crystal_pos: {crystal_pos} by find_defocused_image_center.'
            )

        if self.unblank_beam:
            self.ctrl.beam.unblank()

        if self.mode > 1:
            a_i = self.ctrl.stage.a

            rotation_range = self.rotrangelimit + abs(a_i)
            rotation_t = rotation_range / self.rotation_speed

            try:
                if self.rotation_direction == 0:
                    self.ctrl.stage.set(a=a_i + rotation_range, wait=False)
                else:
                    self.ctrl.stage.set(a=a_i - rotation_range, wait=False)
            except BaseException:
                if a_i < 0:
                    self.ctrl.stage.set(a=a_i + rotation_range, wait=False)
                else:
                    self.ctrl.stage.set(a=a_i - rotation_range, wait=False)

        if self.camtype == 'simulate':
            self.startangle = a
        else:
            time.sleep(self.angle_activation)

        i = 1

        numb_robustTrack = 0
        """Turn on and off for crystal movement guess here."""
        self.guess_crystmove = False
        """Set acquisition time to be around 0.52 s in order to fix the image
        interval times."""
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
                    """If variance changed over 20%, do a robust check to
                    ensure crystal is back."""

                    if (
                        imgvar / img0var < 0.5
                        or imgvar / img0var > 2
                        or imgscale / imgscale0 > 1.15
                        or imgscale / imgscale0 < 0.85
                    ):
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

                if i % self.image_interval == 0:  # aim to make this more dynamically adapted...
                    t_start = time.perf_counter()
                    """Guessing the next particle position by simply apply the
                    same beamshift change as previous."""
                    if self.guess_crystmove and i >= self.nom_ii:
                        bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)

                    self.ctrl.difffocus.value = diff_focus_defocused
                    img, h = self.ctrl.get_image(self.exposure_time_image, header_keys=None)
                    self.ctrl.difffocus.value = diff_focus_proper

                    image_buffer.append((i, img, h))

                    crystal_pos, img_cropped, _ = self.image_cropper(
                        img=img, window_size=window_size
                    )

                    self.logger.debug(
                        f'crystal_pos: {crystal_pos} by find_defocused_image_center.'
                    )

                    imgvar = self.img_var(img_cropped, crystal_pos)

                    self.logger.debug(f'Image variance: {imgvar}')
                    """If variance changed over 50%, then the crystal is
                    outside the beam and stop data collection."""
                    if imgvar / img0var < 0.2 or imgvar / img0var > 5:
                        self.print_and_del(
                            'Collection stopping because crystal out of the beam...'
                        )
                        self.stopEvent.set()
                    if imgvar < self.imgvar_threshold:
                        self.print_and_del('Image variance smaller than blank image.')
                        self.stopEvent.set()

                    if trackmethod == 'c':
                        cc, err, diffphase = phase_cross_correlation(img0_cropped, img_cropped)
                        self.logger.debug(f'Cross correlation result: {cc}')

                        if self.guess_crystmove and i >= self.nom_ii:
                            delta_beamshiftcoord1 = np.matmul(
                                self.calib_beamshift.transform, cc
                            )
                            # print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                            self.logger.debug(
                                f'Beam shift coordinates: {delta_beamshiftcoord1}'
                            )
                            bs_x0, bs_y0 = self.setandupdate_bs(
                                bs_x0, bs_y0, delta_beamshiftcoord1
                            )

                            delta_beamshiftcoord = delta_beamshiftcoord1 + delta_beamshiftcoord

                        else:
                            delta_beamshiftcoord = np.matmul(self.calib_beamshift.transform, cc)
                            # print("Beam shift coordinates: {}".format(delta_beamshiftcoord))
                            self.logger.debug(f'Beam shift coordinates: {delta_beamshiftcoord}')
                            bs_x0, bs_y0 = self.setandupdate_bs(
                                bs_x0, bs_y0, delta_beamshiftcoord
                            )

                    elif trackmethod == 'p':
                        shift = self.tracking_by_particlerecog(img)
                        delta_beamshiftcoord = np.matmul(shift, transform_beamshift_d_defoc)
                        self.logger.debug(f'Beam shift coordinates: {delta_beamshiftcoord}')

                        bs_x0, bs_y0 = self.setandupdate_bs(bs_x0, bs_y0, delta_beamshiftcoord)

                        if shift[0] == 512:
                            self.stopEvent.set()
                            continue

                    if self.check_lens_close_to_limit_warning(
                        lensname='beamshift', lensvalue=bs_x0
                    ) or self.check_lens_close_to_limit_warning(
                        lensname='beamshift', lensvalue=bs_y0
                    ):
                        self.logger.debug(
                            f'Beamshift close to limit warning: bs_x0 = {bs_x0}, bs_y0 = {bs_y0}'
                        )
                        self.stopEvent.set()

                    crystal_pos, r = find_defocused_image_center(img)
                    crystal_pos = crystal_pos[::-1]
                    crystal_pos_dif = crystal_pos - appos0
                    apmv = -crystal_pos_dif
                    dpmv = delta_beamshiftcoord @ transform_beamshift_d_
                    R = (
                        -transform_imgshift2_foc_ @ transform_imgshift_foc @ transform_imgshift_
                        + transform_imgshift2_
                    )
                    mv = apmv - dpmv @ transform_imgshift_foc @ transform_imgshift_
                    delta_imageshift2coord = np.matmul(mv, np.linalg.inv(R))
                    delta_imageshiftcoord = (
                        dpmv @ transform_imgshift_foc
                        - delta_imageshift2coord
                        @ transform_imgshift2_foc_
                        @ transform_imgshift_foc
                    )

                    diff_shift = (
                        delta_imageshiftcoord @ transform_imgshift_foc_
                        + delta_imageshift2coord @ transform_imgshift2_foc_
                    )
                    img_shift = (
                        delta_imageshiftcoord @ transform_imgshift_
                        + delta_imageshift2coord @ transform_imgshift2_
                    )

                    self.logger.debug(
                        f'delta imageshiftcoord: {delta_imageshiftcoord}, delta imageshift2coord: {delta_imageshift2coord}'
                    )

                    self.ctrl.imageshift1.set(
                        x=is_x0 - int(delta_imageshiftcoord[0]),
                        y=is_y0 - int(delta_imageshiftcoord[1]),
                    )
                    self.ctrl.imageshift2.set(
                        x=is2_x0 - int(delta_imageshift2coord[0]),
                        y=is2_y0 - int(delta_imageshift2coord[1]),
                    )

                    is_x0 = is_x0 - int(delta_imageshiftcoord[0])
                    is_y0 = is_y0 - int(delta_imageshiftcoord[1])
                    is2_x0 = is2_x0 - int(delta_imageshift2coord[0])
                    is2_y0 = is2_y0 - int(delta_imageshift2coord[1])

                    if (
                        self.check_lens_close_to_limit_warning(
                            lensname='imageshift1', lensvalue=is_x0
                        )
                        or self.check_lens_close_to_limit_warning(
                            lensname='imageshift1', lensvalue=is_y0
                        )
                        or self.check_lens_close_to_limit_warning(
                            lensname='imageshift2', lensvalue=is2_x0
                        )
                        or self.check_lens_close_to_limit_warning(
                            lensname='imageshift2', lensvalue=is2_y0
                        )
                    ):
                        self.logger.debug(
                            f'Imageshift close to limit warning: is_x0 = {is_x0}, is_y0 = {is_y0}, is2_x0 = {is2_x0}, is2_y0 = {is2_y0}'
                        )
                        self.stopEvent.set()

                    self.logger.debug(
                        f'Image Interval: {self.image_interval}, Imgvar/Img0var:{imgvar / img0var}'
                    )

                    next_interval = t_start + acquisition_time

                    while time.perf_counter() > next_interval:
                        self.logger.debug('Skipping one image.')
                        next_interval += acquisition_time
                        i += 1

                    diff = next_interval - time.perf_counter()
                    time.sleep(diff)

                else:
                    t_start = time.perf_counter()
                    img, h = self.ctrl.get_image(self.expt, header_keys=None)
                    if buffer == []:
                        imgscale0 = np.sum(img)
                    else:
                        imgscale = np.sum(img)
                        self.logger.debug(f'Image scale variation: {imgscale / imgscale0}')

                    buffer.append((i, img, h))

                    next_interval = t_start + acquisition_time

                    while time.perf_counter() > next_interval:
                        next_interval += acquisition_time
                        self.logger.debug(
                            'One image skipped because of too long acquisition or calculation time.'
                        )
                        i += 1

                    diff = next_interval - time.perf_counter()
                    time.sleep(diff)

                i += 1

                if time.perf_counter() - t0 >= rotation_t:
                    self.stopEvent.set()
                    self.print_and_del('Goniometer close to limit!')

            except Exception as e:
                self.print_and_del(e)
                self.stopEvent.set()

        t1 = time.perf_counter()

        self.ctrl.cam.unblock()
        if self.mode > 1:
            self.ctrl.stage.stop()

        if self.camtype == 'simulate':
            self.endangle = self.startangle + np.random.random() * 50
            camera_length = 300
        else:
            self.endangle = self.ctrl.stage.a
            camera_length = int(self.ctrl.magnification.get())

        if self.unblank_beam:
            # print("Blanking beam")
            self.ctrl.beam.blank()

        self.stopEvent.clear()

        self.ctrl.imageshift1.set(x=is1_init[0], y=is1_init[1])
        self.ctrl.imageshift2.set(x=is2_init[0], y=is2_init[1])

        # stage_positions = tracer.stop()
        stageposx, stageposy, stageposz, stageposa, stageposb = self.ctrl.stage.get()
        rotrange = abs(self.endangle - self.startangle)

        if self.verbose:
            print(
                f'Rotated {abs(self.endangle - self.startangle):.2f} degrees from {self.startangle:.2f} to {self.endangle:.2f}'
            )

        self.logger.info(
            f'Rotated {abs(self.endangle - self.startangle):.2f} degrees from {self.startangle:.2f} to {self.endangle:.2f}'
        )

        nframes = (
            i - 1
        )  # i + 1 is not correct since i+=1 was executed before next image is taken???
        osangle = abs(self.endangle - self.startangle) / nframes
        acquisition_time = (t1 - t0) / nframes

        self.logger.info(f'Data collection camera length: {camera_length} mm')
        self.logger.info(
            f'Data collected from {self.startangle} degree to {self.endangle} degree.'
        )
        self.logger.info(f'Oscillation angle: {osangle}')
        self.logger.info(
            'Pixel size and actual camera length updated in SMV file headers for DIALS processing.'
        )

        rotation_angle = config.camera.camera_rotation_vs_stage_xy

        self.pixelsize = config.calibration['diff']['pixelsize'][camera_length]  # px / Angstrom
        self.physical_pixelsize = config.camera.physical_pixelsize  # mm
        self.wavelength = config.microscope.wavelength  # angstrom
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(os.path.join(path, 'cRED_log.txt'), 'w') as f:
            print(f'Data Collection Time: {now}', file=f)
            print(f'Starting angle: {self.startangle}', file=f)
            print(f'Ending angle: {self.endangle}', file=f)
            print(f'Exposure Time: {self.expt} s', file=f)
            print(f'Spot Size: {spotsize}', file=f)
            print(f'Camera length: {camera_length} mm\n', file=f)
            print(f'Pixelsize: {self.pixelsize} px/Angstrom', file=f)
            print(f'Physical pixelsize: {self.physical_pixelsize} um', file=f)
            print(f'Wavelength: {self.wavelength} Angstrom', file=f)
            print(f'Stretch amplitude: {self.stretch_azimuth} %', file=f)
            print(f'Stretch azimuth: {self.stretch_amplitude} degrees', file=f)
            print(f'Rotation axis: {rotation_angle} radians', file=f)
            print(f'Oscillation angle: {osangle} degrees', file=f)
            print(f'Number of frames: {len(buffer)}', file=f)
            print(
                f'Particle found at stage position: x: {stageposx}, y: {stageposy}, z: {stageposz}',
                file=f,
            )

        with open(log_rotaterange, 'a') as f:
            f.write(f'{stageposx}\t{stageposy}\t{stageposz}\t{rotrange}\n')

        img_conv = ImgConversion(
            buffer=buffer,
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
            stretch_azimuth=self.stretch_azimuth,
        )

        img_conv.tiff_writer(pathtiff)
        img_conv.smv_writer(pathsmv)
        img_conv.mrc_writer(pathred)
        img_conv.write_ed3d(pathred)
        img_conv.write_xds_inp(pathsmv)

        img_conv.to_dials(pathsmv)
        pathsmv_str = str(pathsmv)
        msg = {'path': pathsmv_str, 'rotrange': rotrange, 'nframes': nframes, 'osc': osangle}
        msg_tosend = json.dumps(msg).encode('utf8')

        if self.s_c:
            self.s.send(msg_tosend)
            self.print_and_del('SMVs sent to DIALS for processing.')

        if self.s2_c:
            self.s2.send(msg_tosend)
            self.print_and_del('SMVs sent to XDS for processing.')

        # self.logger.info("XDS INP file created.")

        if image_buffer:
            drc = os.path.join(path, 'tiff_image')
            os.makedirs(drc)
            while len(image_buffer) != 0:
                i, img, h = image_buffer.pop(0)
                fn = os.path.join(drc, f'{i:05d}.tiff')
                write_tiff(fn, img, header=h)

        self.ctrl.beam.unblank()
        self.number_exp_performed += 1
        if self.verbose:
            print('Data Collection and Conversion Done.')

    def write_BrightnessStates(self, n_cycles=2):
        print(
            'Go to your desired magnification and camera length. Now recording lens states...'
        )
        self.ctrl.mode.set('mag1')
        input(
            'Please choose the desired magnification, partially converge the beam in MAG1 to around 1 um in diameter, and center it using beamshift. Press ENTER when ready'
        )

        for i in range(0, n_cycles):
            self.hysteresis_check()
            input('Please recenter the beam with beamshift. Press ENTER when ready')

        desired_mag = self.ctrl.magnification.get()
        img_brightness = self.ctrl.brightness.value
        bs = self.ctrl.beamshift.get()

        self.ctrl.mode.set('samag')
        self.ctrl.mode.set('diff')
        input(
            'Please go to diffraction mode, choose desired camera length, focus the diffraction spots, and center it using PLA. Press ENTER when ready'
        )
        for i in range(0, n_cycles):
            self.hysteresis_check()
            input('Please recenter the diffraction spot using PLA. Press ENTER when ready')

        desired_cl = self.ctrl.magnification.get()
        dp_focus = self.ctrl.difffocus.value
        is1status = self.ctrl.imageshift1.get()
        is2status = self.ctrl.imageshift2.get()
        plastatus = self.ctrl.diffshift.get()
        with open(self.calibdir / 'beam_brightness.pkl', 'wb') as f:
            pickle.dump(
                [
                    img_brightness,
                    bs,
                    dp_focus,
                    is1status,
                    is2status,
                    plastatus,
                    desired_mag,
                    desired_cl,
                ],
                f,
            )

        print('Brightness recorded.')
        return [
            img_brightness,
            bs,
            dp_focus,
            is1status,
            is2status,
            plastatus,
            desired_mag,
            desired_cl,
        ]

    def update_referencepoint_bs(self, bs, br):
        exposure = 0.01
        binsize = 1
        scale = 1
        self.ctrl.beamshift.set(*bs)
        self.ctrl.brightness.value = br

        img_cent = self.ctrl.get_raw_image(exposure=exposure, binsize=binsize)

        if np.mean(img_cent) > 10:
            pixel_cent = np.array(find_beam_center(img_cent)) * binsize / scale

            # print(pixel_cent)

            self.calib_beamshift.reference_shift = bs
            self.calib_beamshift.reference_pixel = pixel_cent

            return self.calib_beamshift.reference_pixel
        else:
            return self.calib_beamshift.reference_pixel

    def raster_scan(self):
        from instamatic.experiments.serialed.experiment import get_offsets_in_scan_area

        pixelsize_mag1 = (
            config.calibration['mag1']['pixelsize'][self.magnification] / 1000
        )  # nm -> um
        xdim, ydim = self.ctrl.cam.get_camera_dimensions()
        box_x, box_y = self.pixelsize_mag1 * xdim, self.pixelsize_mag1 * ydim

        # Make negative to reflect config change 2019-07-03 to make omega more in line with other software
        rot_axis = -config.camera.camera_rotation_vs_stage_xy

        offsets = get_offsets_in_scan_area(box_x, box_y, self.scan_area, angle=rot_axis)
        self.offsets = offsets * 1000

        center_x = self.ctrl.stage.x
        center_y = self.ctrl.stage.y

        x_zheight = 0
        y_zheight = 0

        t = tqdm(
            self.offsets,
            desc=f'Number of crystals scanned: {self.number_crystals_scanned}; Number of experiments performed: {self.number_exp_performed}',
        )

        for j, (x_offset, y_offset) in enumerate(t):
            x = center_x + x_offset
            y = center_y + y_offset

            self.ctrl.stage.set(x=x, y=y)
            # print("Stage position: x = {}, y = {}".format(x,y))
            x_change = x - x_zheight
            y_change = y - y_zheight
            dist = np.linalg.norm((x_change, y_change))

            if dist > 50000 or x_zheight * y_zheight == 0 or x_zheight == 999999:
                try:
                    img, h = self.ctrl.get_image(exposure=self.expt, header_keys=None)
                    if img.mean() > 10:
                        self.magnification = self.ctrl.magnification.value
                        crystal_positions = find_crystals_timepix(
                            img, self.magnification, spread=self.spread, offset=self.offset
                        )
                        crystal_coords = [
                            (crystal.x, crystal.y) for crystal in crystal_positions
                        ]

                        n_crystals = len(crystal_coords)
                        if n_crystals > 0:
                            self.print_and_del('centering z height...')
                            x_zheight, y_zheight = center_z_height_HYMethod(
                                self.ctrl, spread=self.spread, offset=self.offset
                            )
                            if x_zheight != 999999:
                                xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stage.get()
                                self.logger.info(
                                    f'Stage position: x = {xpoint}, y = {ypoint}. Z height adjusted to {zpoint}. Tilt angle x {aaa} deg, Tilt angle y {bbb} deg'
                                )
                            else:
                                self.print_and_del('Z height not found.')
                except BaseException:
                    self.print_and_del('Something went wrong, unable to adjust height')
                    pass

            self.start_collection_point()

            t.set_description(
                f'Number of crystals scanned: {self.number_crystals_scanned}; Number of experiments performed: {self.number_exp_performed}'
            )

            if self.stopEvent_rasterScan.is_set():
                print('\nRaster Scan stopped manually.')
                break

    def start_collection_point(self):
        IS1_Neut = self.ctrl.imageshift1.get()
        IS2_Neut = self.ctrl.imageshift2.get()

        path = self.path

        if self.scan_area != 0:
            path = path / f'stagepos_{self.stagepos_idx:04d}'
            self.stagepos_idx += 1
            if not os.path.exists(path):
                os.makedirs(path)

        try:
            with open(self.calibdir / 'beam_brightness.pkl', 'rb') as f:
                [
                    img_brightness,
                    bs,
                    dp_focus,
                    is1status,
                    is2status,
                    plastatus,
                    desired_mag,
                    desired_cl,
                ] = pickle.load(f)
        except OSError:
            [
                img_brightness,
                bs,
                dp_focus,
                is1status,
                is2status,
                plastatus,
                desired_mag,
                desired_cl,
            ] = self.write_BrightnessStates()

        try:
            self.calib_beamshift = CalibBeamShift.from_file(fn=self.calibdir / CALIB_BEAMSHIFT)
            self.ctrl.beamshift.set(
                x=self.calib_beamshift.reference_shift[0],
                y=self.calib_beamshift.reference_shift[1],
            )

        except OSError:
            print(
                'No beam shift calibration result found. Running instamatic.calibrate_beamshift first...\n'
            )
            print(
                'Going to MAG1, desired magnification, and desired brightness. DO NOT change brightness!'
            )
            if self.ctrl.mode != 'mag1':
                self.ctrl.mode.set('mag1')
                self.ctrl.magnification.value = desired_mag
                self.ctrl.brightness.value = img_brightness

            calib_file = 'x'
            while calib_file == 'x':
                print('Find a clear area, toggle the beam to the desired defocus value.')
                self.calib_beamshift = calibrate_beamshift(ctrl=self.ctrl, outdir=self.calibdir)
                print('Beam shift calibration done.')
                calib_file = input(
                    'Press ENTER when ready to continue. Press x to REDO the calibration.'
                )

        self.logger.debug(f'Transform_beamshift: {self.calib_beamshift.transform}')

        try:
            self.calib_directbeam = CalibDirectBeam.from_file(
                fn=self.calibdir / CALIB_DIRECTBEAM
            )
            with open(self.calibdir / 'diff_par.pkl', 'rb') as f:
                self.diff_brightness, self.diff_difffocus = pickle.load(f)
        except OSError:
            if not self.ctrl.mode == 'diff':
                self.ctrl.mode.set('samag')
                self.ctrl.imageshift1.set(x=is1status[0], y=is1status[1])
                self.ctrl.imageshift2.set(x=is2status[0], y=is2status[1])
                self.ctrl.mode.set('diff')
            self.ctrl.difffocus.value = dp_focus

            self.calib_directbeam = CalibDirectBeam.live(self.ctrl, outdir=self.calibdir)
            self.diff_brightness = self.ctrl.brightness.value
            self.diff_difffocus = self.ctrl.difffocus.value
            with open(self.calibdir / 'diff_par.pkl', 'wb') as f:
                pickle.dump([self.diff_brightness, self.diff_difffocus], f)

        try:
            with open(self.calibdir / 'imgvariance.pkl', 'rb') as f:
                self.imgvar_threshold, self.beam_size_avg = pickle.load(f)
        except OSError:
            self.imgvar_threshold, self.beam_size_avg = self.imagevar_blank_estimator(
                brightness=img_brightness
            )
            with open(self.calibdir / 'imgvariance.pkl', 'wb') as f:
                pickle.dump([self.imgvar_threshold, self.beam_size_avg], f)

        self.neutral_beamshift = bs
        # print("Neutral beamshift: from beam_brightness.pkl {}".format(bs))
        self.neutral_diffshift = plastatus

        self.calib_beamshift.reference_pixel = self.update_referencepoint_bs(bs, img_brightness)

        # print("Calib_beamshift_referenceshift: {}".format(self.calib_beamshift.reference_shift))

        transform_imgshift, c = load_IS_Calibrations(
            imageshift='IS1',
            ctrl=self.ctrl,
            diff_defocus=self.diff_defocus,
            logger=self.logger,
            mode='diff',
        )
        transform_imgshift2, c = load_IS_Calibrations(
            imageshift='IS2',
            ctrl=self.ctrl,
            diff_defocus=self.diff_defocus,
            logger=self.logger,
            mode='diff',
        )
        transform_imgshift_foc, c = load_IS_Calibrations(
            imageshift='IS1', ctrl=self.ctrl, diff_defocus=0, logger=self.logger, mode='diff'
        )
        transform_imgshift2_foc, c = load_IS_Calibrations(
            imageshift='IS2', ctrl=self.ctrl, diff_defocus=0, logger=self.logger, mode='diff'
        )

        transform_beamshift_d, c = load_IS_Calibrations(
            imageshift='BS', ctrl=self.ctrl, diff_defocus=0, logger=self.logger, mode='diff'
        )
        transform_beamshift_d_defoc, c = load_IS_Calibrations(
            imageshift='BS',
            ctrl=self.ctrl,
            diff_defocus=self.diff_defocus,
            logger=self.logger,
            mode='diff',
        )
        # transform_beamshift_d = self.calib_beamshift.transform

        transform_stagepos, c = load_IS_Calibrations(
            imageshift='S', ctrl=self.ctrl, diff_defocus=0, logger=self.logger, mode='mag1'
        )

        if self.mode == 3:
            # ready = input("Please make sure that you are in the super user mode and the rotation speed is set via GONIOTOOL! Press ENTER to continue.")

            if self.ctrl.mode != 'mag1':
                self.ctrl.mode.set('mag1')

            self.ctrl.magnification.value = desired_mag
            self.ctrl.brightness.value = 65535

            header_keys = None

            if self.verbose:
                print(f'Beamshift reference: {self.calib_beamshift.reference_shift}')

            self.ctrl.beamshift.set(
                x=self.calib_beamshift.reference_shift[0],
                y=self.calib_beamshift.reference_shift[1],
            )

            self.magnification = self.ctrl.magnification.value

            self.rotation_direction = self.eliminate_backlash_in_tiltx()
            img, h = self.ctrl.get_image(exposure=self.expt, header_keys=header_keys)
            # img, h = Experiment.apply_corrections(img, h)

            threshold = 10  # ignore black images

            if img.mean() > threshold:
                h['exp_magnification'] = self.ctrl.magnification.get()

                write_tiff(path / 'Overall_view', img, h)

                crystal_positions = find_crystals_timepix(
                    img, self.magnification, spread=self.spread, offset=self.offset
                )
                crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]

                n_crystals = len(crystal_coords)

                if n_crystals == 0:
                    self.print_and_del('No crystals found in the image. Find another area!')
                    return 0

                (beamshiftcoord_0, size_crystal_targeted) = (
                    self.center_particle_from_crystalList(
                        crystal_positions,
                        transform_stagepos,
                        self.magnification,
                        self.beam_size_avg,
                    )
                )

                img, h = self.ctrl.get_image(exposure=self.expt, header_keys=header_keys)
                h['exp_magnification'] = self.ctrl.magnification.get()
                write_tiff(path / 'Overall_view', img, h)

                crystal_positions = find_crystals_timepix(
                    img, self.magnification, spread=self.spread, offset=self.offset
                )
                crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]
                crystal_sizes = [crystal.area_pixel for crystal in crystal_positions]
                n_crystals = len(crystal_coords)

                if n_crystals == 0:
                    self.print_and_del('No crystals found in the image. Find another area!')
                    return 0

                if size_crystal_targeted != 0:
                    try:
                        ind_target = crystal_sizes.index(size_crystal_targeted)
                        crystal_coords[0], crystal_coords[ind_target] = (
                            crystal_coords[ind_target],
                            crystal_coords[0],
                        )
                        self.print_and_del(
                            'Targeted isolated crystal centered is swapped to the first of the list.'
                        )
                    except ValueError:
                        self.print_and_del('Lost targeted isolated crystal.')
                        return 0

                self.logger.info(f'{datetime.datetime.now()} {n_crystals} crystals found.')

                k = 0

                while not self.stopEvent_rasterScan.is_set():
                    try:
                        self.ctrl.brightness.value = img_brightness

                        if self.verbose:
                            print(
                                f'Collecting on crystal {k + 1}/{n_crystals}. Beamshift coordinates: {self.ctrl.beamshift.get()}'
                            )

                        outfile = path / f'crystal_{k:04d}'
                        comment = f'crystal {k}'

                        beamshift_coords = np.array(bs) - np.dot(
                            crystal_coords[k] - self.calib_beamshift.reference_pixel,
                            self.calib_beamshift.transform,
                        )
                        self.ctrl.beamshift.set(*beamshift_coords.astype(int))

                        img, h = self.ctrl.get_image(
                            exposure=0.001, comment=comment, header_keys=header_keys
                        )
                        h['exp_magnification'] = self.ctrl.magnification.get()
                        write_tiff(path / f'crystal_{k:04d}', img, h)

                        self.number_crystals_scanned += 1

                        if (
                            self.isolated(crystal_positions[k], crystal_coords)
                            and crystal_positions[k].isolated
                            and not any(t < 100 for t in crystal_coords[k])
                            and not any(t > 416 for t in crystal_coords[k])
                        ):
                            self.ctrl.mode.set('samag')
                            self.ctrl.mode.set('diff')
                            self.ctrl.imageshift1.set(x=is1status[0], y=is1status[1])
                            self.ctrl.imageshift2.set(x=is2status[0], y=is2status[1])
                            self.ctrl.diffshift.set(x=plastatus[0], y=plastatus[1])

                            # compensate beamshift
                            beamshift_offset = beamshift_coords - self.neutral_beamshift
                            pixelshift = self.calib_directbeam.beamshift2pixelshift(
                                beamshift_offset
                            )

                            diffshift_offset = self.calib_directbeam.pixelshift2diffshift(
                                pixelshift
                            )
                            diffshift = self.neutral_diffshift - diffshift_offset

                            self.ctrl.diffshift.set(*diffshift.astype(int))

                            pathtiff = outfile / 'tiff'
                            pathsmv = outfile / 'SMV'
                            pathred = outfile / 'RED'

                            self.auto_cred_collection(
                                outfile,
                                pathtiff,
                                pathsmv,
                                pathred,
                                transform_imgshift,
                                transform_imgshift2,
                                transform_imgshift_foc,
                                transform_imgshift2_foc,
                                transform_beamshift_d,
                                transform_beamshift_d_defoc,
                                self.calib_beamshift,
                            )

                            self.ctrl.beamshift.set(
                                x=self.calib_beamshift.reference_shift[0],
                                y=self.calib_beamshift.reference_shift[1],
                            )
                            self.ctrl.mode.set('mag1')
                            self.ctrl.brightness.value = 65535
                            time.sleep(0.5)

                            self.rotation_direction = self.eliminate_backlash_in_tiltx()
                            img, h = self.ctrl.get_image(
                                exposure=self.expt, header_keys=header_keys
                            )
                            h['exp_magnification'] = self.ctrl.magnification.get()
                            write_tiff(path / f'Overall_view_{k:04d}', img, h)

                            crystal_positions = find_crystals_timepix(
                                img, self.magnification, spread=self.spread, offset=self.offset
                            )
                            crystal_coords = [
                                (crystal.x, crystal.y) for crystal in crystal_positions
                            ]
                            # self.ctrl.brightness.value = img_brightness

                            if n_crystals == 0:
                                self.print_and_del(
                                    'No crystals found in the image. exitting loop...'
                                )
                                break

                            (beamshiftcoord_0, size_crystal_targeted) = (
                                self.center_particle_from_crystalList(
                                    crystal_positions,
                                    transform_stagepos,
                                    self.magnification,
                                    self.beam_size_avg,
                                )
                            )

                            img, h = self.ctrl.get_image(
                                exposure=self.expt, header_keys=header_keys
                            )
                            h['exp_magnification'] = self.ctrl.magnification.get()
                            write_tiff(path / f'Overall_view_{k:04d}', img, h)

                            crystal_positions = find_crystals_timepix(
                                img, self.magnification, spread=self.spread, offset=self.offset
                            )
                            crystal_coords = [
                                (crystal.x, crystal.y) for crystal in crystal_positions
                            ]
                            crystal_sizes = [
                                crystal.area_pixel for crystal in crystal_positions
                            ]
                            n_crystals = len(crystal_coords)

                            if n_crystals == 0:
                                self.print_and_del(
                                    'No crystals found in the image. Find another area!'
                                )
                                break

                            if size_crystal_targeted != 0:
                                try:
                                    ind_target = crystal_sizes.index(size_crystal_targeted)
                                    crystal_coords[k + 1], crystal_coords[ind_target] = (
                                        crystal_coords[ind_target],
                                        crystal_coords[k + 1],
                                    )
                                    self.print_and_del(
                                        'Targeted isolated crystal centered is swapped to the next.'
                                    )
                                except ValueError:
                                    self.print_and_del('Lost targeted isolated crystal.')
                                    break

                        else:
                            if self.verbose:
                                print(
                                    f'Crystal {k + 1} not isolated: not suitable for cred collection'
                                )

                        k = k + 1
                        if k >= n_crystals:
                            break
                    except BaseException:
                        traceback.print_exc()
                        self.ctrl.beam.unblank()
                        self.print_and_del('Exitting loop...')
                        break

                self.ctrl.mode.set('mag1')
                self.ctrl.brightness.value = 65535

                self.ctrl.imageshift1.set(x=IS1_Neut[0], y=IS1_Neut[1])
                self.ctrl.imageshift2.set(x=IS2_Neut[0], y=IS2_Neut[1])

                self.ctrl.beamshift.set(
                    x=self.calib_beamshift.reference_shift[0],
                    y=self.calib_beamshift.reference_shift[1],
                )

                if self.verbose:
                    print(
                        'AutocRED with crystal_finder data collection done. Find another area for particles.'
                    )

            if os.listdir(path) == ['Overall_view.tiff']:
                shutil.rmtree(path)
                # print("Path {} removed since no crystal rotation data was collected.".format(path))

            try:
                if len(os.listdir(path)) == 0:
                    os.rmdir(path)
                    # print("Path {} removed since it is empty.".format(path))
            except BaseException:
                # print("Deletion error. Path might have already been deleted.")
                pass

        elif self.mode == 1 or self.mode == 2:
            self.pathtiff = Path(self.path) / 'tiff'
            self.pathsmv = Path(self.path) / 'SMV'
            self.pathred = Path(self.path) / 'RED'

            for path in (self.path, self.pathtiff, self.pathsmv, self.pathred):
                if not os.path.exists(path):
                    os.makedirs(path)
            self.auto_cred_collection(
                self.path,
                self.pathtiff,
                self.pathsmv,
                self.pathred,
                transform_imgshift,
                transform_imgshift2,
                transform_imgshift_foc,
                transform_imgshift2_foc,
                transform_beamshift_d,
                transform_beamshift_d_defoc,
                self.calib_beamshift,
            )

        else:
            print('Choose cRED tab for data collection with manual/blind tracking.')
            return 0

    def start_collection(self):
        ready = input(
            'Please make sure that you have adjusted Goniotool if you are using full autocRED!'
        )
        if self.stopEvent_rasterScan.is_set():
            # print("Raster scan stopper clearing..")
            self.stopEvent_rasterScan.clear()

        if not self.auto_zheight:
            try:
                with open(self.calibdir / 'z-height-adjustment-time.pkl', 'rb') as f:
                    t = pickle.load(f)
                    if t - time.perf_counter() > 14400:
                        self.print_and_del(
                            'Z-height needs to be updated every session. Readjusting z-height...'
                        )
                        x_zheight, y_zheight = center_z_height_HYMethod(
                            self.ctrl, spread=self.spread, offset=self.offset
                        )
                        xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stage.get()
                        self.logger.info(
                            f'Stage position: x = {xpoint}, y = {ypoint}. Z height adjusted to {zpoint}. Tilt angle x {aaa} deg, Tilt angle y {bbb} deg'
                        )
                        t = time.perf_counter()
                        with open(self.calibdir / 'z-height-adjustment-time.pkl', 'wb') as f:
                            pickle.dump(t, f)

            except BaseException:
                input(
                    'No z-height adjustment found. Please find an area with particles! Press Enter to continue auto adjustment of z height>>>'
                )
                x_zheight, y_zheight = center_z_height_HYMethod(
                    self.ctrl, spread=self.spread, offset=self.offset
                )
                xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stage.get()
                self.logger.info(
                    f'Stage position: x = {xpoint}, y = {ypoint}. Z height adjusted to {zpoint}. Tilt angle x {aaa} deg, Tilt angle y {bbb} deg'
                )
                t = time.perf_counter()
                with open(self.calibdir / 'z-height-adjustment-time.pkl', 'wb') as f:
                    pickle.dump(t, f)
        else:
            self.print_and_del('Z height adjusting...')
            x_zheight, y_zheight = center_z_height_HYMethod(
                self.ctrl, spread=self.spread, offset=self.offset
            )
            xpoint, ypoint, zpoint, aaa, bbb = self.ctrl.stage.get()
            self.logger.info(
                f'Stage position: x = {xpoint}, y = {ypoint}. Z height adjusted to {zpoint}. Tilt angle x {aaa} deg, Tilt angle y {bbb} deg'
            )
            t = time.perf_counter()
            with open(self.calibdir / 'z-height-adjustment-time.pkl', 'wb') as f:
                pickle.dump(t, f)

        lensPar = self.ctrl.to_dict()
        with open(self.calibdir / 'LensPar.pkl', 'wb') as f:
            pickle.dump(lensPar, f)

        # Check DIALS server connection status here

        if self.scan_area == 0:
            self.start_collection_point()
        else:
            self.raster_scan()

        self.stopEvent_rasterScan.clear()

        with open(self.calibdir / 'LensPar.pkl', 'rb') as f:
            lensPar_i = pickle.load(f)

        self.ctrl.from_dict(lensPar_i)
        self.ctrl.beam.blank()

        print('AutocRED collection done.')
        self.number_crystals_scanned = 0
        self.number_exp_performed = 0
