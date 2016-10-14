#!/usr/bin/env python

import sys, os
import numpy as np

from scipy.stats import linregress

import matplotlib.pyplot as plt

from camera import save_image_and_header
from TEMController import initialize

import fileio
from calibration import load_img, CalibBrightness
from find_crystals import find_holes


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

        img, h = ctrl.getImage(exposure=exposure, comment="Calib image {}: brightness={}".format(i, target))
        brightness = float(h["Brightness"])
        
        holes = find_holes(img, plot=False, verbose=False, max_eccentricity=0.8)
        
        if len(holes) == 0:
            print " >> No holes found, continuing..."
            continue

        size = max([hole.equivalent_diameter for hole in holes])

        print "Brightness: {:.3f}, equivalent diameter: {:.1f}".format(brightness, size)
        values.append((brightness, size))

        if save_images:
            outfile = "calib_brightness_{:04d}".format(i)
            save_image_and_header(outfile, img=img,  header=h)
            
    values = np.array(values)
    slope, intercept, r_value, p_value, std_err = linregress(values[:,0], values[:,1])

    print
    print "r_value:", r_value
    print "p_value:", p_value

    c = CalibBrightness(slope, intercept)

    x = np.linspace(start-step, target+step)
    y = c.brightness_to_pixelsize(x)

    plt.close()
    plt.plot(x, y, "r-", label="linear regression")
    plt.scatter(*values.T)
    plt.title("Fit brightness")
    plt.legend()
    plt.show()

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
        print fn
        img, h = load_img(fn)
        brightness = float(h["Brightness"])

        holes = find_holes(img, plot=False, fname=None, verbose=False, max_eccentricity=0.8) # fname=fn.replace("edf", "png")
        
        size = max([hole.equivalent_diameter for hole in holes])

        print "Brightness: {:.3f}, equivalent diameter: {:.1f}".format(brightness, size)
        values.append((brightness, size))

    values = np.array(values)
    slope, intercept, r_value, p_value, std_err = linregress(values[:,0], values[:,1])

    print
    print "r_value:", r_value
    print "p_value:", p_value

    c = CalibBrightness(slope, intercept)

    x = np.linspace(0, 65535)
    y = c.brightness_to_pixelsize(x)

    plt.plot(x, y, "r-", label="linear regression")
    plt.scatter(*values.T)
    plt.title("Fit brightness")
    plt.legend()
    plt.show()

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

    fileio.write_calib_brightness(calib)


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
