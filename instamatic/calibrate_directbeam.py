#!/usr/bin/env python

import sys, os
import numpy as np
import json

from cross_correlate import cross_correlate

from TEMController import initialize
from camera import save_image_and_header

from calibration import CalibDirectBeam, fit_affine_transformation
import matplotlib.pyplot as plt
from find_holes import find_holes
from tools import *

refine_params = {
    "DiffShift": {"rotation": True, "translation": False, "shear": False},
    "BeamShift": {"rotation": True, "translation": False, "shear": False}
}

calib_params = {
    "DiffShift": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44000, "difffocus":32000},
    "BeamShift": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44000, "difffocus":32000},
    "ImageShift1": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44000, "difffocus":32000},
    "ImageShift2": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44000, "difffocus":32000}
}


def calibrate_directbeam_live(ctrl, key="DiffShift", gridsize=5, stepsize=2500, exposure=0.1, binsize=2, save_images=False, **kwargs):
    if not ctrl.mode == "diff":
        print " >> Switching to diffraction mode"
        ctrl.mode_diffraction()

    magnification   = kwargs.get("magnification")
    brightness      = kwargs.get("brightness")
    difffocus       = kwargs.get("difffocus")

    ctrl.magnification.value = magnification
    ctrl.brightness.value = brightness
    ctrl.difffocus.value = difffocus
    
    attr = getattr(ctrl, key.lower())

    img_cent, h = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Beam in center of image")
    x_cent, y_cent = readout_cent = np.array(attr.get())

    img_cent, scale = autoscale(img_cent)
    
    outfile = "calib_{}_0000".format(key) if save_images else None

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale

    print "{}: x={} | y={}".format(key, *readout_cent)
    print "Pixel: x={} | y={}".format(*pixel_cent)
        
    shifts = []
    readouts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    outfile = None

    i = 1
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        attr.set(x=x_cent+dx, y=y_cent+dy)
        print
        print "\bPosition: {}/{}".format(i+1, tot)
        print attr
        
        outfile = "calib_diffshift_{:04d}".format(i) if save_images else None

        img, h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))
        img = imgscale(img, scale)

        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        readout = np.array(h[key])
        readouts.append(readout)
        shifts.append(shift)

        i += 1
            
    print " >> Reset to center"
    attr.set(*keyshift_cent)

    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    readouts = np.array(readouts) - np.array((readout_cent))
    
    c = CalibDirectBeam.from_data(shifts, readouts, key, **refine_params[key])
    c.plot(key)

    return c


def calibrate_directbeam_from_file(center_fn, other_fn, key="DiffShift"):
    print
    print "Center:", center_fn
    
    img_cent, h_cent = load_img(center_fn)
    readout_cent = np.array(h_cent[key])

    img_cent, scale = autoscale(img_cent, maxdim=512)

    binsize = h_cent["ImageBinSize"]

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale
    
    print "{}: x={} | y={}".format(key, *readout_cent)
    print "Pixel: x={:.2f} | y={:.2f}".format(*pixel_cent)

    shifts = []
    readouts = []

    for fn in other_fn:
        print fn
        img, h = load_img(fn)
        img = imgscale(img, scale)
        
        readout = np.array((h[key]))
        print
        print "Image:", fn
        print "{}: dx={} | dy={}".format(key, *readout)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        readouts.append(readout)
        shifts.append(shift)
        
    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    readouts = np.array(readouts) - np.array((readout_cent))

    c = CalibDirectBeam.from_data(shifts, readouts, key, **refine_params[key])
    c.plot(key)

    return c


def calibrate_directbeam(patterns=None, ctrl=None, save_images=True, confirm=True):
    import glob
    keys = ("DiffShift", "BeamShift")
    if not patterns:
        if confirm and not raw_input("\n >> Go to diffraction mode (150x) so that the beam is\n focused and in the middle of the image (fluorescent screen works well for this)\n(type 'go' to start): """) == "go":
            return
        else:
            for key in keys:
                r,t = calibrate_directbeam_live(ctrl, save_images=save_images, key=key, **calib_params[key])
    else:
        cs = []
        for pattern in patterns:
            key, pattern = pattern.split(":")
            assert key in keys, "Unknown key: {}".format(key)
            fns = glob.glob(pattern)
            center_fn = fns[0]
            other_fn = fns[1:]
            c = calibrate_directbeam_from_file(center_fn, other_fn, key=key)
            cs.append(c)

        calib = CalibDirectBeam.combine(cs)

    print
    print calib

    calib.to_file()


def calibrate_directbeam_entry():
    if "help" in sys.argv:
        print """
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_directbeam
        To start live calibration routine on the microscope
    
    instamatic.calibrate_directbeam calibpla.json
        To perform calibration from saved file
"""
        exit()
    if len(sys.argv[1:]) > 0:
        calibrate_directbeam(patterns=sys.argv[1:])
    else:
        ctrl = initialize()
        calibrate_directbeam(ctrl=ctrl)

if __name__ == '__main__':
    calibrate_directbeam_entry()
