#!/usr/bin/env python

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
import sys, os
import numpy as np
import matplotlib.pyplot as plt

from instamatic.tools import *
from instamatic.processing.cross_correlate import cross_correlate
from instamatic.TEMController import initialize
from .fit import fit_affine_transformation
from .filenames import *

from instamatic.tools import printer
import pickle

import logging
logger = logging.getLogger(__name__)


refine_params = {
    "DiffShift": {"rotation": True, "translation": False, "shear": False},
    "BeamShift": {"rotation": True, "translation": False, "shear": False}
}


def optimize_diffraction_focus(ctrl, steps=(50, 15, 5)):
    """Function to optimize the diffraction focus live on the microscope
    It does so by minimizing the halfwidth of the primary beam"""

    for step in steps:
        current = ctrl.difffocus.value

        best_score = np.inf
        best_delta = 0
    
        for delta in np.arange(-5, 6)*step:
            ctrl.difffocus.set(current + delta)
    
            img, h = ctrl.getImage(header_keys=None)
    
            score = np.sum(img > img.max()/2)**2
    
            if score < best_score:
                best_score = score
                best_delta = delta

        newval = current+best_delta
        ctrl.difffocus.set(newval)
        logger.info("Best diff_focus (step=%d): %d, score: %d", step, best_score, newval)

    return newval


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

    @classmethod
    def live(cls, ctrl, outdir="."):
        while True:
            c = calibrate_directbeam(ctrl=ctrl, save_images=True, outdir=outdir)
            if input(" >> Accept? [y/n] ") == "y":
                return c

    def to_file(self, fn=CALIB_DIRECTBEAM, outdir="."):
        """Save calibration to file"""
        fout = os.path.join(outdir, fn)
        pickle.dump(self, open(fout, "w"))

    def add(self, key, dct):
        """Add calibrations to self._dct
        Must contain keys: 'r', 't'
        optional: 'data_shifts', 'data_readout'
        """
        self._dct[key] = dct

    def plot(self, key, to_file=None, outdir=""):
        data_shifts = self._dct[key]["data_shifts"]   # pixelshifts
        data_readout = self._dct[key]["data_readout"] # microscope readout

        if to_file == True:
            to_file = "calib_db_{}.png".format(key)

        shifts_ = self.any2pixelshift(shift=data_readout, key=key)

        plt.scatter(*data_shifts.T, marker=">", label="Observed pixel shifts")
        plt.scatter(*shifts_.T, marker="<", label="Calculated shift from readout")
        plt.title(key + " vs. Direct beam position (Diffraction)")
        plt.legend()
        if to_file:
            plt.savefig(os.path.join(outdir, to_file))
            plt.close()
        else:
            plt.show()


def calibrate_directbeam_live(ctrl, key="DiffShift", gridsize=None, stepsize=None, save_images=False, outdir=".", **kwargs):
    """
    Calibrate pixel->beamshift coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    key: `str`
        Name of property to calibrate
    gridsize: `int` or None
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float` or None
        Size of steps for property along x and y
    exposure: `float` or None
        exposure time
    binsize: `int` or None

    In case paramers are not defined, camera specific default parameters are 

    return:
        instance of Calibration class with conversion methods
    """

    if not ctrl.mode == "diff":
        print(" >> Switching to diffraction mode")
        ctrl.mode_diffraction()

    exposure = kwargs.get("exposure", ctrl.cam.default_exposure)
    binsize = kwargs.get("binsize", ctrl.cam.default_binsize)

    if not gridsize:
        gridsize = ctrl.cam.defaults.calib_directbeam.get(key, {}).get("gridsize", 5)    # dat syntax...
    if not stepsize:
        stepsize = ctrl.cam.defaults.calib_directbeam.get(key, {}).get("stepsize", 750)  # just to fit everything on 1 line =)

    attr = getattr(ctrl, key.lower())

    outfile = os.path.join(outdir, "calib_db_{}_0000".format(key)) if save_images else None
    img_cent, h_cent = ctrl.getImage(exposure=exposure, binsize=binsize, comment="Beam in center of image", out=outfile)
    x_cent, y_cent = readout_cent = np.array(h_cent[key])

    img_cent, scale = autoscale(img_cent)

    print("{}: x={} | y={}".format(key, *readout_cent))
            
    shifts = []
    readouts = []
    
    n = int((gridsize - 1) / 2) # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    tot = gridsize*gridsize

    for i, (dx,dy) in enumerate(np.stack([x_grid, y_grid]).reshape(2,-1).T):
        i += 1

        attr.set(x=x_cent+dx, y=y_cent+dy)

        printer("Position: {}/{}: {}".format(i, tot, attr))
        
        outfile = os.path.join(outdir, "calib_db_{}_{:04d}".format(key, i)) if save_images else None

        comment = "Calib image {}: dx={} - dy={}".format(i, dx, dy)
        img, h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment=comment, header_keys=key)
        img = imgscale(img, scale)

        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        readout = np.array(h[key])
        readouts.append(readout)
        shifts.append(shift)
    
    print("")
    # print "\nReset to center"
    attr.set(*readout_cent)

    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    readouts = np.array(readouts) - np.array((readout_cent))
    
    c = CalibDirectBeam.from_data(shifts, readouts, key, header=h_cent, **refine_params[key])
    
    # Calling c.plot with videostream crashes program
    # if not hasattr(ctrl.cam, "VideoLoop"):
    #     c.plot(key)

    return c


def calibrate_directbeam_from_file(center_fn, other_fn, key="DiffShift"):
    print()
    print("Center:", center_fn)
    
    img_cent, h_cent = load_img(center_fn)
    readout_cent = np.array(h_cent[key])

    img_cent, scale = autoscale(img_cent, maxdim=512)

    binsize = h_cent["ImageBinSize"]

    print("{}: x={} | y={}".format(key, *readout_cent))
    
    shifts = []
    readouts = []

    for i, fn in enumerate(other_fn):
        print(fn)
        img, h = load_img(fn)
        img = imgscale(img, scale)
        
        readout = np.array((h[key]))
        print()
        print("Image:", fn)
        print("{}: dx={} | dy={}".format(key, *readout))
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        readouts.append(readout)
        shifts.append(shift)
        
    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    readouts = np.array(readouts) - np.array((readout_cent))

    c = CalibDirectBeam.from_data(shifts, readouts, key, header=h_cent, **refine_params[key])
    c.plot(key)

    return c


def calibrate_directbeam(patterns=None, ctrl=None, save_images=True, outdir=".", confirm=True, auto_diff_focus=False):
    import glob
    keys = ("BeamShift", "DiffShift")
    if not patterns:
        if confirm and input("""
Calibrate direct beam position
------------------------------
 1. Go to diffraction mode and select desired camera length (CAM L)
 2. Center the beam with diffraction shift (PLA)
 3. Focus the diffraction pattern (DIFF FOCUS)
    
 >> Press <ENTER> to start\n"""):
            return
        else:
            if auto_diff_focus:
                print("Optimizing diffraction focus")
                current_difffocus = ctrl.difffocus.value
                difffocus = optimize_diffraction_focus(ctrl)
                logger.info("Optimized diffraction focus from %s to %s", current_difffocus, difffocus)
            
            cs = []
            for key in keys:
                c = calibrate_directbeam_live(ctrl, save_images=save_images, outdir=outdir, key=key)
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

    logger.debug(calib)

    calib.to_file(outdir=outdir)
    # calib.plot(to_file=True, outdir=outdir)  # FIXME: this causes a freeze

    return calib


def main_entry():
    if "help" in sys.argv:
        print("""
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_directbeam
        To start live calibration routine on the microscope
    
    instamatic.calibrate_directbeam (DiffShift:pattern.tiff) (BeamShift:pattern.tiff)
        To perform calibration from saved images
""")
        exit()
    if len(sys.argv[1:]) > 0:
        calibrate_directbeam(patterns=sys.argv[1:])
    else:
        ctrl = initialize()
        calibrate_directbeam(ctrl=ctrl)

if __name__ == '__main__':
    main_entry()
