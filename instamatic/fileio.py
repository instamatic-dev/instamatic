#!/usr/bin/env python
import pickle
import os
from calibration import CalibStage
from calibration import CalibBrightness
from calibration import CalibBeamShift
from calibration import CalibDiffShift
import numpy as np


CALIB_STAGE_LOWMAG = "calib_stage_lowmag.pickle"
CALIB_BEAMSHIFT = "calib_beamshift.pickle"
CALIB_BRIGHTNESS = "calib_brightness.pickle"
CALIB_DIFFSHIFT = "calib_diffshift.pickle"
HOLE_COORDS = "hole_coords.npy"
EXPERIMENT = "experiment.pickle"


def load_calib_stage_lowmag():
    if os.path.exists(CALIB_STAGE_LOWMAG):
        d = pickle.load(open(CALIB_STAGE_LOWMAG, "r"))
        if d.has_key("transform"):
            d["rotation"] = d["transform"]
        calib = CalibStage(**d)
    else:
        raise IOError("\n >> Please run instamatic.calibrate_stage_lowmag first.")
    return calib

def load_hole_stage_positions():
    if os.path.exists(HOLE_COORDS):
        coords = np.load(HOLE_COORDS)
    else:
        raise IOError("\n >> Please run instamatic.map_holes first.")
    return coords

def load_calib_beamshift():
    if os.path.exists(CALIB_BEAMSHIFT):
        d = pickle.load(open(CALIB_BEAMSHIFT, "r"))
        calib = CalibBeamShift(**d)
    else:
        raise IOError("\n >> Please run instamatic.calibrate_beamshift first.")
    return calib

def load_experiment():
    print os.path.abspath(".")
    if os.path.exists(EXPERIMENT):
        d = pickle.load(open(EXPERIMENT, "r"))
    else:
        raise IOError("\n >> Please run instamatic.prepare_experiment first.")
    return d

def load_calib_brightness():
    print os.path.abspath(".")
    if os.path.exists(CALIB_BRIGHTNESS):
        d = pickle.load(open(CALIB_BRIGHTNESS, "r"))
        calib = CalibBrightness(**d)
    else:
        raise IOError("\n >> Please run instamatic.calib_brightness first.")
    return calib

def load_calib_diffshift():
    print os.path.abspath(".")
    if os.path.exists(CALIB_DIFFSHIFT):
        d = pickle.load(open(CALIB_DIFFSHIFT, "r"))
        calib = CalibDiffShift(**d)
    else:
        raise IOError("\n >> Please run instamatic.calib_diffshift first.")
    return calib

def write_calib_stage_lowmag(calib):
    pickle.dump({
        "rotation": calib.rotation,
        "translation": calib.translation,
        "reference_position": calib.reference_position
        }, open(CALIB_STAGE_LOWMAG,"w"))

# def write_hole_stage_positions():
#     pass

def write_calib_beamshift(calib):
    pickle.dump({
        "transform": calib.transform,
        "reference_shift": calib.reference_shift,
        "reference_pixel": calib.reference_pixel
        }, open(CALIB_BEAMSHIFT, "w"))

def write_experiment(experiment):
    pickle.dump(experiment, open(EXPERIMENT, "w"))

def write_calib_brightness(calib):
    pickle.dump({
        "slope": calib.slope,
        "intercept": calib.intercept
        }, open(CALIB_BRIGHTNESS, "w"))

def write_calib_diffshift(calib):
    pickle.dump({
        "rotation": calib.rotation,
        "translation": calib.translation,
        }, open(CALIB_DIFFSHIFT,"w"))