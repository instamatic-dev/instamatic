#! python2

from __future__ import division
from instamatic.formats import write_adsc
import os
import numpy as np
from datetime import datetime
import time
from instamatic.formats import read_tiff, write_tiff
from instamatic.processing.flatfield import apply_flatfield_correction
from instamatic.processing.stretch_correction import apply_stretch_correction
from instamatic import config
from instamatic.tools import find_beam_center
from itertools import izip
import collections

import logging
logger = logging.getLogger(__name__)


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
                 buffer, 
                 camera_length,
                 osangle,
                 startangle,
                 endangle,
                 rotation_angle,              # radians
                 acquisition_time,
                 resolution_range=(20, 0.8),
                 flatfield='flatfield.tiff'
                 ):
        flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.mrc_header = b'\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4B\x00\x00\xb4B\x00\x00\xb4B\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x888Fx\x06sA\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00MAP DA\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00aaaaaaaaaaaaaaaaaaaaaa,aaaaaaaaaaa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

        self.headers = {}
        self.data = {}

        self.smv_subdrc = "data"

        while len(buffer) != 0:
            i, img, h = buffer.pop(0)

            self.headers[i] = h

            if self.flatfield is not None:
                self.data[i] = apply_flatfield_correction(img, self.flatfield)
            else:
                self.data[i] = img

        self.data_shape = img.shape
        try:
            self.pixelsize = config.calibration.diffraction_pixeldimensions[camera_length] # px / Angstrom
        except KeyError:
            self.pixelsize = 1
            print "No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length)
            logger.warning("No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length))

        self.physical_pixelsize = config.camera.physical_pixelsize # mm
        self.wavelength = config.microscope.wavelength # angstrom
        # NOTE: Stretch correction - not sure if the azimuth and amplitude are correct anymore.
        self.stretch_azimuth = config.microscope.stretch_azimuth
        self.stretch_amplitude = config.microscope.stretch_amplitude

        self.beam_center = self.get_average_beam_center()
        self.distance = (1/self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osangle = osangle
        self.startangle = startangle
        self.endangle = endangle
        self.rotation_angle = rotation_angle
        self.dmax, self.dmin = resolution_range
        self.nframes = max(self.data.keys())
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = get_calibrated_rotation_speed(osangle / self.acquisition_time) 

        logger.debug("Primary beam at: {}".format(self.beam_center))

    def get_average_beam_center(self):
        # take every 10th frame for beam center determination to speed up the calculation
        return np.mean([find_beam_center(img, sigma=10) for img in self.data.values()[1::10]], axis=0)

    def fixStretchCorrection(self, image, directXY):
        center = np.copy(directXY)
        
        azimuth   = self.stretch_azimuth
        amplitude = self.stretch_amplitude
        
        newImage = apply_stretch_correction(image, center=center, azimuth=azimuth, amplitude=amplitude)
    
        return newImage

    def makedirs(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def tiff_writer(self, path):
        print ("Writing TIFF files......")

        os.makedirs(path)

        for i in self.data.keys():
            self.write_tiff(path, i)

        logger.debug("Tiff files saved in folder: {}".format(path))

    def smv_writer(self, path):
        print ("Writing SMV files......")

        path = os.path.join(path, self.smv_subdrc)
        self.makedirs(path)
    
        for i in self.data.keys():
            self.write_smv(path, i)
               
        logger.debug("SMV files saved in folder: {}".format(path))
     
    def mrc_writer(self, path):
        print ("Writing MRC files......")

        self.makedirs(path)

        for i in self.data.keys():
            self.write_mrc(path, i)

        logger.debug("MRC files created in folder: {}".format(path))

    def threadpoolwriter(self, tiff_path=None, smv_path=None, mrc_path=None, workers=8):
        write_tiff = tiff_path is not None
        write_smv  = smv_path  is not None
        write_mrc  = mrc_path  is not None

        if write_smv:
            smv_path = os.path.join(smv_path, self.smv_subdrc)
            self.makedirs(smv_path)
            logger.debug("SMV files saved in folder: {}".format(smv_path))

        if write_tiff:
            self.makedirs(tiff_path)
            logger.debug("Tiff files saved in folder: {}".format(tiff_path))

        if write_mrc:
            self.makedirs(mrc_path)
            logger.debug("MRC files saved in folder: {}".format(mrc_path))

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for i in self.data.keys():
                
                if write_tiff:
                    futures.append(executor.submit(self.write_tiff, tiff_path, i))
                if write_mrc:
                    futures.append(executor.submit(self.write_mrc, mrc_path, i))
                if write_smv:
                    futures.append(executor.submit(self.write_smv, smv_path, i))

            for future in futures:
                ret = future.result()

    def write_tiff(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        fn = os.path.join(path, "{:05d}.tiff".format(i))
        write_tiff(fn, img, header=h)
        return fn

    def write_smv(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        img = self.fixStretchCorrection(img, self.beam_center)
        img = np.ushort(img)
        shape_x, shape_y = img.shape
        
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
        header['BEAMLINE'] = "TIMEPIX_SU"   # special ID for DIALS
        header['DETECTOR_SN'] = 901         # special ID for DIALS
        header['DATE'] = str(datetime.fromtimestamp(h["ImageGetTime"]))
        header['TIME'] = str(h["ImageExposureTime"])
        header['DISTANCE'] = "{:.2f}".format(self.distance)
        header['TWOTHETA'] = 0.00
        header['PHI'] = self.startangle
        header['OSC_START'] = self.startangle
        header['OSC_RANGE'] = self.osangle
        header['WAVELENGTH'] = self.wavelength
        # reverse XY coordinates for XDS
        header['BEAM_CENTER_X'] = "%.2f" % self.beam_center[1]
        header['BEAM_CENTER_Y'] = "%.2f" % self.beam_center[0]
        header['DENZO_X_BEAM'] = "%.2f" % (self.beam_center[0]*self.physical_pixelsize)
        header['DENZO_Y_BEAM'] = "%.2f" % (self.beam_center[1]*self.physical_pixelsize)
        fn = os.path.join(path, "{:05d}.img".format(i))
        write_adsc(fn, img, header=header)
        return fn

    def write_mrc(self, path, i):
        img = self.data[i]
        h = self.headers[i]

        fn = os.path.join(path, "{:05d}.mrc".format(i))

        # flip up/down because RED reads images from the bottom left corner
        img = self.fixStretchCorrection(img, self.beam_center)
        img = np.flipud(img.astype(np.int16))
        
        with open(fn, "wb") as mrcf:
            mrcf.write(self.mrc_header)
            mrcf.write(img.tobytes())
        return fn


    def write_ed3d(self, path):
        self.makedirs(path)

        ed3d = open(os.path.join(path, "1.ed3d"), 'w')

        rotation_angle = np.degrees(self.rotation_angle)

        if self.startangle > self.endangle:
            sign = -1
        else:
            sign = 1

        ed3d.write("WAVELENGTH    {}\n".format(self.wavelength))
        ed3d.write("ROTATIONAXIS    {}\n".format(rotation_angle))
        ed3d.write("CCDPIXELSIZE    {}\n".format(self.pixelsize))
        ed3d.write("GONIOTILTSTEP    {}\n".format(self.osangle))
        ed3d.write("BEAMTILTSTEP    0\n")
        ed3d.write("BEAMTILTRANGE    0.000\n")
        ed3d.write("STRETCHINGMP    0.0\n")
        ed3d.write("STRETCHINGAZIMUTH    0.0\n")
        ed3d.write("\n")
        ed3d.write("FILELIST\n")
    
        for i in self.data.keys():

            img = self.data[i]
            h = self.headers[i]

            fn = "{:05d}.mrc".format(i)
            ed3d.write("FILE {fn}    {ang}    0    {ang}\n".format(fn=fn, ang=self.startangle+sign*self.osangle*i))
        
        ed3d.write("ENDFILELIST")
        ed3d.close()
        logger.debug("Ed3d file created in path: {}".format(path))
        
    def write_xds_inp(self, path):
        from XDS_template import XDS_template
        from math import cos, pi

        self.makedirs(path)

        nframes = self.nframes
        rotation_angle = self.rotation_angle # radians

        if self.startangle > self.endangle:
            rotation_angle += np.pi

        shape_x, shape_y = self.data_shape

        if nframes != len(self.data.keys()):
            exclude = "\n".join(["EXCLUDE_DATA_RANGE={} {}".format(i, i) for i in range(1, nframes+1) if i not in self.data.keys()])
        else:
            exclude = "!EXCLUDE_DATA_RANGE="

        s = XDS_template.format(
            date=str(time.ctime()),
            data_drc=self.smv_subdrc,
            data_begin=1,
            data_end=nframes,
            exclude=exclude,
            starting_angle=self.startangle,
            wavelength=self.wavelength,
            dmin=self.dmin,
            dmax=self.dmax,
            # reverse XY coordinates for XDS
            origin_x=self.beam_center[1],
            origin_y=self.beam_center[0],
            NX=shape_y,
            NY=shape_x,
            sign="+",
            detdist=self.distance,
            QX=self.physical_pixelsize,
            QY=self.physical_pixelsize,
            osangle=self.osangle,
            calib_osangle=self.rotation_speed * self.acquisition_time,
            rot_x=cos(rotation_angle),
            rot_y=cos(rotation_angle+np.pi/2),
            rot_z=0.0
            )
       
        with open(os.path.join(path, 'XDS.INP'),'w') as f:
            f.write(s)
        
        logger.info("XDS INP file created.")


