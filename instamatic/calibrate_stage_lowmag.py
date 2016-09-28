#!/usr/bin/env python

import sys, os
import numpy as np

from cross_correlate import cross_correlate

from camera import save_image_and_header
from TEMController import initialize

from calibration import CalibStage, load_img, lsq_rotation_scaling_matrix, lsq_rotation_scaling_trans_matrix
import fileio

def calibrate_stage_lowmag_live(ctrl, gridsize=5, stepsize=50000, exposure=0.1, binsize=1, save_images=False):
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

    img_cent, header_cent = ctrl.getImage(exposure=exposure, comment="Center image")
    x_cent, y_cent, _, _, _ = header_cent["StagePosition"]
    
    if save_images:
        outfile = "calib_center"
        save_image_and_header(outfile, img=img_cent, header=header_cent)

    stagepos = []
    shifts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)

    i = 0
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.stageposition.set(x=x_cent+dx, y=y_cent+dy)
           
        print
        print ctrl.stageposition
        
        img, h = ctrl.getImage(exposure=exposure, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))
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
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))
    
    r = lsq_rotation_scaling_matrix(shifts, stagepos)
    c = CalibStage(rotation=r, reference_position=np.array([x_cent, y_cent]))

    # r, t = lsq_rotation_scaling_trans_matrix(shifts, stagepos)
    # c = CalibStage(rotation=r, translation=t, reference_position=np.array([x_cent, y_cent]))

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
    x_cent, y_cent, _, _, _ = header_cent["StagePosition"]
    print
    print "Center:", center_fn
    print "Stageposition: x={:.2f} | y={:.2f}".format(x_cent, y_cent)

    shifts = []
    stagepos = []
    
    # gridsize = 5
    # stepsize = 50000
    # n = (gridsize - 1) / 2 # number of points = n*(n+1)
    # x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    # stagepos_p = np.array(zip(x_grid.flatten(), y_grid.flatten()))

    for fn in other_fn:
        img, h = load_img(fn)
        
        xobs, yobs, _, _, _ = h["StagePosition"]
        print
        print "Image:", fn
        print "Stageposition: x={:.2f} | y={:.2f}".format(xobs, yobs)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        stagepos.append((xobs, yobs))
        shifts.append(shift)
        
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))

    r = lsq_rotation_scaling_matrix(shifts, stagepos)
    c = CalibStage(rotation=r, reference_position=np.array([x_cent, y_cent]))

    # r, t = lsq_rotation_scaling_trans_matrix(shifts, stagepos)
    # c = CalibStage(rotation=r, translation=t, reference_position=np.array([x_cent, y_cent]))

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

    fileio.write_calib_stage_lowmag(calib)


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