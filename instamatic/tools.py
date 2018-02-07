from __future__ import division
from builtins import range
from scipy import ndimage
from instamatic.formats import read_tiff, write_tiff
import sys, os
import numpy as np
import glob
import time
from skimage import exposure


def autoscale(img, maxdim=512):
    if maxdim:
        scale = float(maxdim) / max(img.shape)

    return ndimage.zoom(img, scale, order=1), scale


def imgscale(img, scale):
    if scale == 1:
        return img
    return ndimage.zoom(img, scale, order=1)


def denoise(img, sigma=3, method="median"):
    """Denoises the image using a gaussian or median filter.
    median filter is better at preserving edges"""
    if method == "gaussian":
        return ndimage.gaussian_filter(img, sigma)
    else:
        return ndimage.median_filter(img, sigma)


def enhance_contrast(img):
    """Enhance contrast by histogram equalization"""
    return exposure.equalize_hist(img)


def find_beam_center(img, sigma=30):
    "Find position of the central beam using gaussian filter"
    blurred = ndimage.gaussian_filter(img, sigma)
    center = np.unravel_index(blurred.argmax(), blurred.shape)
    return np.array(center)


def get_files(file_pat):
    """Grab files from globbing pattern or stream file"""
    from instamatic.formats import read_ycsv
    if os.path.exists(file_pat):
        root, ext = os.path.splitext(file_pat)
        if ext.lower() == ".ycsv":
            df, d = read_ycsv(file_pat)
            fns = df.index.tolist()
        else:
            f = open(file_pat, "r")
            fns = [line.split("#")[0].strip() for line in f if not line.startswith("#")]
    else:
        fns = glob.glob(file_pat)

    if len(fns) == 0:
        raise IOError("No files matching '{}' were found.".format(file_pat))

    return fns


def printer(data):
    """Print things to stdout on one line dynamically"""
    sys.stdout.write("\r\x1b[K"+data.__str__())
    sys.stdout.flush()


class ProgressBar(object):
    """docstring for ProgressBar"""
    def __init__(self):
        
        self.reverse = False
        self.a = ' '
        self.b = '='
        self.width = 10
        self.delay = 0.2

    def loop(self):
        for i in range(self.width):
            if self.reverse:
                i = self.width-i
            time.sleep(self.delay)
            printer('['+self.b*(i)+self.a*(self.width-i)+']')
        self.reverse = not self.reverse
        for i in range(self.width):
            if self.reverse:
                i = self.width-i
            time.sleep(self.delay)
            printer('['+self.a*(self.width-i)+self.b*i+']')
        self.a,self.b = self.b,self.a
        
    def clear(self):
        printer('')


