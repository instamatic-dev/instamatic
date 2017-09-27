# -*- coding: utf-8 -*-
"""
Created on Thu Mar  9 14:20:05 2017

@author: jong1047
"""
#from __future__ import absolute_import, division, print_function

from skimage.io import imread
from scipy import ndimage
import os
import numpy as np

def mainLoop(options):
    header = b'\x00\x02\x00\x00\x00\x02\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x02\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4B\x00\x00\xb4B\x00\x00\xb4B\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x888Fx\x06sA\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00MAP DA\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00aaaaaaaaaaaaaaaaaaaaaa,aaaaaaaaaaa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   
    onlyTiffFiles = []
    for fileOrFolder in os.listdir(options["path"]):
        if fileOrFolder[-5:]==".tiff":
            onlyTiffFiles.append(fileOrFolder)
    
    if options["MRC"] == True:
        if not os.path.exists(options["path"]+"mrc"):
            os.makedirs(options["path"]+"mrc")
            
        makeEd3d(options["path"] + "\\mrc\\" + "mrc.ed3d",
                 options,
                 onlyTiffFiles
                 )
    
    if options["fMRC"] == True:
        if not os.path.exists(options["path"]+"fmrc"):
            os.makedirs(options["path"]+"fmrc")
            
        makeEd3d(options["path"] + "\\fmrc\\" + "fmrc.ed3d",
                 options,
                 onlyTiffFiles
                 )
        
    if options["IMG"] == True:
        if not os.path.exists(options["path"]+"img"):
            os.makedirs(options["path"]+"img")
        
    speed = ((0.114,0.45),
             (0.45, 1.8),
             (1.126,4.5))
    
    realCameraLenght = calcRealCameralength(options["camerlength"])
    
    directXY = [256.0,256.0]
    
    if options["smooth"] == True:
        smoothXY = smoothDirectBeam(options,onlyTiffFiles)
    
    angnum = 0
    for tiffFile in onlyTiffFiles:
        angle = (options["startangle"] + options["direction"] * angnum *
                 speed[options["gear"]-1][options["CRS"]] * options["exptime"])
        rotSpeed = speed[options["gear"]-1][options["CRS"]] * options["exptime"] * options["direction"]
        
        if options["smooth"] == True:
            directXY = smoothXY[:,angnum]
        readTIFFAndWriteMRCAndWriteIMG(tiffFile,
                                       header,
                                       options,
                                       angle,
                                       rotSpeed,
                                       realCameraLenght,
                                       directXY
                                       )
        angnum += 1
        

def readTIFFAndWriteMRCAndWriteIMG(tiffFile,
                                   header,
                                   options,
                                   angle,
                                   rotSpeed,
                                   realCameraLenght,
                                   directXY
                                   ):
    """
    Opens one tiff file and writes the files specified in the options
    """
    if options["quiet"] == False:
        print("Reading " + tiffFile)
        
    image = imread(options["path"]+tiffFile).astype(np.int16)[::-1,:]
    
    if options["MRC"] == True:
        writeFileName = "mrc\\" + tiffFile[:-5] + ".mrc"
   
        if options["quiet"] == False:
            print("Writing " + writeFileName)
            
        with open(options["path"]+writeFileName, "wb") as f:
            f.write(header)
            f.write(image.tobytes())
    
    
    if options["fMRC"] == True:
        writeFileName = "fmrc\\" + tiffFile[:-5] + ".mrc"
        
        if options["quiet"] == False:
            print("Writing " + writeFileName)
        
        newImage = fixCross(image,options["factor"])

        with open(options["path"]+writeFileName, "wb") as f:
            for n in range(0,256):
                byte = header[n*4:n*4+4]

                if n in [0,1,7,8]:
                    f.write(b'\x04\x02\x00\x00')
                else:
                    f.write(byte)
            f.write(newImage.astype(np.int16).tobytes())
    
    
    if options["IMG"] == True:
        
        writeFileName = "img\\" + tiffFile[:-5] + ".img"

        if options["quiet"] == False:
            print("Writing " + writeFileName)
        
        if options["smooth"] == False:
            above95 = np.where(image[::-1,:].T>np.max(image)*0.95)
            directXY = np.average(above95[0]),np.average(above95[1])
    
        if options["fixDist"] == True:
            image = fixDistortion(options,image,directXY)

        headerList = makeIMGHeader(options["wavelength"],
                                   directXY[0],
                                   directXY[1],
                                   rotSpeed,
                                   angle,
                                   angle,
                                   realCameraLenght
                                   )
        
        
        
        with open(options["path"]+writeFileName, "w") as f:
            for n in range(0,len(headerList)):
                f.write(headerList[n] + "\n")
            f.write("}")
                
        with open(options["path"]+writeFileName, "r+b") as f:
            for n in range(0,512):
                chunk = f.read(1)
                if chunk == b'':
                    f.write(b'\x00')
            f.write(image[::-1,:].tobytes())
    
    return image
    
    
    
def makeIMGHeader(
                  wavelength,
                  beamCenterX,
                  beamCenterY,
                  oscRange,
                  oscStart,
                  phi,
                  realCameraLenght
                  ):

    headerList = [
                  "{",
                  "HEADER_BYTES=  512;",
                  "DIM=2;",
                  "BYTE_ORDER=little_endian;",
                  "TYPE=unsigned_short;",
                  "SIZE1=512;",
                  "SIZE2=512;",
                  "PIXEL_SIZE=0.050000;",
                  "BIN=1x1;",
                  "BIN_TYPE=HW;",
                  "ADC=fast;",
                  "CREV=1;",
                  "BEAMLINE=ALS831;",
                  "DETECTOR_SN=926;",
                  "DATE=Tue Jun 26 09:43:09 2007;",
                  "TIME=0.096288;",
                  "DISTANCE="      + str("%.2f" % realCameraLenght)  + ";",
                  "TWOTHETA=0.00;",
                  "PHI="           + str("%.2f" % phi)               + ";",
                  "OSC_START="     + str("%.2f" % oscStart)          + ";",
                  "OSC_RANGE="     + str("%.2f" % oscRange)          + ";",
                  "WAVELENGTH="    + str("%.2f" % wavelength)        + ";",
                  "BEAM_CENTER_X=" + str("%.2f" % beamCenterX)       + ";",
                  "BEAM_CENTER_Y=" + str("%.2f" % beamCenterY)       + ";",
                  "DENZO_X_BEAM="  + str("%.2f" % (beamCenterX*0.05))+ ";",
                  "DENZO_Y_BEAM="  + str("%.2f" % (beamCenterY*0.05))+ ";",
                  ]
    
    return headerList





def makeEd3d(completePath,
             options,
             onlyTiffFiles
             ):
    
    with open(completePath, 'w') as f:
        
        speed =     ((0.114,0.45),
                     (0.45,1.8),
                     (1.126,4.5))
        
        lengthopix = {15:0.00838,
                      20:0.00623,
                      25:0.00499,
                      30:0.00412,
                      40:0.00296,
                      50:0.00238,
                      60:0.00198,
                      80:0.00148}

        try:
            pixelsize = lengthopix[options["camerlength"]]
            
        except:
            print("Invalid camera length, 15 is used instead")
            pixelsize = lengthopix[15]
        
        topdata = [options["wavelength"],
                   options["rotationaxis"],
                   pixelsize,
                   options["strechamp"],
                   options["strechazimuth"]]

        topname = ['WAVELENGTH',
                   'ROTATIONAXIS',
                   'CCDPIXELSIZE',
                   'STRETCHINGAMP',
                   'STRETCHINGAZIMUTH']

        for name, data in zip(topname, topdata):
            f.write(name + '\t' + str(data) + '\n')
        f.write('\nFILELIST\n')
        #make filelists
        angnum = 0
        
        for tiffFile in onlyTiffFiles:
                f.write("FILE ")
                f.write(tiffFile[:-5] + ".mrc")
                angle = options["startangle"] + options["direction"] * angnum * speed[options["gear"]-1][options["CRS"]] * options["exptime"]
                angle = " " + str("%.3f" % angle)
                f.write(angle+'\t0\t'+angle+'\n')
                angnum += 1
        
        f.write('ENDFILELIST')	            
        
def affine_transform_ellipse_to_circle(azimuth, stretch, inverse=False):
    """Usage: 
    r = circle_to_ellipse_affine_transform(azimuth, stretch):
    np.dot(x, r) # x.shape == (n, 2)
    
    http://math.stackexchange.com/q/619037
    """
    sin = np.sin(azimuth)
    cos = np.cos(azimuth)
    sx    = 1 - stretch
    sy    = 1 + stretch
    
    # apply in this order
    rot1 = np.array((cos, -sin,  sin, cos)).reshape(2,2)
    scale = np.array((sx, 0, 0, sy)).reshape(2,2)
    rot2 = np.array((cos,  sin, -sin, cos)).reshape(2,2)
    
    composite = rot1.dot(scale).dot(rot2)
    
    if inverse:
        return np.linalg.inv(composite)
    else:
        return composite

def affine_transform_circle_to_ellipse(azimuth, stretch):
    """Usage: 
    r = circle_to_ellipse_affine_transform(azimuth, stretch):
    np.dot(x, r) # x.shape == (n, 2)
    """
    return affine_transform_ellipse_to_circle(azimuth, stretch, inverse=True)

def apply_transform_to_image(img, transform, center=None):
    """Applies transformation matrix to image and recenters it
    http://docs.sunpy.org/en/stable/_modules/sunpy/image/transform.html
    http://stackoverflow.com/q/20161175
    """
    
    if center is None:
        center = (np.array(img.shape)[::-1]-1)/2.0
    
    displacement = np.dot(transform, center)
    shift = center - displacement
    
    img_tf = ndimage.interpolation.affine_transform(img, transform, offset=shift, mode="constant", order=3, cval=0.0)
    return img_tf

def fixCross(image, factor):
    """
    Adds missing pixels in cross
    """
    newImage = np.zeros([516,516],dtype=np.int16)
    newImage[0:256,0:256]   = image[0:256,0:256]
    newImage[256+4:,256+4:] = image[256:,256:]
    newImage[0:256,256+4:]  = image[0:256,256:]
    newImage[256+4:,0:256]  = image[256:,0:256]
        
    for n in range(0,2):
        newImage[255:258,:] = newImage[255,:]/factor
        newImage[258:261,:] = newImage[260,:]/factor
        newImage = newImage.T
    return newImage

def fixFixCross(newImage):
    """
    Removes added pixels in cross
    """
    fixFixImage = np.zeros([512,512],dtype=np.int16)
    fixFixImage[0:256,0:256] = newImage[0:256,0:256]
    fixFixImage[256:,256:]   = newImage[256+4:,256+4:]
    fixFixImage[0:256,256:]  = newImage[0:256,256+4:]
    fixFixImage[256:,0:256]  = newImage[256+4:,0:256]
    
    return fixFixImage

def fixDistortion(options,image,directXY):
    
    radianAzimuth = np.radians(options["strechazimuth"])
    stretch = options["strechamp"] * 0.01
                
    newImage = fixCross(image,options["factor"])
                
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
         
    c2e = affine_transform_circle_to_ellipse(radianAzimuth, stretch)
    newImage = apply_transform_to_image(newImage[::-1,:], c2e, directXY)[::-1,:]
    fixFixImage = fixFixCross(newImage)
    
    return fixFixImage


def smoothDirectBeam(options,onlyTiffFiles):
    xys = []
    for tiffFile in onlyTiffFiles:
        if options["quiet"] == False:
            print("Finding direct beam in: "+tiffFile)
            
        image = imread(options["path"]+tiffFile).astype(np.int16)[::-1,:]
        above95 = np.where(image[::-1,:].T>np.max(image)*0.95)
        directXY = np.average(above95[0]),np.average(above95[1])
        xys.append(directXY)
        
    if options["quiet"] == False:
        print("Smooting...")
        
    x = np.array(xys)[:,0]
    y = np.array(xys)[:,1]
    
    xs = np.linspace(0,x.shape[0]-1,x.shape[0])
    
    xPoly = np.polyfit(xs,x,2)
    yPoly = np.polyfit(xs,y,2)
    
    smoothX = xPoly[0]*xs**2+xPoly[1]*xs+xPoly[2]
    smoothY = yPoly[0]*xs**2+yPoly[1]*xs+yPoly[2]
    
    smoothXY = np.array([smoothX,smoothY])
    return smoothXY

def calcRealCameralength(camerlength):
    lengthToLength = {15: 237.71,
                      20: 319.75,
                      25: 399.20,
                      30: 483.50,
                      40: 672.98,
                      50: 836.99,
                      60: 1006.08,
                      80: 1345.97}
    realCameraLenght = lengthToLength[camerlength]
    return realCameraLenght


