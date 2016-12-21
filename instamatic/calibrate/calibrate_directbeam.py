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

import pickle

refine_params = {
    "DiffShift": {"rotation": True, "translation": False, "shear": False},
    "BeamShift": {"rotation": True, "translation": False, "shear": False}
}

calib_params = {
    "DiffShift": {"gridsize":5, "stepsize":300, "magnification": 5000, "brightness": 44335, "difffocus":20561},
    "BeamShift": {"gridsize":5, "stepsize":75, "magnification": 5000, "brightness": 44335, "difffocus":20561},
    "ImageShift1": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44335, "difffocus":20561},
    "ImageShift2": {"gridsize":5, "stepsize":2500, "magnification": 5000, "brightness": 44335, "difffocus":20561}
}
#Beamshift @  5000x: 700
#Beamshift @ 10000x: 350


class CalibDirectBeam(object):
    """docstring for CalibDirectBeam"""
    def __init__(self, dct={}):
        super(CalibDirectBeam, self).__init__()
        self._dct = dct
    
    def __repr__(self):
        ret = "CalibDirectBeam("
        for key in self._dct.keys():
            r = self._dct[key]["r"]
            t = self._dct[key]["t"]

            ret += "\n {}(rotation=\n{},\n  translation={})".format(key, r, t)
        ret += ")"
        return ret

    @classmethod
    def combine(cls, lst):
        return cls({k: v for c in lst for k, v in c._dct.items()})

    def any2pixelshift(self, shift, key):
        r = self._dct[key]["r"]
        t = self._dct[key]["t"]

        shift = np.array(shift)
        r_i = np.linalg.inv(r)
        pixelshift = np.dot(shift - t, r_i)
        return pixelshift

    def pixelshift2any(self, pixelshift, key):
        r = self._dct[key]["r"]
        t = self._dct[key]["t"]

        pixelshift = np.array(pixelshift)
        shift = np.dot(pixelshift, r) + t
        return shift

    def beamshift2pixelshift(self, beamshift):
        return self.any2pixelshift(shift=beamshift, key="BeamShift")

    def diffshift2pixelshift(self, diffshift):
        return self.any2pixelshift(shift=diffshift, key="DiffShift")

    def imageshift2pixelshift(self, imageshift):
        return self.any2pixelshift(shift=imageshift, key="ImageShift")

    def imagetilt2pixelshift(self, imagetilt):
        return self.any2pixelshift(shift=imagetilt, key="ImageTilt")

    def pixelshift2beamshift(self, pixelshift):
        return self.pixelshift2any(pixelshift=pixelshift, key="BeamShift")

    def pixelshift2diffshift(self, pixelshift):
        return self.pixelshift2any(pixelshift=pixelshift, key="DiffShift")

    def pixelshift2imageshift(self, pixelshift):
        return self.pixelshift2any(pixelshift=pixelshift, key="ImageShift")

    def pixelshift2imagetilt(self, pixelshift):
        return self.pixelshift2any(pixelshift=pixelshift, key="ImageTilt")

    @classmethod
    def from_data(cls, shifts, readout, key, header=None, **dct):
        r, t = fit_affine_transformation(shifts, readout, **dct)

        d = {
            "header": header,
            "data_shifts": shifts,
            "data_readout": readout,
            "r": r,
            "t": t
        }

        return cls({key:d})

    @classmethod
    def from_file(cls, fn=CALIB_DIRECTBEAM):
        import pickle
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_directbeam"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_DIRECTBEAM):
        pickle.dump(self, open(fn, "w"))

    def add(self, key, dct):
        """Add calibrations to self._dct
        Must contain keys: 'r', 't'
        optional: 'data_shifts', 'data_readout'
        """
        self._dct[key] = dct

    def plot(self, key):
        data_shifts = self._dct[key]["data_shifts"]   # pixelshifts
        data_readout = self._dct[key]["data_readout"] # microscope readout

        shifts_ = self.any2pixelshift(shift=data_readout, key=key)

        plt.scatter(*data_shifts.T, label="Observed pixelshifts shift")
        plt.scatter(*shifts_.T, label="Calculated shift from readout from BeamShift")
        plt.title(key + " vs. Direct beam position")
        plt.legend()
        plt.show()


def calibrate_directbeam_live(ctrl, key="DiffShift", gridsize=5, stepsize=2500, exposure=0.1, binsize=2, save_images=False, **kwargs):
    if not ctrl.mode == "diff":
        print " >> Switching to diffraction mode"
        ctrl.mode_diffraction()

    magnification   = kwargs.get("magnification")
    brightness      = kwargs.get("brightness")
    difffocus       = kwargs.get("difffocus")

    # ctrl.magnification.value = magnification
    # ctrl.brightness.value = brightness
    # ctrl.difffocus.value = difffocus
    
    attr = getattr(ctrl, key.lower())

    outfile = "calib_{}_0000".format(key) if save_images else None
    img_cent, h_cent = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Beam in center of image", out=outfile)
    x_cent, y_cent = readout_cent = np.array(h_cent[key])

    img_cent, scale = autoscale(img_cent)

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
   
    print "{}: x={} | y={}".format(key, *readout_cent)
            
    shifts = []
    readouts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    outfile = None

    for i, (dx,dy) in enumerate(np.stack([x_grid, y_grid]).reshape(2,-1).T):
        i += 1

        attr.set(x=x_cent+dx, y=y_cent+dy)
        print
        print "\bPosition: {}/{}".format(i, tot)
        print attr
        
        outfile = "calib_{}_{:04d}".format(key, i) if save_images else None

        comment = "Calib image {}: dx={} - dy={}".format(i, dx, dy)
        img, h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment=comment, header_keys=key)
        img = imgscale(img, scale)

        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        readout = np.array(h[key])
        readouts.append(readout)
        shifts.append(shift)
            
    print " >> Reset to center"
    attr.set(*readout_cent)

    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    readouts = np.array(readouts) - np.array((readout_cent))
    
    c = CalibDirectBeam.from_data(shifts, readouts, key, header=h_cent, **refine_params[key])
    
    # Calling c.plot with videostream crashes program
    if not hasattr(ctrl.cam, "VideoLoop"):
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
    
    print "{}: x={} | y={}".format(key, *readout_cent)
    
    shifts = []
    readouts = []

    for i,fn in enumerate(other_fn):
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

    c = CalibDirectBeam.from_data(shifts, readouts, key, header=h_cent, **refine_params[key])
    c.plot(key)

    return c


def calibrate_directbeam(patterns=None, ctrl=None, save_images=True, confirm=True):
    import glob
    keys = ("BeamShift", "DiffShift")
    if not patterns:
        if confirm and not raw_input("\n >> Go to diffraction mode (150x) so that the beam is\n focused and in the middle of the image \n(type 'go' to start): """) == "go":
            return
        else:
            cs = []
            for key in keys:
                c = calibrate_directbeam_live(ctrl, save_images=save_images, key=key, **calib_params[key])
                cs.append(c)
            calib = CalibDirectBeam.combine(cs)
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


def main_entry():
    if "help" in sys.argv:
        print """
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_directbeam
        To start live calibration routine on the microscope
    
    instamatic.calibrate_directbeam (DiffShift:pattern.tiff) (BeamShift:pattern.tiff)
        To perform calibration from saved images
"""
        exit()
    if len(sys.argv[1:]) > 0:
        calibrate_directbeam(patterns=sys.argv[1:])
    else:
        ctrl = initialize()
        calibrate_directbeam(ctrl=ctrl)

if __name__ == '__main__':
    main_entry()
