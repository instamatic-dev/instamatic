#! python2

from __future__ import division
from instamatic.formats import adscimage
import datetime
import glob
import os
import numpy as np
from instamatic.flatfield import apply_flatfield_correction
from instamatic.formats import read_tiff
import msvcrt
from instamatic.processing.stretch_correction import apply_stretch_correction
from instamatic.TEMController import config
from instamatic.tools import find_beam_center

import logging
logger = logging.getLogger(__name__)


class ImgConversion(object):
    
    'This class is for post cRED data collection image conversion and necessary files generation for REDp and XDS processing, as well as DIALS processing'

    def __init__(self,expdir, flatfield='flatfield_tpx_2017-06-21.tiff'):
        self.pxd = config.diffraction_pixeldimensions
        curdir = os.path.dirname(os.path.realpath(__file__))
        flatfield, h = read_tiff(os.path.join(curdir, flatfield))
        data=flatfield
        newdata=np.zeros([512,512],dtype=np.ushort)
        newdata[0:256,0:256]=data[0:256,0:256]
        newdata[256:,0:256]=data[260:,0:256]
        newdata[0:256,256:]=data[0:256,260:]
        newdata[256:,256:]=data[260:,260:]
        flatfield=newdata
        mrc_header=b'\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x02\x00\x00\x04\x02\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4B\x00\x00\xb4B\x00\x00\xb4B\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x888Fx\x06sA\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00MAP DA\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00aaaaaaaaaaaaaaaaaaaaaa,aaaaaaaaaaa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

        self.flatfield=flatfield
        self.mrc_header=mrc_header
        
    def TiffToIMG(self, pathtiff, pathsmv, cl, startangle, osangle):
        import collections
        print ("Tiff converting to IMG......")
    
        nowt = datetime.datetime.now()
        listing = glob.glob(os.path.join(pathtiff,"*.tiff"))
    
        px = self.pxd[cl]
        
        # TODO: fix magic numbers, can this be calculated from the pixelsize directly?
        # Distance *1.1 to facilitate DIALS processing since pixel size was changed to 0.055
        distance = 483.89*0.00412/px*1.1
        
        filenamelist = []
        
        for f in listing:
            fnm = os.path.splitext(os.path.basename(f))[0]
            filenamelist.append(fnm)
        
        pbc=[]
        for f in filenamelist:
            img, h = read_tiff(os.path.join(pathtiff,"{}.tiff".format(f)))
            pb = find_beam_center(img)
            pbc.append(pb)
        
        pb = np.mean(np.array(pbc), axis=0)
    
        logger.debug("Primary beam at: {}".format(pb))

        for f in filenamelist:


            img, h = read_tiff(os.path.join(pathtiff,"{}.tiff".format(f)))
            data=np.ushort(img)

            # TODO: this is already done by the data collection, also use 2.3 instead of 2.7
            ## if it's original tiff image from Sophy need to correct the intensity at cross
            if len(data)==512:
                data[255,:]=data[255,:]/2.7
                data[256,:]=data[256,:]/2.7
                data[:,255]=data[:,255]/2.7
                data[:,256]=data[:,256]/2.7
            
            ## if it's corrected image, need to take away the two extra rows and columns
            if len(data)==516:
                newdata=np.zeros([512,512],dtype=np.ushort)
                newdata[0:256,0:256]=data[0:256,0:256]
                newdata[256:,0:256]=data[260:,0:256]
                newdata[0:256,256:]=data[0:256,260:]
                newdata[256:,256:]=data[260:,260:]
                data=newdata
            
            data = apply_flatfield_correction(data, self.flatfield)
            data = np.ushort(data)
            header = collections.OrderedDict()
            header['HEADER_BYTES'] = 512
            header['DIM'] = 2
            header['BYTE_ORDER'] = "little_endian"
            header['TYPE'] = "unsigned_short"
            header['SIZE1'] = 512
            header['SIZE2'] = 512
            header['PIXEL_SIZE'] = 0.055000
            header['BIN'] = "1x1"
            header['BIN_TYPE'] = "HW"
            header['ADC'] = "fast"
            header['CREV'] = 1
            header['BEAMLINE'] = "TIMEPIX_SU"
            header['DETECTOR_SN'] = 901
            header['DATE'] = "{}".format(nowt)
            header['TIME'] = 0.096288
            header['DISTANCE'] = "%.2f" % distance
            header['TWOTHETA'] = 0.00
            header['PHI'] = startangle
            header['OSC_START'] = startangle
            header['OSC_RANGE'] = osangle
            header['WAVELENGTH'] = 0.025080
            header['BEAM_CENTER_X'] = "%.2f" % pb[0]
            header['BEAM_CENTER_Y'] = "%.2f" % pb[1]
            header['DENZO_X_BEAM'] = "%.2f" % (pb[1]*0.05)
            header['DENZO_Y_BEAM'] = "%.2f" % (pb[0]*0.05)
            newimg=adscimage.adscimage(data,header)
            newimg.write(os.path.join(pathsmv,"{}.img".format(f)))
        
        logger.debug("SMV files (size 512*512) saved in folder: {}".format(pathsmv))
        return pb
     
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
            
    def MRCCreator(self, pathtiff, pathred, header, pb):
        
        print ("Tiff converting to MRC......")
        listing = glob.glob(os.path.join(pathtiff,"*.tiff"))
        filenamelist = []
        for f in listing:
            fnm = os.path.splitext(os.path.basename(f))[0]
            filenamelist.append(int(fnm))
        filenamelist = np.sort(filenamelist)
        ind = 1
        for f in listing:
            img, h = read_tiff(f)
            data = img
            data = data.astype(np.int16)[::-1,:]
            
            with open(os.path.join(pathred,"{:05d}.mrc".format(ind)), "wb") as mrcf:
                mrcf.write(header)
                data = self.fixDistortion(data, pb)
                mrcf.write(data.tobytes())
            ind += 1
            
        logger.debug("MRC files created in folder: {}".format(pathred))
        
    def ED3DCreator(self, pathtiff, pathred, pxs, startangle, osangle, rot_angle):
        print ("Creating ed3d file......")
        listing = glob.glob(os.path.join(pathtiff, "*.tiff"))
    
        ed3d = open(os.path.join(pathred, "1.ed3d"), 'w')
        
        ed3d.write("WAVELENGTH    0.02508\n")
        ed3d.write("ROTATIONAXIS    {}\n".format(rot_angle))
        ed3d.write("CCDPIXELSIZE    {}\n".format(pxs))
        ed3d.write("GONIOTILTSTEP    {}\n".format(osangle))
        ed3d.write("BEAMTILTSTEP    0\n")
        ed3d.write("BEAMTILTRANGE    0.000\n")
        ed3d.write("STRETCHINGMP    0.0\n")
        ed3d.write("STRETCHINGAZIMUTH    0.0\n")
        ed3d.write("\n")
        ed3d.write("FILELIST\n")
    
        for i, fn in enumerate(listing):
            basename = os.path.splitext(os.path.basename(fn))[0]
            # MRC files are named as %05d.mrc
            ed3d.write("FILE {name}.mrc    {ang}    0    {ang}\n".format(name=basename, ang=startangle+osangle*i))
        
        ed3d.write("ENDFILELIST")
        ed3d.close()
        logger.debug("Ed3d file created in path: {}".format(pathred))
        
    def XDSINPCreator(self, pathsmv, indend, startangle, dmin, dmax, beam_center, camlen, osangle, rot_angle):
        print ("Creating XDS inp file......")
        from XDS_template import XDS_template
        from math import cos, pi

        px = self.pxd[camlen]

        # TODO: fix magic numbers, can this be calculated from the pixelsize directly?
        distance = 483.89*0.00412/px

        s = XDS_template.format(
            data_begin=1,
            data_end=indend,
            starting_angle=startangle,
            dmin=dmin,
            dmax=dmax,
            origin_x=beam_center[0],
            origin_y=beam_center[1],
            sign="+",
            detdist=distance,
            osangle=osangle,
            rot_x=cos(rot_angle),
            rot_y=cos(rot_angle+np.pi/2),
            rot_z=0.0
            )
       
        with open(os.path.join(pathsmv, 'XDS.INP'),'w') as f:
            f.write(s)
        
        logger.debug(" >> Wrote XDS.inp.")
        
    def wait(self):
        msvcrt.getch()
