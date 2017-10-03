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
from instamatic.processing.stretch_correction import apply_transform_to_image, affine_transform_circle_to_ellipse
from instamatic.TEMController import config

import logging
logger = logging.setLogger(__name__)

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
        
    def TiffToIMG(self,pathtiff,pathsmv,cl,startangle,osangle):
        import collections
        print ("Tiff converting to IMG......")
    
        if osangle < 0:
            osangle=-osangle
            
        nowt=datetime.datetime.now()
        listing=glob.glob(os.path.join(pathtiff,"*.tiff"))
    
        px=self.pxd[cl]
        
        #Distance *1.1 to facilitate DIALS processing since pixel size was changed to 0.055
        distance=483.89*0.00412/px*1.1
        
        filenamelist=[]
        
        for f in listing:
            fnm=os.path.splitext(os.path.basename(f))[0]
            filenamelist.append(fnm)
        
        pbc=[]
        for f in filenamelist:
            img, h = read_tiff(os.path.join(pathtiff,"{}.tiff".format(f)))
            pb=np.where(img.data>10000)
            pbc.append([np.mean(pb[0]),np.mean(pb[1])])
        
        #warnings.filterwarnings('error')

        #try:
        pbc=np.asarray(pbc)
        pbc=pbc[~np.isnan(pbc)]
        pbc=np.reshape(pbc,[len(pbc)/2,2])
        pb=[np.mean(pbc[:,1]),np.mean(pbc[:,0])]
        #except:
            #logger.debug("An error caught.")
    
        logger.debug("Primary beam at: {}".format(pb))

        for f in filenamelist:
            img, h = read_tiff(os.path.join(pathtiff,"{}.tiff".format(f)))
            data=np.ushort(img.data)
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
            
            data=apply_flatfield_correction(data, self.flatfield)
            data=np.ushort(data)
            header=collections.OrderedDict()
            header['HEADER_BYTES'] =512
            header['DIM'] =2
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
     
    def fixDistortion(self,image,directXY):
    
        radianAzimuth = np.radians(90)
        stretch = 1.3 * 0.01
        
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
             
        c2e = self.affine_transform_circle_to_ellipse(radianAzimuth, stretch)
        newImage = apply_transform_to_image(image[::-1,:], c2e, center)[::-1,:]
    
        return newImage
            
    def MRCCreator(self,pathtiff,pathred,header,pb):
        
        print ("Tiff converting to MRC......")
        listing=glob.glob(os.path.join(pathtiff,"*.tiff"))
        filenamelist=[]
        for f in listing:
            fnm=os.path.splitext(os.path.basename(f))[0]
            filenamelist.append(int(fnm))
        filenamelist=np.sort(filenamelist)
        ind=10000
        for f in filenamelist:
            img, h = read_tiff(os.path.join(pathtiff,"{}.tiff".format(f)))
            data=img.data
            data=data.astype(np.int16)[::-1,:]
            
            with open(os.path.join(pathred,"{}.mrc".format(ind)), "wb") as mrcf:
                mrcf.write(header)
                data=self.fixDistortion(data,pb)
                mrcf.write(data.tobytes())
            ind=ind+1
            
        logger.debug("MRC files created in folder: {}".format(pathred))
        
    def ED3DCreator(self,pathtiff,pathred,pxs,startangle,endangle):
        print ("Creating ed3d file......")
        listing=glob.glob(os.path.join(pathtiff,"*.tiff"))
        filenamelist=[]
        for f in listing:
            fnm=os.path.splitext(os.path.basename(f))[0]
            filenamelist.append(fnm)
    
        ed3d=open(os.path.join(pathred,"1.ed3d"),'w')
        
        low=startangle
        up=endangle
        nb=len(listing)
        step=(up-low)/nb
        
        ed3d.write("WAVELENGTH    0.02508\n")
        ed3d.write("ROTATIONAXIS    -38.5\n")
        ed3d.write("CCDPIXELSIZE    {}\n".format(pxs))
        ed3d.write("GINIOTILTSTEP    {}\n".format(step))
        ed3d.write("BEAMTILTSTEP    0\n")
        ed3d.write("BEAMTILTRANGE    0.000\n")
        ed3d.write("STRETCHINGMP    0.0\n")
        ed3d.write("STRETCHINGAZIMUTH    0.0\n")
        ed3d.write("\n")
        ed3d.write("FILELIST\n")
    
        ind=10000
        for j in range(0,nb):
            ed3d.write("FILE {}.mrc    {}    0    {}\n".format(ind,low+step*j,low+step*j))
            """MRC files are named as 10???.mrc"""
            ind=ind+1
        
        ed3d.write("ENDFILELIST")
        ed3d.close()
        logger.debug("Ed3d file created in path: {}".format(pathred))
        
    def XDSINPCreator(self,pathsmv,indend,startangle,lowres,highres,pb,cl,osangle,RA):
        print ("Creating XDS inp file......")
        from math import cos,pi
        if osangle < 0:
            osangle=-osangle
        px=self.pxd[cl]
        distance=483.89*0.00412/px
        curdir = os.path.dirname(os.path.realpath(__file__))
        f=open(os.path.join(curdir,'XDS_template.INP'),'r')
        f_xds=open(os.path.join(pathsmv,'XDS.INP'),'w')
        nb_line=1
        for line in f:
            if nb_line==54:
                f_xds.write("DATA_RANGE=           {} {}\n".format(1,indend-10001))
            elif nb_line==56:
                f_xds.write("SPOT_RANGE=           {} {}\n".format(1,indend-10001))
            elif nb_line==58:
                f_xds.write("BACKGROUND_RANGE=           {} {}\n".format(1,indend-10001))
            elif nb_line==69:
                f_xds.write("STARTING_ANGLE= {}\n".format(startangle))
            elif nb_line==134:
                f_xds.write("INCLUDE_RESOLUTION_RANGE= {}   {}\n".format(lowres,highres))
            elif nb_line==156:
                f_xds.write("ORGX= {}    ORGY= {}       !Detector origin (pixels). Often close to the image center, i.e. ORGX=NX/2; ORGY=NY/2\n".format(pb[0],pb[1]))
            elif nb_line==157:
                f_xds.write("DETECTOR_DISTANCE= +{}   ! can be negative. Positive because the detector normal points away from the crystal.\n".format(distance))
            elif nb_line==159:
                f_xds.write(" OSCILLATION_RANGE= {}\n".format(osangle))
            elif nb_line==162:
                f_xds.write("ROTATION_AXIS= {} {} 0\n".format(cos(RA),cos((RA+np.pi/2))))
            else:
                f_xds.write(line)
            nb_line=nb_line+1
        
        logger.debug("XDS.inp file created. Modify .img path accordingly in your Linux machine.")
        
    def wait(self):
        msvcrt.getch()
