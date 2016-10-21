#!/usr/bin/env python

import logging
logging.basicConfig(
    filename="instamatic.log", 
    level=logging.DEBUG, 
    format='%(asctime)s | %(levelname)8s | %(message)s')

import sys, os
import numpy as np
from scipy import ndimage

from tools import *

from cross_correlate import cross_correlate

from camera import save_image_and_header
from TEMController import initialize

from calibration import CalibStage


def calibrate_stage_lowmag_live(ctrl, gridsize=5, stepsize=50000, exposure=0.2, binsize=1, save_images=False):
    """
    Calibrate pixel->stageposition coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """

    # Ensure that backlash is eliminated
    ctrl.stageposition.reset_xy()

    # Accurate reading fo the center positions is needed so that we can come back to it,
    #  because this will be our anchor point
    img_cent, header_cent = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Center image (start)")
    x_cent, y_cent, _, _, _ = header_cent["StagePosition"]
    xy_cent = np.array([x_cent, y_cent])
    
    img_cent, scale = autoscale(img_cent)

    if save_images:
        outfile = "calib_start"
        save_image_and_header(outfile, img=img_cent, header=header_cent)

    stagepos = []
    shifts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    i = 0
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.stageposition.set(x=x_cent+dx, y=y_cent+dy)

        print
        print "Position {}/{}".format(i+1, tot)
        print ctrl.stageposition
        
        img, h = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))

        img = imgscale(img, scale)

        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        xobs, yobs, _, _, _ = h["StagePosition"]
        stagepos.append((xobs, yobs))
        shifts.append(shift)

        if save_images:
            outfile = "calib_{:04d}".format(i)
            save_image_and_header(outfile, img=img, header=h)
        
        i += 1
    
    print " >> Reset to center"
    ctrl.stageposition.set(x=x_cent, y=y_cent)
    ctrl.stageposition.reset_xy()

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))

    if stagepos[12].max() > 50:
        print " >> Warning: Large difference between image 12, and center image. These should be close for a good calibration."
        print "    Difference:", stagepos[12]
        print
    
    if save_images:
        img, header = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Center image (end)")
        outfile = "calib_end"
        save_image_and_header(outfile, img=img, header=header)

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent)
    c.plot()

    return c


def calibrate_stage_lowmag_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->stageposition coordinates from a set of images

    center_fn: `str`
        Reference image at the center of the grid (with the clover in the middle)
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    img_cent, header_cent = load_img(center_fn)
    
    img_cent, scale = autoscale(img_cent)

    x_cent, y_cent, _, _, _ = header_cent["StagePosition"]
    xy_cent = np.array([x_cent, y_cent])
    print "Center:", center_fn
    print "Stageposition: x={:.0f} | y={:.0f}".format(*xy_cent)
    print

    binsize = header_cent["ImageBinSize"]

    shifts = []
    stagepos = []
    
    # gridsize = 5
    # stepsize = 50000
    # n = (gridsize - 1) / 2 # number of points = n*(n+1)
    # x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    # stagepos_p = np.array(zip(x_grid.flatten(), y_grid.flatten()))

    for fn in other_fn:
        img, h = load_img(fn)

        img = imgscale(img, scale)
        
        xobs, yobs, _, _, _ = h["StagePosition"]
        print "Image:", fn
        print "Stageposition: x={:.0f} | y={:.0f}".format(xobs, yobs)
        print
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        stagepos.append((xobs, yobs))
        shifts.append(shift)

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - xy_cent

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent)
    c.plot()

    return c


def calibrate_stage_lowmag(center_fn=None, other_fn=None, ctrl=None, confirm=True, save_images=False):
    if not (center_fn or other_fn):
        if confirm and not raw_input("\n >> Go too 100x mag, and move the sample stage\nso that the grid center (clover) is in the\nmiddle of the image (type 'go'): """) == "go":
            return
        else:
            calib = calibrate_stage_lowmag_live(ctrl, save_images=True)
    else:
        calib = calibrate_stage_lowmag_from_image_fn(center_fn, other_fn)

    print
    print calib

    calib.to_file()


def calibrate_stage_lowmag_entry():

    if "help" in sys.argv:
        print """
Program to calibrate lowmag (100x) of microscope

Usage: 
prepare
    instamatic.calibrate100x
        To start live calibration routine on the microscope

    instamatic.calibrate100x CENTER_IMAGE (CALIBRATION_IMAGE ...)
       To perform calibration using pre-collected images
"""
        exit()
    elif len(sys.argv) == 1:
        ctrl = initialize()
        calibrate_stage_lowmag(ctrl=ctrl, save_images=True)
    else:
        center_fn = sys.argv[1]
        other_fn = sys.argv[2:]
        calibrate_stage_lowmag(center_fn, other_fn)


if __name__ == '__main__':
    calibrate_stage_lowmag_entry()