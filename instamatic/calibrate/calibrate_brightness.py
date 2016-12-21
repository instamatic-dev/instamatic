#!/usr/bin/env python

import sys, os
import numpy as np
import matplotlib.pyplot as plt

from instamatic.tools import *
from instamatic.TEMController import initialize
from filenames import *

from instamatic.find_holes import find_holes

import pickle

class CalibBrightness(object):
    """docstring for calib_brightness"""
    def __init__(self, slope, intercept):
        self.slope = slope
        self.intercept = intercept
        self.has_data = False

    def __repr__(self):
        return "CalibBrightness(slope={}, intercept={})".format(self.slope, self.intercept)

    def brightness_to_pixelsize(self, val):
        return self.slope*val + self.intercept

    def pixelsize_to_brightness(self, val):
        return int((val - self.intercept) / self.slope)

    @classmethod
    def from_data(cls, brightness, pixeldiameter, header=None):
        slope, intercept, r_value, p_value, std_err = linregress(brightness, pixeldiameter)
        print
        print "r_value: {:.4f}".format(r_value)
        print "p_value: {:.4f}".format(p_value)

        c = cls(slope=slope, intercept=intercept)
        c.data_brightness = brightness
        c.data_pixeldiameter = pixeldiameter
        c.has_data = True
        c.header = header
        return c

    @classmethod
    def from_file(cls, fn=CALIB_BRIGHTNESS):
        import pickle
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_brightness"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_BRIGHTNESS):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            pass

        mn = self.data_brightness.min()
        mx = self.data_brightness.max()
        extend = abs(mx - mn)*0.1
        x = np.linspace(mn - extend, mx + extend)
        y = self.brightness_to_pixelsize(x)
    
        plt.plot(x, y, "r-", label="linear regression")
        plt.scatter(self.data_brightness, self.data_pixeldiameter)
        plt.title("Fit brightness")
        plt.legend()
        plt.show()


def calibrate_brightness_live(ctrl, step=1000, save_images=False, **kwargs):
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

    raise NotImplementedError("calibrate_brightness_live function needs fixing...")

    exposure = kwargs.get("exposure", ctrl.cam.default_exposure)
    binsize = kwargs.get("binsize", ctrl.cam.default_binsize)

    values = []
    start = ctrl.brightness.value

    for i in range(10):
        target = start + i*step
        ctrl.brightness.value = int(target)

        outfile = "calib_brightness_{:04d}".format(i) if save_images else None

        comment = "Calib image {}: brightness={}".format(i, target)
        img, h = ctrl.getImage(exposure=exposure, out=outfile, comment=comment, header_keys="Brightness")
        
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
    
    # Calling c.plot with videostream crashes program
    if not hasattr(ctrl.cam, "VideoLoop"):
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


def main_entry():
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
    main_entry()

