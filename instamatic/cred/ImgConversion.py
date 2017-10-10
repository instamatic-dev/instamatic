#! python2

from __future__ import division
from instamatic.formats import write_adsc
import os
import numpy as np
from instamatic.formats import read_tiff, write_tiff
from instamatic.processing.flatfield import apply_flatfield_correction
from instamatic.processing.stretch_correction import apply_stretch_correction
from instamatic.TEMController import config
from instamatic.tools import find_beam_center
from itertools import izip

import logging
logger = logging.getLogger(__name__)


def pixelsize2cameralength(pixelsize):
    # TODO: fix magic number, can this be calculated from the pixelsize directly?
    # for physical_pixelsize = 0.055 mm
    magic_number = 2.19122
    return magic_number / pixelsize


def get_calibrated_rotation_speed(val):
    """Correct for the overestimation of the oscillation angle if the rotation 
    was stopped before interrupting the data collection. It uses calibrated values for the 
    rotation speeds of the microscope, and matches them to the observed one"""

    rotation_speeds = set(config.specifications["rotation_speeds"]["coarse"] + config.specifications["rotation_speeds"]["fine"])
    calibrated_value = min(rotation_speeds, key=lambda x:abs(x-val))
    print "Correcting oscillation angle from {} to calibrated value {}".format(val, calibrated_value)
    return calibrated_value


class ImgConversion(object):
    
    'This class is for post cRED data collection image conversion and necessary files generation for REDp and XDS processing, as well as DIALS processing'

    def __init__(self, 
                 buffer, 
                 camera_length,
                 osangle,
                 startangle,
                 endangle,
                 rotation_angle,
                 acquisition_time,
                 resolution_range=(20, 0.8),
                 flatfield='flatfield.tiff'
                 ):
        self.pxd = config.diffraction_pixeldimensions
        curdir = os.path.dirname(os.path.realpath(__file__))
        flatfield, h = read_tiff(os.path.join(curdir, flatfield))
        self.flatfield = flatfield

        self.mrc_header = b'\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4B\x00\x00\xb4B\x00\x00\xb4B\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x888Fx\x06sA\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00MAP DA\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00aaaaaaaaaaaaaaaaaaaaaa,aaaaaaaaaaa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

        self.headers = []
        self.data = []

        while len(buffer) != 0:
            img, h = buffer.pop(0)
            self.headers.append(h)
            self.data.append(apply_flatfield_correction(img, self.flatfield))

        self.pixelsize = self.pxd[camera_length]
        self.physical_pixelsize = 0.055 # mm
        self.wavelength = 0.025080
        self.beam_center = self.get_average_beam_center()
        self.distance = pixelsize2cameralength(self.pixelsize)
        self.osangle = osangle
        self.startangle = startangle
        self.endangle = endangle
        self.rotation_angle = rotation_angle
        self.dmax, self.dmin = resolution_range
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = get_calibrated_rotation_speed(osangle / self.acquisition_time) 

        logger.debug("Primary beam at: {}".format(self.beam_center))

    def get_average_beam_center(self):
        return np.mean([find_beam_center(img, sigma=10) for img in self.data], axis=0)

    def writeTiff(self, path):
        print ("Writing TIFF files......")

        for i, (img, h) in enumerate(izip(self.data, self.headers)):
            j = i + 1
            fn = os.path.join(path, "{:05d}.tiff".format(j))
            write_tiff(fn, img, header=h)
        logger.debug("Tiff files saved in folder: {}".format(path))

    def writeIMG(self, path):
        import collections
        print ("Writing SMV files......")
    
        for i, (img, h) in enumerate(izip(self.data, self.headers)):
            j = i + 1

            img = np.ushort(img)

            # NOTE: Stretch correction?
            
            ## if it's corrected image, need to take away the two extra rows and columns
            if len(img) == 516:
                newimg = np.zeros([512,512], dtype=np.ushort)
                newimg[0:256,0:256] = img[0:256,0:256]
                newimg[256:,0:256] = img[260:,0:256]
                newimg[0:256,256:] = img[0:256,260:]
                newimg[256:,256:] = img[260:,260:]
                img = newimg
            
            header = collections.OrderedDict()
            header['HEADER_BYTES'] = 512
            header['DIM'] = 2
            header['BYTE_ORDER'] = "little_endian"
            header['TYPE'] = "unsigned_short"
            header['SIZE1'] = 512
            header['SIZE2'] = 512
            header['PIXEL_SIZE'] = self.physical_pixelsize
            header['BIN'] = "1x1"
            header['BIN_TYPE'] = "HW"
            header['ADC'] = "fast"
            header['CREV'] = 1
            header['BEAMLINE'] = "TIMEPIX_SU"   # special ID for DIALS
            header['DETECTOR_SN'] = 901         # special ID for DIALS
            header['DATE'] = str(h["ImageGetTime"])
            header['TIME'] = str(h["ImageExposureTime"])
            header['DISTANCE'] = "{:.2f}".format(self.distance)
            header['TWOTHETA'] = 0.00
            header['PHI'] = self.startangle
            header['OSC_START'] = self.startangle
            header['OSC_RANGE'] = self.osangle
            header['WAVELENGTH'] = self.wavelength
            header['BEAM_CENTER_X'] = "%.2f" % self.beam_center[0]
            header['BEAM_CENTER_Y'] = "%.2f" % self.beam_center[1]
            # NOTE: where does the 0.05 come from?
            header['DENZO_X_BEAM'] = "%.2f" % (self.beam_center[0]*self.physical_pixelsize)
            header['DENZO_Y_BEAM'] = "%.2f" % (self.beam_center[1]*self.physical_pixelsize)
            
            fn = os.path.join(path, "{:05d}.img".format(j))
            newimg = write_adsc(fn, img, header=header)
        
        logger.debug("SMV files (size 512*512) saved in folder: {}".format(path))
     
    def fixDistortion(self, image, directXY):
        center = np.copy(directXY)
        
        if directXY[0] > (255):
            center[0] += 1
        if directXY[0] > (256):
            center[0] += 2
        if directXY[0] > (257):
            center[0] += 1
                
        if directXY[1] > (255):
            center[1] += 1
        if directXY[1] > (256):
            center[1] += 2
        if directXY[1] > (257):
            center[1] += 1
             
        azimuth   = -6.61
        amplitude =  2.43
        
        newImage = apply_stretch_correction(image, center=center, azimuth=azimuth, amplitude=amplitude)
    
        return newImage
            
    def MRCCreator(self, path):
        print ("Writing MRC files......")

        for i, img in enumerate(self.data):
            j = i + 1
            fn = os.path.join(path, "{:05d}.mrc".format(j))

            img = img.astype(np.int16)[::-1,:]  # NOTE: what is this trickery with reversing the image?
            img = self.fixDistortion(img, self.beam_center)
           
            with open(fn, "wb") as mrcf:
                mrcf.write(self.mrc_header)
                mrcf.write(img.tobytes())
            
        logger.debug("MRC files created in folder: {}".format(path))
        
    def ED3DCreator(self, path, rotation_angle):
        print ("Creating ed3d file......")
    
        ed3d = open(os.path.join(path, "1.ed3d"), 'w')

        if self.startangle > self.endangle:
            sign = -1
        else:
            sign = 1
        
        ed3d.write("WAVELENGTH    {}\n".format(self.wavelength))
        ed3d.write("ROTATIONAXIS    {}\n".format(rotation_angle-(sign-1)*90))
        ed3d.write("CCDPIXELSIZE    {}\n".format(self.pixelsize))
        ed3d.write("GONIOTILTSTEP    {}\n".format(self.osangle))
        ed3d.write("BEAMTILTSTEP    0\n")
        ed3d.write("BEAMTILTRANGE    0.000\n")
        ed3d.write("STRETCHINGMP    0.0\n")
        ed3d.write("STRETCHINGAZIMUTH    0.0\n")
        ed3d.write("\n")
        ed3d.write("FILELIST\n")
    
        for i in range(len(self.data)):
            j = i + 1
            fn = "{:05d}.mrc".format(j)
            ed3d.write("FILE {fn}    {ang}    0    {ang}\n".format(fn=fn, ang=self.startangle+sign*self.osangle*i))
        
        ed3d.write("ENDFILELIST")
        ed3d.close()
        logger.debug("Ed3d file created in path: {}".format(path))
        
    def XDSINPCreator(self, pathsmv, rotation_angle):
        print ("Creating XDS inp file......")
        from XDS_template import XDS_template
        from math import cos, pi

        indend = len(self.data)

        if self.startangle > self.endangle:
            sign = -1
        else:
            sign = 1

        s = XDS_template.format(
            data_begin=1,
            data_end=indend,
            starting_angle=self.startangle,
            wavelength=self.wavelength,
            dmin=self.dmin,
            dmax=self.dmax,
            origin_x=self.beam_center[0],
            origin_y=self.beam_center[1],
            sign="+",

            # Divide distnace by 1.1 to account for wrongly defined physical pixelsize 
            # in XDS input file (0.050 instead of 0.055 mm)
            detdist=self.distance/1.1,
            osangle=self.osangle,
            calib_osangle=self.rotation_speed * self.acquisition_time,
            rot_x=cos(rotation_angle-(sign-1)*np.pi/2),
            rot_y=cos(rotation_angle-(sign-1)*np.pi/2+np.pi/2),
            rot_z=0.0
            )
       
        with open(os.path.join(pathsmv, 'XDS.INP'),'w') as f:
            f.write(s)
        
        logger.debug(" >> Wrote XDS.inp.")
