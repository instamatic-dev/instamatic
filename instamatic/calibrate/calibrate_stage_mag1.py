#!/usr/bin/env python

import sys, os, time
import numpy as np

from instamatic.tools import *
from instamatic.processing.cross_correlate import cross_correlate
from instamatic.TEMController import initialize
from .fit import fit_affine_transformation
from .filenames import *
from .calibrate_stage_lowmag import CalibStage
from instamatic.formats import read_image

from instamatic import config

import pickle

import logging
logger = logging.getLogger(__name__)


def plot_it(arr1, arr2, params):
    import matplotlib.pyplot as plt
    angle = params["angle"].value
    sx    = params["sx"].value
    sy    = params["sy"].value
    tx    = params["tx"].value
    ty    = params["ty"].value
    k1    = params["k1"].value
    k2    = params["k2"].value
    
    sin = np.sin(angle)
    cos = np.cos(angle)
    
    r = np.array([
        [ sx*cos, -sy*k1*sin],
        [ sx*k2*sin,  sy*cos]])
    t = np.array([tx, ty])

    fit = np.dot(arr1, r) + t

    plt.scatter(*fit.T)
    plt.scatter(*arr2.T)
    plt.show()


def calibrate_mag1_live(ctrl, gridsize=5, stepsize=5000, minimize_backlash=True, save_images=False, **kwargs):
    """
    Calibrate pixel->stageposition coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    minimize_backlash: bool,
        Attempt to minimize backlash by overshooting a bit
        Follows the routine from Oostergetel (1998): https://doi.org/10.1016/S0304-3991(98)00022-9
    exposure: `float`
        Exposure time in seconds
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """

    settle_delay = 1.0 # seconds

    exposure = kwargs.get("exposure", config.camera.default_exposure)
    binsize = kwargs.get("binsize", config.camera.default_binsize)

    if minimize_backlash:
        ctrl.stageposition.eliminate_backlash_xy(step=stepsize, settle_delay=settle_delay)

    outfile = "calib_start" if save_images else None

    # Accurate reading fo the center positions is needed so that we can come back to it,
    #  because this will be our anchor point
    img_cent, h_cent = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment="Center image (start)")
    stage_cent = ctrl.stageposition.get()

    cam_dimensions = h_cent["ImageCameraDimensions"]
    bin_x, bin_y = cam_dimensions / np.array(img_cent.shape)
    assert bin_x == bin_y, "Binsizes do not match {bin_x} != {bin_y}"
    binsize = int(bin_x)

    x_cent = stage_cent.x
    y_cent = stage_cent.y

    xy_cent = np.array([x_cent, y_cent])
    
    img_cent, scale = autoscale(img_cent)

    stagepos = []
    shifts = []
    
    n = int((gridsize - 1) / 2) # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    i = 0

    x_range = np.arange(-n, n+1) * stepsize
    y_range = np.arange(-n, n+1) * stepsize

    if minimize_backlash:
        xtarget = x_cent + x_range[0]
        ytarget = y_cent + y_range[0]
        ctrl.stageposition.set(x=xtarget-stepsize, y=ytarget-stepsize)
        time.sleep(settle_delay)

        print("(minimize_backlash) Overshoot a bit in XY: ", ctrl.stageposition.xy)

    for dx in x_range:
        for dy in y_range:
            ctrl.stageposition.set(x=x_cent+dx, y=y_cent+dy)
            time.sleep(settle_delay)
            stage = ctrl.stageposition.get()

            print()
            print("Position {}/{}".format(i+1, tot))
            print(stage)
            
            outfile = "calib_{:04d}".format(i) if save_images else None

            comment = "Calib image {}: dx={} - dy={}".format(i, dx, dy)
            img, h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment=comment)
            
            img = imgscale(img, scale)

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)

            xobs = stage.x
            yobs = stage.y        

            stagepos.append((xobs, yobs))
            shifts.append(shift)
            
            i += 1

        if minimize_backlash:
            ytarget = y_cent + y_range[0]
            ctrl.stageposition.set(y=ytarget-stepsize)
            time.sleep(settle_delay)
            print("(minimize_backlash) Overshoot a bit in Y: ", ctrl.stageposition.xy)
    
    print(" >> Reset to center")
    ctrl.stageposition.set(x=x_cent, y=y_cent)
    time.sleep(settle_delay)
    # ctrl.stageposition.reset_xy()

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))

    m = gridsize**2 // 2 
    if gridsize % 2 and stagepos[m].max() > 50:
        print(" >> Warning: Large difference between image {}, and center image. These should be close for a good calibration.".format(m))
        print("    Difference:", stagepos[m])
        print()
    
    if save_images:
        ctrl.getImage(exposure=exposure, binsize=binsize, out="calib_end", comment="Center image (end)")

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent, camera_dimensions=cam_dimensions)
    c.plot()

    return c


def calibrate_mag1_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->stageposition coordinates from a set of images

    center_fn: `str`
        Reference image at the center of the grid (with the clover in the middle)
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    img_cent, h_cent = read_image(center_fn)

    # binsize = h_cent["ImageBinSize"]
    cam_dimensions = h_cent["ImageCameraDimensions"]
    bin_x, bin_y = cam_dimensions / np.array(img_cent.shape)
    assert bin_x == bin_y, "Binsizes do not match {bin_x} != {bin_y}"
    binsize = int(bin_x)
    
    img_cent, scale = autoscale(img_cent, maxdim=512)

    x_cent, y_cent, _, _, _ = h_cent["StagePosition"]
    # x_cent=40943.0
    # y_cent=-6258.4

    xy_cent = np.array([x_cent, y_cent])
    print("Center:", center_fn)
    print("Stageposition: x={:.0f} | y={:.0f}".format(*xy_cent))
    print()

    shifts = []
    stagepos = []

    # stage = ((30943.5, -16255.5),
    # (30874.701171875, -11258.2998046875),
    # (31009.701171875, -6256.89990234375),
    # (30876.0, -1256.9000244140625),
    # (31011.0, 3744.400146484375), 
    # (35943.5, -16256.900390625),
    # (35874.6015625, -11256.900390625),
    # (36011.0, -6256.89990234375),
    # (35874.6015625, -1256.9000244140625),
    # (36012.30078125, 3743.0), 
    # (40943.40234375, -16252.7001953125),
    # (40943.40234375, -11256.900390625),
    # (40943.40234375, -6258.30029296875),
    # (40943.40234375, -1256.9000244140625),
    # (40943.40234375, 3744.400146484375),
    # (45943.40234375, -16255.5),
    # (45943.40234375, -11258.2998046875),
    # (45943.40234375, -6255.5),
    # (45943.40234375, -1259.7000732421875),
    # (45943.40234375, 3745.800048828125), 
    # (50943.40234375, -16255.5),
    # (50943.40234375, -11258.2998046875),
    # (50943.40234375, -6256.89990234375),
    # (50943.40234375, -1256.9000244140625),
    # (50943.40234375, 3743.0)) 

    for i, fn in enumerate(other_fn):
        img, h = read_image(fn)


        img = imgscale(img, scale)
        
        x_xobs, yobs, _, _, _ = h_cent["StagePosition"]
        # xobs, yobs = stage[i]
        print("Image:", fn)
        print("Stageposition: x={:.0f} | y={:.0f}".format(xobs, yobs))
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        print("Shift:", shift)
        print()
        
        stagepos.append((xobs, yobs))
        shifts.append(shift)

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - xy_cent

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent, camera_dimensions=cam_dimensions)
    c.plot()

    return c


def calibrate_mag1(center_fn=None, other_fn=None, ctrl=None, confirm=True, save_images=False):
    if not (center_fn or other_fn):
        if confirm and not input("\n >> Go to 5000x mag, and move the sample stage\nso that a strong feature is clearly in the middle \nof the image (type 'go'): """) == "go":
            return
        else:
            calib = calibrate_mag1_live(ctrl, save_images=True)
    else:
        calib = calibrate_mag1_from_image_fn(center_fn, other_fn)

    print()
    print(calib)

    calib.to_file()


def main_entry():

    if "help" in sys.argv:
        print("""
Program to calibrate mag1 of microscope

Usage: 
prepare
    instamatic.calibrate_mag1
        To start live calibration routine on the microscope

    instamatic.calibrate_mag1 CENTER_IMAGE (CALIBRATION_IMAGE ...)
       To perform calibration using pre-collected images
""")
        exit()
    elif len(sys.argv) == 1:
        ctrl = initialize()
        calibrate_mag1(ctrl=ctrl, save_images=True)
    else:
        center_fn = sys.argv[1]
        other_fn = sys.argv[2:]
        calibrate_mag1(center_fn, other_fn)


if __name__ == '__main__':
    main_entry()