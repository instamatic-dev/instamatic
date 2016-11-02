#!/usr/bin/env python

import sys, os
import numpy as np

from camera import save_image_and_header
from TEMController import initialize

from calibration import CalibBrightness
from find_holes import find_holes
from tools import *


def calibrate_brightness_live(ctrl, step=1000, exposure=0.1, binsize=1, save_images=False):
    """
    Calibrate pixel->brightness coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    start: `float`
        start value for calibration (0.0 - 1.0)
    end: `float`
        end value for calibration (0.0 - 1.0)
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of CalibBrightness class with conversion methods
    """

    values = []
    start = ctrl.brightness.value

    for i in range(10):
        target = start + i*step
        ctrl.brightness.value = int(target)

        outfile = "calib_brightness_{:04d}".format(i) if save_images else None

        img, h = ctrl.getImage(exposure=exposure, out=outfile, comment="Calib image {}: brightness={}".format(i, target))
        
        img, scale = autoscale(img)

        brightness = float(h["Brightness"])
        
        holes = find_holes(img, plot=False, verbose=False, max_eccentricity=0.8)
        
        if len(holes) == 0:
            print " >> No holes found, continuing..."
            continue

        size = max([hole.equivalent_diameter for hole in holes]) * binsize / scale

        print "Brightness: {:.f}, equivalent diameter: {:.1f}".format(brightness, size)
        values.append((brightness, size))

    values = np.array(values)
    c = CalibBrightness.from_data(*values.T)
    c.plot()

    return c


def calibrate_brightness_from_image_fn(fns):
    """
    Calibrate pixel->brightness (size of beam) from a set of images

    fns: `str`
        Set of images to determine size of beam from

    return:
        instance of Calibration class with conversion methods
    """

    values = []

    for fn in fns:
        print
        print "Image:", fn
        img, h = load_img(fn)
        brightness = float(h["Brightness"])
        binsize = float(h["ImageBinSize"])

        img, scale = autoscale(img)

        holes = find_holes(img, plot=False, fname=None, verbose=False, max_eccentricity=0.8)
        
        size = max([hole.equivalent_diameter for hole in holes]) * binsize / scale

        print "Brightness: {:.0f}, equivalent diameter: {:.1f}px".format(brightness, size)
        values.append((brightness, size))

    values = np.array(values)
    c = CalibBrightness.from_data(*values.T)
    c.plot()

    return c


def calibrate_brightness(fns=None, ctrl=None, confirm=True):
    if not fns:
        if confirm and not raw_input("\n >> Go too 2500x mag (type 'go' to start): """) == "go":
            return
        else:
            calib = calibrate_brightness_live(ctrl, save_images=True)
    else:
        calib = calibrate_brightness_from_image_fn(fns)

    print
    print calib

    calib.to_file()


def calibrate_brightness_entry():
    if "help" in sys.argv:
        print """
Program to calibrate brightness of microscope

Usage: 
prepare
    instamatic.calibrate_brightness
        To start live calibration routine on the microscope

    instamatic.calibrate_brightness IMAGE (IMAGE ...)
       To perform calibration using pre-collected images
"""
        exit()
    elif len(sys.argv) == 1:
        ctrl = initialize()
        calibrate_brightness(ctrl, save_images=True)
    else:
        fns = sys.argv[1:]
        calibrate_brightness(fns)

if __name__ == '__main__':
    calibrate_brightness_entry()

