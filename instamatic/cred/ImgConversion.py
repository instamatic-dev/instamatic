#! python2

from __future__ import division
from instamatic.formats import adscimage
import datetime
import glob
import os
import numpy as np
from instamatic.flatfield import apply_flatfield_correction
from instamatic.formats import read_tiff
from instamatic.processing.stretch_correction import apply_stretch_correction
from instamatic.TEMController import config
from instamatic.tools import find_beam_center

import logging
logger = logging.getLogger(__name__)


class ImgConversion(object):
    
    'This class is for post cRED data collection image conversion and necessary files generation for REDp and XDS processing, as well as DIALS processing'

    def __init__(self, 
                 pathtiff, 
                 camera_length,
                 osangle,
                 startangle,
                 endangle,
                 rotation_angle,
                 resolution_range=(20, 0.8),
                 flatfield='flatfield_tpx_2017-06-21.tiff'
                 ):
        self.pxd = config.diffraction_pixeldimensions
        curdir = os.path.dirname(os.path.realpath(__file__))
        flatfield, h = read_tiff(os.path.join(curdir, flatfield))
        data = flatfield
        newdata = np.zeros([512,512], dtype=np.ushort)
        newdata[0:256,0:256] = data[0:256,0:256]
        newdata[256:,0:256] = data[260:,0:256]
        newdata[0:256,256:] = data[0:256,260:]
        newdata[256:,256:] = data[260:,260:]
        flatfield=newdata
        self.mrc_header=b'\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4B\x00\x00\xb4B\x00\x00\xb4B\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x888Fx\x06sA\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00MAP DA\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00aaaaaaaaaaaaaaaaaaaaaa,aaaaaaaaaaa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

        self.flatfield = flatfield

        self.fns = fns = glob.glob(os.path.join(pathtiff, "*.tiff"))
        self.data = [read_tiff(fn)[0] for fn in fns]

        self.pixelsize = self.pxd[camera_length]
        self.physical_pixelsize = 0.055 # mm
        self.wavelength = 0.025080
        self.beam_center = self.get_average_beam_center()
        self.distance = 483.89*0.00412/self.pixelsize
        self.osangle = osangle
        self.startangle = startangle
        self.endangle = endangle
        self.rotation_angle = rotation_angle
        self.dmax, self.dmin = resolution_range
        logger.debug("Primary beam at: {}".format(self.beam_center))
        
    def get_average_beam_center(self):
        return np.mean([find_beam_center(img) for img in self.data], axis=0)

    def TiffToIMG(self, pathtiff, pathsmv, cl, startangle, osangle):
        import collections
        print ("Tiff converting to IMG......")
    
        nowt = datetime.datetime.now()

        for fn, img in zip(self.fns, self.data):
            img = apply_flatfield_correction(img, self.flatfield)
            img = np.ushort(img)

            # TODO: this is already done by the img collection, also use 2.3 instead of 2.7
            ## if it's original tiff image from Sophy need to correct the intensity at cross
            if len(img) == 512:
                img[255,:] = img[255,:]/2.7
                img[256,:] = img[256,:]/2.7
                img[:,255] = img[:,255]/2.7
                img[:,256] = img[:,256]/2.7
            
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
            header['BEAMLINE'] = "TIMEPIX_SU"
            header['DETECTOR_SN'] = 901
            header['DATE'] = "{}".format(nowt)
            header['TIME'] = 0.096288  # NOTE: where does this number come from?

            # TODO: fix magic numbers, can this be calculated from the pixelsize directly?
            # Distance *1.1 to facilitate DIALS processing since pixel size was changed to 0.055
            header['DISTANCE'] = "{:.2f}".format(self.distance*1.1)
            header['TWOTHETA'] = 0.00
            header['PHI'] = startangle
            header['OSC_START'] = startangle
            header['OSC_RANGE'] = osangle
            header['WAVELENGTH'] = self.wavelength
            header['BEAM_CENTER_X'] = "%.2f" % self.beam_center[0]
            header['BEAM_CENTER_Y'] = "%.2f" % self.beam_center[1]
            # NOTE: where does the 0.05 come from?
            header['DENZO_X_BEAM'] = "%.2f" % (self.beam_center[0]*0.05)
            header['DENZO_Y_BEAM'] = "%.2f" % (self.beam_center[1]*0.05)
            
            newimg = adscimage.adscimage(img, header)
            newimg.write(os.path.join(pathsmv, fn.replace(".tiff", ".img")))
        
        logger.debug("SMV files (size 512*512) saved in folder: {}".format(pathsmv))
     
    def fixDistortion(self, image, directXY):
        center = np.copy(directXY)
        
        if directXY[0]>(255):
            center[0] += 1
        if directXY[0]>(256):
            center[0] += 2
        if directXY[0]>(257):
            center[0] += 1
                
        if directXY[1]>(255):
            center[1] += 1
        if directXY[1]>(256):
            center[1] += 2
        if directXY[1]>(257):
            center[1] += 1
             
        azimuth   = -6.61
        amplitude =  2.43
        
        newImage = apply_stretch_correction(image, center=center, azimuth=azimuth, amplitude=amplitude)
    
        return newImage
            
    def MRCCreator(self, pathred):
        print ("Tiff converting to MRC......")

        for fn, img in zip(self.fns, self.data):
            img = img.astype(np.int16)[::-1,:]  # NOTE: what is this trickery with reversing the image?
            img = self.fixDistortion(img, self.beam_center)
           
            with open(os.path.join(pathred, fn.replace(".tiff", ".mrc")), "wb") as mrcf:
                mrcf.write(self.mrc_header)
                mrcf.write(img.tobytes())
            
        logger.debug("MRC files created in folder: {}".format(pathred))
        
    def ED3DCreator(self, pathred, rotation_angle):
        print ("Creating ed3d file......")
    
        ed3d = open(os.path.join(pathred, "1.ed3d"), 'w')
        
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
    
        for i, fn in enumerate(self.fns):
            fn_mrc = fn.replace(".tiff", ".mrc")
            ed3d.write("FILE {name}    {ang}    0    {ang}\n".format(name=fn_mrc, ang=self.startangle+self.osangle*i))
        
        ed3d.write("ENDFILELIST")
        ed3d.close()
        logger.debug("Ed3d file created in path: {}".format(pathred))
        
    def XDSINPCreator(self, pathsmv, rotation_angle):
        print ("Creating XDS inp file......")
        from XDS_template import XDS_template
        from math import cos, pi

        indend = len(self.data)

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
            detdist=self.distance,
            osangle=self.osangle,
            rot_x=cos(rotation_angle),
            rot_y=cos(rotation_angle+np.pi/2),
            rot_z=0.0
            )
       
        with open(os.path.join(pathsmv, 'XDS.INP'),'w') as f:
            f.write(s)
        
        logger.debug(" >> Wrote XDS.inp.")
