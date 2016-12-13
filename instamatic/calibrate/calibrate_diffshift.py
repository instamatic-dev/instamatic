#!/usr/bin/env python

import sys, os
import numpy as np
import matplotlib.pyplot as plt

from instamatic.tools import *
from instamatic.cross_correlate import cross_correlate
from instamatic.TEMController import initialize
from fit import fit_affine_transformation
from filenames import *

import pickle

class CalibDiffShift(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results

    NOTE: The TEM stores different values for diffshift depending on the mode used
        i.e. mag1 vs sa-diff"""
    def __init__(self, rotation, translation, neutral_beamshift=None):
        super(CalibDiffShift, self).__init__()
        self.rotation = rotation
        self.translation = translation
        if not neutral_beamshift:
            neutral_beamshift = (32576, 31149)
        self.neutral_beamshift = neutral_beamshift
        self.has_data = False

    def __repr__(self):
        return "CalibDiffShift(rotation=\n{},\n translation=\n{})".format(
            self.rotation, self.translation)

    def diffshift2beamshift(self, diffshift):
        diffshift = np.array(diffshift)
        r = self.rotation
        t = self.translation

        return (np.dot(diffshift, r) + t).astype(int)

    def beamshift2diffshift(self, beamshift):
        beamshift = np.array(beamshift)
        r_i = np.linalg.inv(self.rotation)
        t = self.translation

        return np.dot(beamshift - t, r_i).astype(int)

    def compensate_beamshift(self, ctrl):
        if not ctrl.mode == "diff":
            print " >> Switching to diffraction mode"
            ctrl.mode_diffraction()
        beamshift = ctrl.beamshift.get()
        diffshift = self.beamshift2diffshift(beamshift)
        ctrl.diffshift.set(*diffshift)

    def compensate_diffshift(self, ctrl):
        if not ctrl.mode == "diff":
            print " >> Switching to diffraction mode"
            ctrl.mode_diffraction()
        diffshift = ctrl.diffshift.get()
        beamshift = self.diffshift2beamshift(diffshift)
        ctrl.beamshift.set(*beamshift)

    def reset(self, ctrl):
        ctrl.beamshift.set(*self.neutral_beamshift)
        self.compensate_diffshift()

    @classmethod
    def from_data(cls, diffshift, beamshift, neutral_beamshift, header=None):
        r, t = fit_affine_transformation(diffshift, beamshift, translation=True, shear=True)

        c = cls(rotation=r, translation=t, neutral_beamshift=neutral_beamshift)
        c.data_diffshift = diffshift
        c.data_beamshift = beamshift
        c.has_data = True
        c.header = header
        return c

    @classmethod
    def from_file(cls, fn=CALIB_DIFFSHIFT):
        import pickle
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_diffshift"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_DIFFSHIFT):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            return
    
        diffshift = self.data_diffshift

        r_i = np.linalg.inv(self.rotation)
        beamshift_ = np.dot(self.data_beamshift - self.translation, r_i)
    
        plt.scatter(*diffshift.T, label="Observed Diffraction shift")
        plt.scatter(*beamshift_.T, label="Calculated DiffShift from BeamShift")
        plt.legend()
        plt.show()