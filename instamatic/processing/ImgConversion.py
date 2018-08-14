import os
import numpy as np
from datetime import datetime
import time
from instamatic.formats import read_tiff, write_tiff, write_mrc, write_adsc
from instamatic.processing.flatfield import apply_flatfield_correction
from instamatic.processing.stretch_correction import apply_stretch_correction
from instamatic import config
from instamatic.tools import find_beam_center, find_subranges
from pathlib import Path
from math import cos, pi
import math
from scipy.signal import convolve2d
from scipy import ndimage
import collections

import logging
logger = logging.getLogger(__name__)


def rotation_axis_to_xyz(rotation_axis, invert=False, setting='xds'):
    if invert:
        rotation_axis += np.pi

    rot_x = cos(rotation_axis)
    rot_y = cos(rotation_axis+np.pi/2)
    rot_z = 0

    if setting == 'dials':
        return rot_x, -rot_y, rot_z
    elif setting == 'xds':
        return rot_x, rot_y, rot_z
    else:
        raise ValueError("Must be one of {'dials', 'xds'}")


def export_dials_variables(path, *, sequence=(), missing=(), rotation_xyz=None):
    import io

    scanranges = find_subranges(sequence)
    
    scanrange = " ".join(f"scan_range={i},{j}" for i, j in scanranges)
    excludeimages = ",".join((str(n) for n in missing))

    if rotation_xyz:
        rot_x, rot_y, rot_z = rotation_xyz
    
    # newline='\n' to have unix line endings
    with open(path / "dials_variables.sh", "w",  newline='\n') as f:
        print(f"#!/usr/bin/env bash", file=f)
        print(f"scan_range='{scanrange}'", file=f)
        print(f"exclude_images='exclude_images={excludeimages}'", file=f)
        if rotation_xyz:
            print(f"rotation_axis='geometry.goniometer.axes={rot_x:.4f},{rot_y:.4f},{rot_z:.4f}'", file=f)
        print("#", file=f)
        print("# To run:", file=f)
        print("#     source dials_variables.sh", file=f)
        print("#", file=f)
        print("# and:", file=f)
        print("#     dials.import directory=data $rotation_axis", file=f)
        print("#     dials.find_spots datablock.json $scan_range", file=f)
        print("#     dials.integrate $exclude_images refined.pickle refined.json", file=f)
        print("#", file=f)

    with open(path / "dials_variables.bat", "w", newline='\n') as f:
        print("@echo off", file=f)
        print("", file=f)
        print(f"set scan_range={scanrange}", file=f)
        print(f"set exclude_images=exclude_images={excludeimages}", file=f)
        if rotation_xyz:
            print(f"set rotation_axis=geometry.goniometer.axes={rot_x:.4f},{rot_y:.4f},{rot_z:.4f}", file=f)
        print("", file=f)
        print(":: To run:", file=f)
        print("::     call dials_variables.bat", file=f)
        print("::", file=f)
        print("::     dials.import directory=data %rotation_axis%", file=f)
        print("::     dials.find_spots datablock.json %scan_range%", file=f)
        print("::     dials.integrate %exclude_images% refined.pickle refined.json", file=f)


def get_calibrated_rotation_speed(val):
    """Correct for the overestimation of the oscillation angle if the rotation 
    was stopped before interrupting the data collection. It uses calibrated values for the 
    rotation speeds of the microscope, and matches them to the observed one"""

    rotation_speeds = set(config.microscope.specifications["rotation_speeds"]["coarse"] + config.microscope.specifications["rotation_speeds"]["fine"])
    calibrated_value = min(rotation_speeds, key=lambda x:abs(x-val))
    logger.info("Correcting oscillation angle from {:.3f} to calibrated value {:.3f}".format(val, calibrated_value))
    return calibrated_value


class ImgConversion(object):
    
    'This class is for post cRED data collection image conversion and necessary files generation for REDp and XDS processing, as well as DIALS processing'

    def __init__(self, 
                 buffer,                     # image buffer, list of (index [int], image data [2D numpy array], header [dict])
                 camera_length,              # virtual camera length read from the microscope
                 osc_angle,                  # degrees, oscillation angle of the rotation
                 start_angle,                # degrees, start angle of the rotation
                 end_angle,                  # degrees, end angle of the rotation
                 rotation_axis,              # radians, specifies the position of the rotation axis
                 acquisition_time,           # seconds, acquisition time (exposure time + overhead)
                 flatfield='flatfield.tiff', 
                 centerDP=False 
                 ):
        flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.headers = {}
        self.data = {}

        self.smv_subdrc = "data"
        
        self.do_centerDP = centerDP
            
        while len(buffer) != 0:
            i, img, h = buffer.pop(0)
                
            self.headers[i] = h

            if self.flatfield is not None:
                self.data[i] = apply_flatfield_correction(img, self.flatfield)
            else:
                self.data[i] = img

        self.observed_range = set(self.data.keys())
        self.complete_range = set(range(min(self.observed_range), max(self.observed_range) + 1))
        self.missing_range = self.observed_range ^ self.complete_range

        if self.do_centerDP:
            self.data_c, self.pbc = self.DP_centering()
            for _, h in self.headers.items():
                h["beam_center"] = self.pbc

        self.data_shape = img.shape
        try:
            self.pixelsize = config.calibration.diffraction_pixeldimensions[camera_length] # px / Angstrom
        except KeyError:
            self.pixelsize = 1
            print("No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length))
            logger.warning("No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length))

        self.physical_pixelsize = config.camera.physical_pixelsize # mm
        self.wavelength = config.microscope.wavelength # angstrom
        # NOTE: Stretch correction - not sure if the azimuth and amplitude are correct anymore.
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        self.mean_beam_center, self.beam_center_std = self.get_beam_centers()
        self.distance = (1/self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osc_angle = osc_angle
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.rotation_axis = rotation_axis
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = get_calibrated_rotation_speed(osc_angle / self.acquisition_time) 

        self.do_stretch_correction = True

        logger.debug("Primary beam at: {}".format(self.mean_beam_center))

    def estimate_noise(self, I):
        H, W = I.shape
        
        M = [[1, -2, 1],
             [-2, 4, -2],
             [1, -2, 1]]
        
        sigma = np.sum(np.sum(np.absolute(convolve2d(I, M))))
        sigma = sigma * math.sqrt(0.5 * math.pi) / (6 * (W-2) * (H-2))
        
        return sigma
        
    def find_beam_center(self, img, sigma=30):
        """instamatic.tools"""
        "Find position of the central beam using gaussian filter"
        blurred = ndimage.gaussian_filter(img, sigma)
        center = np.unravel_index(blurred.argmax(), blurred.shape)
        return np.array(center)

    def DP_centering(self, sigma = 30):
        """In full autocRED, DPs drift because of too much utilization of lenses. Need to center them for XDS and DIALS"""
        centered_dp = {}
        
        img0 = self.data[1]
        sizex, sizey = img0.shape
        pbc1 = self.find_beam_center(img0, sigma = sigma)
        
        print("Centering DP according to the first image...")
        for i in self.observed_range:
            img = self.data[i]
            noise = self.estimate_noise(img)
            pbc = self.find_beam_center(img, sigma = sigma)
            shift = pbc - pbc1
            shift = (int(shift[0]), int(shift[1]))
            imgnew = np.zeros((sizex, sizey))
            for j in range(0, sizex):
                for k in range(0, sizey):
                    if j - shift[0] < 0 or k - shift[1] < 0:
                        imgnew[(j - shift[0]) % sizex, (k - shift[1]) % sizey] = np.random.normal(3*noise, noise)
                    else:
                        imgnew[(j - shift[0]) % sizex, (k - shift[1]) % sizey] = img[j, k]
            centered_dp[i] = imgnew.astype(np.int16)
            
        print("Images are now centered according to the first image.")
        return centered_dp, pbc1
    
    def get_beam_centers(self):
        centers = []
        for i, h in self.headers.items():
            if self.do_centerDP:
                center = find_beam_center(self.data_c[i], sigma=10)
            else:
                center = find_beam_center(self.data[i], sigma=10)
                h["beam_center"] = center
                
            centers.append(center)

        beam_centers = np.array(centers)

        # avg_center = np.mean(centers, axis=0)
        avg_center = np.median(beam_centers, axis=0)
        std_center = np.std(beam_centers, axis=0)

        return avg_center, std_center

    def apply_stretch_correction(self, image, center):
        center = np.copy(center)
        
        azimuth   = self.stretch_azimuth
        amplitude = self.stretch_amplitude
        
        newImage = apply_stretch_correction(image, center=center, azimuth=azimuth, amplitude=amplitude)
    
        return newImage

    def tiff_writer(self, path):
        print ("Writing TIFF files......")

        path.mkdir(exist_ok=True)

        for i in self.observed_range:
            self.write_tiff(path, i)

        logger.debug("Tiff files saved in folder: {}".format(path))

    def smv_writer(self, path):
        print ("Writing SMV files......")

        path = path / self.smv_subdrc
        path.mkdir(exist_ok=True)
        
        for i in self.observed_range:
            if self.do_centerDP:
                self.write_smv_centered(path, i)
                logger.debug("SMV files (centered) saved in folder: {}".format(path))
            else:
                self.write_smv(path, i)
                logger.debug("SMV files saved in folder: {}".format(path))
     
    def mrc_writer(self, path):
        print ("Writing MRC files......")

        path.mkdir(exist_ok=True)

        for i in self.observed_range:
            self.write_mrc(path, i)

        logger.debug("MRC files created in folder: {}".format(path))

    def threadpoolwriter(self, tiff_path=None, smv_path=None, mrc_path=None, workers=8):
        write_tiff = tiff_path is not None
        write_smv  = smv_path  is not None
        write_mrc  = mrc_path  is not None

        if write_smv:
            smv_path = smv_path / self.smv_subdrc
            smv_path.mkdir(exist_ok=True, parents=True)
            logger.debug("SMV files saved in folder: {}".format(smv_path))

        if write_tiff:
            tiff_path.mkdir(exist_ok=True, parents=True)
            logger.debug("Tiff files saved in folder: {}".format(tiff_path))

        if write_mrc:
            mrc_path.mkdir(exist_ok=True, parents=True)
            logger.debug("MRC files saved in folder: {}".format(mrc_path))

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for i in self.observed_range:
                
                if write_tiff:
                    futures.append(executor.submit(self.write_tiff, tiff_path, i))
                if write_mrc:
                    futures.append(executor.submit(self.write_mrc, mrc_path, i))
                if write_smv:
                    futures.append(executor.submit(self.write_smv, smv_path, i))

            for future in futures:
                ret = future.result()

    def to_dials(self, smv_path, interval=False):
        observed_range = self.observed_range
        self.missing_range = self.missing_range

        invert_rotation_axis = self.start_angle > self.end_angle
        rotation_xyz = rotation_axis_to_xyz(self.rotation_axis, invert=invert_rotation_axis, setting='dials')

        export_dials_variables(smv_path, sequence=observed_range, missing=self.missing_range, rotation_xyz=rotation_xyz)

        path = smv_path / self.smv_subdrc

        i = min(observed_range)
        empty = np.zeros_like(self.data[i])
        h = self.headers[i].copy()
        h["ImageGetTime"] = time.time()

        # add data to self.data/self.headers so that existing functions can be used
        # make sure to remove them afterwards, not to interfere with other data writing
        logger.debug("Writing missing files for DIALS: {}".format(self.missing_range))

        for n in self.missing_range:
            self.headers[n] = h

            if self.do_centerDP:
                self.data_c[n] = empty
                self.write_smv_centered(path, n)
                del self.data_c[n]
            else:
                self.data[n] = empty
                self.write_smv(path, n)
                del self.data[n]
            del self.headers[n]

    def write_tiff(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        # PETS reads only 16bit unsignt integer TIFF
        img = np.round(img, 0).astype(np.uint16)

        fn = path / f"{i:05d}.tiff"
        write_tiff(fn, img, header=h)
        return fn

    def write_smv(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        beam_center = h["beam_center"]

        if self.do_stretch_correction:
            img = self.apply_stretch_correction(img, beam_center)
        img = np.ushort(img)
        shape_x, shape_y = img.shape
        
        phi = self.start_angle + self.osc_angle * (i-1)

        # TODO: Dials reads the beam_center from the first image and uses that for the whole range
        # For now, use the average beam center and consider it stationary, remove this line later
        beam_center = self.mean_beam_center
        
        header = collections.OrderedDict()
        header['HEADER_BYTES'] = 512
        header['DIM'] = 2
        header['BYTE_ORDER'] = "little_endian"
        header['TYPE'] = "unsigned_short"
        header['SIZE1'] = shape_x
        header['SIZE2'] = shape_y
        header['PIXEL_SIZE'] = self.physical_pixelsize
        header['BIN'] = "1x1"
        header['BIN_TYPE'] = "HW"
        header['ADC'] = "fast"
        header['CREV'] = 1
        header['BEAMLINE'] = "TimePix_SU"   # special ID for DIALS
        header['DETECTOR_SN'] = 901         # special ID for DIALS
        header['DATE'] = str(datetime.fromtimestamp(h["ImageGetTime"]))
        header['TIME'] = str(h["ImageExposureTime"])
        header['DISTANCE'] = "{:.4f}".format(self.distance)
        header['TWOTHETA'] = 0.00
        header['PHI'] = "{:.4f}".format(phi)
        header['OSC_START'] = "{:.4f}".format(phi)
        header['OSC_RANGE'] = "{:.4f}".format(self.osc_angle)
        header['WAVELENGTH'] = "{:.4f}".format(self.wavelength)
        # reverse XY coordinates for XDS
        header['BEAM_CENTER_X'] = "{:.4f}".format(beam_center[1])
        header['BEAM_CENTER_Y'] = "{:.4f}".format(beam_center[0])
        header['DENZO_X_BEAM'] = "{:.4f}".format((beam_center[0]*self.physical_pixelsize))
        header['DENZO_Y_BEAM'] = "{:.4f}".format((beam_center[1]*self.physical_pixelsize))
        fn = path / f"{i:05d}.img"
        write_adsc(fn, img, header=header)
        return fn
    
    def write_smv_centered(self, path, i):
        img= self.data_c[i]
        h = self.headers[i]

        beam_center = h["beam_center"]

        if self.do_stretch_correction:
            img = self.apply_stretch_correction(img, beam_center)
        img = np.ushort(img)
        shape_x, shape_y = img.shape
        
        phi = self.start_angle + self.osc_angle * (i-1)

        # TODO: Dials reads the beam_center from the first image and uses that for the whole range
        # For now, use the average beam center and consider it stationary, remove this line later
        beam_center = self.pbc
        
        header = collections.OrderedDict()
        header['HEADER_BYTES'] = 512
        header['DIM'] = 2
        header['BYTE_ORDER'] = "little_endian"
        header['TYPE'] = "unsigned_short"
        header['SIZE1'] = shape_x
        header['SIZE2'] = shape_y
        header['PIXEL_SIZE'] = self.physical_pixelsize
        header['BIN'] = "1x1"
        header['BIN_TYPE'] = "HW"
        header['ADC'] = "fast"
        header['CREV'] = 1
        header['BEAMLINE'] = "TimePix_SU"   # special ID for DIALS
        header['DETECTOR_SN'] = 901         # special ID for DIALS
        header['DATE'] = str(datetime.fromtimestamp(h["ImageGetTime"]))
        header['TIME'] = str(h["ImageExposureTime"])
        header['DISTANCE'] = "{:.4f}".format(self.distance)
        header['TWOTHETA'] = 0.00
        header['PHI'] = "{:.4f}".format(phi)
        header['OSC_START'] = "{:.4f}".format(phi)
        header['OSC_RANGE'] = "{:.4f}".format(self.osc_angle)
        header['WAVELENGTH'] = "{:.4f}".format(self.wavelength)
        # reverse XY coordinates for XDS
        header['BEAM_CENTER_X'] = "{:.4f}".format(beam_center[1])
        header['BEAM_CENTER_Y'] = "{:.4f}".format(beam_center[0])
        header['DENZO_X_BEAM'] = "{:.4f}".format((beam_center[0]*self.physical_pixelsize))
        header['DENZO_Y_BEAM'] = "{:.4f}".format((beam_center[1]*self.physical_pixelsize))
        fn = path / f"{i:05d}.img"
        write_adsc(fn, img, header=header)
        return fn

    def write_mrc(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        beam_center = h["beam_center"]

        fn = path / f"{i:05d}.mrc"

        if self.do_stretch_correction:
            img = self.apply_stretch_correction(img, beam_center)
        # flip up/down because RED reads images from the bottom left corner
        # for RED these need to be as integers

        dtype = np.int16
        if False:
            # Use maximum range available in data type for extra precision when converting from FLOAT to INT
            dynamic_range = 11900  # a little bit higher just in case
            maxval = np.iinfo(dtype).max
            img = (img / dynamic_range)*maxval
        img = np.round(img, 0).astype(dtype)
        img = np.flipud(img)
        
        write_mrc(fn, img)

        return fn

    def write_ed3d(self, path):
        path.mkdir(exist_ok=True)

        rotation_axis = np.degrees(self.rotation_axis)

        if self.start_angle > self.end_angle:
            sign = -1
        else:
            sign = 1

        with open(path / "1.ed3d", 'w') as f:
            print(f"WAVELENGTH    {self.wavelength}", file=f)
            print(f"ROTATIONAXIS    {rotation_axis:5f}", file=f)
            print(f"CCDPIXELSIZE    {self.pixelsize:5f}", file=f)
            print(f"GONIOTILTSTEP    {self.osc_angle:5f}", file=f)
            print(f"BEAMTILTSTEP    0", file=f)
            print(f"BEAMTILTRANGE    0.000", file=f)
            print(f"STRETCHINGMP    0.0", file=f)
            print(f"STRETCHINGAZIMUTH    0.0", file=f)
            print(f"", file=f)
            print(f"FILELIST", file=f)
        
            for i in self.observed_range:
                fn = "{:05d}.mrc".format(i)
                angle = self.start_angle+sign*self.osc_angle*i
                print(f"FILE {fn}    {angle: 12.4f}    0    {angle: 12.4f}", file=f)
            
            print(f"ENDFILELIST", file=f)

        logger.debug("Ed3d file created in path: {}".format(path))
        
    def write_xds_inp(self, path):
        from .XDS_template import XDS_template

        path.mkdir(exist_ok=True)

        nframes = max(self.complete_range)

        invert_rotation_axis = self.start_angle > self.end_angle
        rot_x, rot_y, rot_z = rotation_axis_to_xyz(self.rotation_axis, invert=invert_rotation_axis)

        shape_x, shape_y = self.data_shape

        if self.missing_range:
            exclude = "\n".join(["EXCLUDE_DATA_RANGE={} {}".format(i, j) for i, j in find_subranges(self.missing_range)])
        else:
            exclude = "!EXCLUDE_DATA_RANGE="
            
        if self.do_centerDP:
            s = XDS_template.format(
            date=str(time.ctime()),
            data_drc=self.smv_subdrc,
            data_begin=1,
            data_end=nframes,
            exclude=exclude,
            starting_angle=self.start_angle,
            wavelength=self.wavelength,
            # reverse XY coordinates for XDS
            origin_x=self.pbc[1],
            origin_y=self.pbc[0],
            NX=shape_y,
            NY=shape_x,
            sign="+",
            detector_distance=self.distance,
            QX=self.physical_pixelsize,
            QY=self.physical_pixelsize,
            osc_angle=self.osc_angle,
            calib_osc_angle=self.rotation_speed * self.acquisition_time,
            rot_x=rot_x,
            rot_y=rot_y,
            rot_z=rot_z
            )
        else:
            s = XDS_template.format(
                date=str(time.ctime()),
                data_drc=self.smv_subdrc,
                data_begin=1,
                data_end=nframes,
                exclude=exclude,
                starting_angle=self.start_angle,
                wavelength=self.wavelength,
                # reverse XY coordinates for XDS
                origin_x=self.mean_beam_center[1],
                origin_y=self.mean_beam_center[0],
                NX=shape_y,
                NY=shape_x,
                sign="+",
                detector_distance=self.distance,
                QX=self.physical_pixelsize,
                QY=self.physical_pixelsize,
                osc_angle=self.osc_angle,
                calib_osc_angle=self.rotation_speed * self.acquisition_time,
                rot_x=rot_x,
                rot_y=rot_y,
                rot_z=rot_z
                )
       
        with open(path / 'XDS.INP','w') as f:
            print(s, file=f)
        
        logger.info("XDS INP file created.")

    def write_beam_centers(self, drc):
        centers = np.zeros((max(self.observed_range), 2), dtype=np.float)
        for i, h in self.headers.items():
            centers[i-1] = h["beam_center"]
        for i in self.missing_range:
            centers[i-1] = [np.NaN, np.NaN]

        np.savetxt(drc / "beam_centers.txt", centers, fmt="%10.4f")

    def write_pets_inp(self, path):
        if self.start_angle > self.end_angle:
            sign = -1
        else:
            sign = 1

        with open(path / "pets.pts", "w") as f:
            date = str(time.ctime())
            print("# PETS input file for Rotation Electron Diffraction generated by `instamatic`", file=f)
            print(f"# {date}", file=f)
            print("# For definitions of input parameters, see:", file=f) 
            print("# http://pets.fzu.cz/ ", file=f)
            print("", file=f)
            print(f"lambda {self.wavelength}", file=f)
            print(f"Aperpixel {self.pixelsize}", file=f)
            print(f"phi 0.0", file=f)
            print(f"omega {np.degrees(self.rotation_axis + np.pi*2)}", file=f)
            print(f"bin 1", file=f)
            print(f"reflectionsize 20", file=f)
            print(f"noiseparameters 3.5 38", file=f)
            print("", file=f)
            # print("reconstructions", file=f)
            # print("endreconstructions", file=f)
            # print("", file=f)
            # print("distortions", file=f)
            # print("enddistortions", file=f)
            # print("", file=f)
            print("imagelist", file=f)
            for i in self.observed_range:
                fn = "{:05d}.tiff".format(i)
                angle = self.start_angle+sign*self.osc_angle*i
                print(f"tiff/{fn} {angle:10.4f} 0.00", file=f)
            print("endimagelist", file=f)
            