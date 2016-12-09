#!/usr/bin/env python

import sys, os
import numpy as np
import matplotlib.pyplot as plt

from instamatic.tools import *
from instamatic.cross_correlate import cross_correlate
from instamatic.TEMController import initialize
from fit import fit_affine_transformation
from filenames import *

from instamatic.find_holes import find_holes


class CalibBeamShift(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results"""
    def __init__(self, transform, reference_shift, reference_pixel):
        super(CalibBeamShift, self).__init__()
        self.transform = transform
        self.reference_shift = reference_shift
        self.reference_pixel = reference_pixel
        self.has_data = False
   
    def __repr__(self):
        return "CalibBeamShift(transform=\n{},\n   reference_shift=\n{},\n   reference_pixel=\n{})".format(
            self.transform, self.reference_shift, self.reference_pixel)

    def beamshift_to_pixelcoord(self, beamshift):
        """Converts from beamshift x,y to pixel coordinates"""
        r_i = np.linalg.inv(self.transform)
        pixelcoord = np.dot(self.reference_shift - beamshift, r_i) + self.reference_pixel
        return pixelcoord
        
    def pixelcoord_to_beamshift(self, pixelcoord):
        """Converts from pixel coordinates to beamshift x,y"""
        r = self.transform
        beamshift = self.reference_shift - np.dot(pixelcoord - self.reference_pixel, r)
        return beamshift.astype(int)

    @classmethod
    def from_data(cls, shifts, beampos, reference_shift, reference_pixel, header=None):
        r, t = fit_affine_transformation(shifts, beampos)

        c = cls(transform=r, reference_shift=reference_shift, reference_pixel=reference_pixel)
        c.data_shifts = shifts
        c.data_beampos = beampos
        c.has_data = True
        c.header = header
        return c

    @classmethod
    def from_file(cls, fn=CALIB_BEAMSHIFT):
        """Read calibration from file"""
        import pickle
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_beamshift"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_BEAMSHIFT):
        """Save calibration to file"""
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            return

        beampos = self.data_beampos
        shifts = self.data_shifts

        r_i = np.linalg.inv(self.transform)
        beampos_ = np.dot(beampos, r_i)

        plt.scatter(*shifts.T, label="Observed pixel shifts")
        plt.scatter(*beampos_.T, label="Positions in pixel coords")
        plt.legend()
        plt.show()

    def center(self, ctrl=None):
        """Return beamshift values to center the beam in the frame"""
        beamshift = self.pixelcoord_to_beamshift((1024, 1024))
        if ctrl:
            ctrl.beamshift.set(*beamshift)
        else:
            return beamshift


def calibrate_beamshift_live(ctrl, gridsize=5, stepsize=2500, exposure=0.1, binsize=2, save_images=False):
    """
    Calibrate pixel->beamshift coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for beamshift along x and y
        Defined at a magnification of 2500, scales stepsize down for other mags.
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """

    img_cent, h_cent = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Beam in center of image")
    x_cent, y_cent = beamshift_cent = np.array(ctrl.beamshift.get())

    magnification = h_cent["Magnification"]
    stepsize = 2500.0/magnification * stepsize

    img_cent, scale = autoscale(img_cent)
    
    outfile = "calib_beamcenter" if save_images else None

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale
    
    print "Beamshift: x={} | y={}".format(*beamshift_cent)
    print "Pixel: x={} | y={}".format(*pixel_cent)
        
    shifts = []
    beampos = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    outfile = None

    i = 0
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.beamshift.set(x=x_cent+dx, y=y_cent+dy)
        print
        print "\bPosition: {}/{}".format(i+1, tot)
        print ctrl.beamshift
        
        outfile = "calib_beamshift_{:04d}".format(i) if save_images else None

        img, h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))
        img = imgscale(img, scale)

        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        beamshift = np.array(h["BeamShift"])
        beampos.append(beamshift)
        shifts.append(shift)

        i += 1
            
    print " >> Reset to center"
    ctrl.beamshift.set(*beamshift_cent)

    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    beampos = np.array(beampos) - np.array((beamshift_cent))
    
    c = CalibBeamShift.from_data(shifts, beampos, reference_shift=beamshift_cent, reference_pixel=pixel_cent, header=h_cent)
    c.plot()

    return c


def calibrate_beamshift_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->beamshift coordinates from a set of images

    center_fn: `str`
        Reference image with the beam at the center of the image
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    print
    print "Center:", center_fn
    
    img_cent, h_cent = load_img(center_fn)
    beamshift_cent = np.array(h_cent["BeamShift"])
    
    img_cent, scale = autoscale(img_cent, maxdim=512)

    binsize = h_cent["ImageBinSize"]

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale
    
    print "Beamshift: x={} | y={}".format(*beamshift_cent)
    print "Pixel: x={:.2f} | y={:.2f}".format(*pixel_cent)
    
    shifts = []
    beampos = []
    
    for fn in other_fn:
        img, h = load_img(fn)
        img = imgscale(img, scale)
        
        beamshift = np.array((h["BeamShift"]))
        print
        print "Image:", fn
        print "Beamshift: x={} | y={}".format(*beamshift)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        beampos.append(beamshift)
        shifts.append(shift)
        
    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    beampos = np.array(beampos) - beamshift_cent
    
    c = CalibBeamShift.from_data(shifts, beampos, reference_shift=beamshift_cent, reference_pixel=pixel_cent, header=h_cent)
    c.plot()

    return c


def calibrate_beamshift(center_fn=None, other_fn=None, ctrl=None, save_images=True, confirm=True):
    if not (center_fn or other_fn):
        if confirm and not raw_input("\n >> Go to 2500x mag, and move the beam by beamshift\nso that is in the middle of the image (use reasonable size)\n(type 'go' to start): """) == "go":
            return
        else:
            calib = calibrate_beamshift_live(ctrl, save_images=save_images)
    else:
        calib = calibrate_beamshift_from_image_fn(center_fn, other_fn)

    print
    print calib

    calib.to_file()


def main_entry():
    if "help" in sys.argv:
        print """
Program to calibrate beamshift of microscope

Usage: 
    instamatic.calibrate_beamshift
        To start live calibration routine on the microscope

    instamatic.calibrate_beamshift CENTER_IMAGE (CALIBRATION_IMAGE ...)
       To perform calibration using pre-collected images
"""
        exit()
    elif len(sys.argv) == 1:
        ctrl = initialize()
        calibrate_beamshift(ctrl=ctrl, save_images=True)
    else:
        center_fn = sys.argv[1]
        other_fn = sys.argv[2:]
        calibrate_beamshift(center_fn=center_fn, other_fn=other_fn)


if __name__ == '__main__':
    main_entry()
