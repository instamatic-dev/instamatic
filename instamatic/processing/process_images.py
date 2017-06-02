import os, sys

import numpy as np
import pandas as pd
import warnings

import matplotlib.pyplot as plt

from scipy.ndimage import interpolation
from scipy import stats, ndimage

import glob

from snapkit.small_functions import get_beam_center

from instamatic.formats import *
from instamatic.cross_correlate import *

from snapkit import radialprofile


def get_initial_reference(imgs):
    shape = imgs[0].shape

    initial_reference = np.zeros(shape)

    xcent = shape[0] / 2
    ycent = shape[1] / 2

    for img in imgs:
        cy, cx = get_beam_center(img)
    
        sx, sy = [xcent - cx, ycent - cy]
        initial_reference += interpolation.shift(img, [sy, sx])
    
    return initial_reference / len(imgs)


def get_reference(imgs, initial_reference=None, repeat=3, remove_background=False):
    if initial_reference is None:
        initial_reference = get_initial_reference(imgs)
   
    shape = imgs[0].shape
    
    reference = initial_reference
    for n in range(repeat):
        current = reference
        reference = np.zeros(shape)
        
        if remove_background and (n + 1 == repeat):
            for img in imgs:
                sx, sy = cross_correlate(img, current, verbose=False)
                reference += correct_background(interpolation.shift(img, [-sx, -sy]))
        else:
            for img in imgs:
                sx, sy = cross_correlate(img, current, verbose=False)
                reference += interpolation.shift(img, [-sx, -sy])
    
    return reference / len(imgs)


def get_centers(imgs, reference=None):
    if reference is None:
        reference = get_reference(imgs)
    
    shifts = [cross_correlate(img, reference, verbose=False) for img in imgs]

    center = np.array(imgs[0].shape) / 2
    
    return np.array(shifts) + center


def get_shapiro_curve(imgs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.array([stats.shapiro(img)[0] for img in imgs])


def make_1d_powder_pattern(img, center=None, binsize=1):
    if center is None:
        smooth = ndimage.gaussian_filter(img, 20)
        center = np.argwhere(smooth == smooth.max())
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        x, y = radialprofile.azimuthalAverage(img, center=center, returnradii=True, interpnan=True, binsize=binsize)
        e = radialprofile.azimuthalAverage(img, center=center, stddev=True, interpnan=True, binsize=binsize)
    xye = np.vstack((x,y,e)).T
    return xye


def correct_background(img):
    blur_max = ndimage.gaussian_filter(img, 30)
    blur_min = ndimage.gaussian_filter(img, 5)
    new = np.maximum(np.where(blur_min > blur_max, img, 0) - blur_max, 0)
    return new


def main():
    fns = sys.argv[1:]
    if not fns:
        print "Program to pre-process diffraction patterns (in TIFF format)."
        print "    - Shapiro-Wilk test for normality to filter images without signal"
        print "    - Cross-correlation to average all images"
        print "    - Cross-correlation to determine location of the incident beam on each frame"
        print
        print "Usage: python process_patterns.py image1.tiff [image2.tiff ...]"
        print
        print "Or, using a globbing pattern:"
        print "       python process_patterns.py data/image_*.tiff"
        print
        print "Or, using a file list:"
        print "       python process_patterns.py filelist.txt"
        print
        exit()

    stream = "cli"
    if len(fns) == 1:
        if not os.path.exists(fns[0]):
            fns = glob.glob(fns[0])
            stream = "glob"
        if "filelist" in fns[0]:
            fns = [line.strip() for line in open(fns[0], "r") if not line.startswith("#")]
            stream = "list"
    
    print "Reading {} images".format(len(fns))
    imgs = [read_tiff(fn)[0] for fn in fns]

    if stream != "list":
        print "Calculating Shapiro-Wilk curve"
    s = get_shapiro_curve(imgs)
    r = np.argsort(s)
    plt.plot(s[r], "r+")
    plt.title("Shapiro S-curve")
    plt.show()
    plt.close()

    thresh = raw_input("\nThreshold? [0.25] >> ")
    thresh = float(thresh) if thresh else 0.25

    print "Threshold =", thresh

    idx = np.argwhere(s < thresh)

    fns =  [ fn  for i,fn  in enumerate(fns)  if i in idx ]
    imgs = [ img for i,img in enumerate(imgs) if i in idx ]
    
    print "{} images remaining".format(len(imgs))

    print "Generating powder image"
    initref = get_initial_reference(imgs)
    print "Aligning images"
    powder = get_reference(imgs, initref, remove_background=True)
    
    plt.imshow(powder)
    plt.title("Powder pattern ({} imgs)".format(len(imgs)))
    plt.show()

    fpowder = "powder.tiff"
    write_tiff(fpowder, powder, header="Powder pattern generated from {} images".format(len(imgs)))
    print "Writing powder image to {}".format(fpowder)

    powder1d = make_1d_powder_pattern(powder, center=np.array(powder.shape) / 2)
    fpowder1d = "powder.xye"
    np.savetxt(fpowder1d, powder1d, fmt="%12.4f")
    print "Writing powder pattern to {}".format(fpowder1d)

    print "Performing shift correction"
    centers = get_centers(imgs, powder)

    fcalib = "calibration.json"
    filenames = [os.path.split(fn)[-1] for fn in fns]
    df = pd.DataFrame(index=pd.Index(filenames), data=centers, columns=("det_ycent", "det_xcent"))

    print >> open(fcalib,"w"), df.to_json(orient="index").replace('},"', '},\n"')
    print "Writing incident beam centers to {}".format(fcalib)

    if stream != "list":
        filelist = "filelist.txt"
        print >> open(filelist, "w"), "\n".join(fns)
        print "Writing", filelist
    

if __name__ == '__main__':
    main()
