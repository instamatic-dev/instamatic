#!/usr/bin/env python

import sys, os
import numpy as np
import json

from TEMController import initialize

from calibration import CalibDiffShift, CalibBeamShift
from tools import *

def calibrate_diffshift_live(ctrl, gridsize=5, stepsize=2500):

    if not ctrl.mode == "diff":
        print " >> Switching to diffraction mode"
        ctrl.mode_diffraction()

    beam_center_x, beam_center_y = ctrl.beamshift.get()

    plas = []
    beams = []

    pattern = 12, 7, 2, 1, 0, 5, 10, 15, 20, 21, 22, 23, 24, 19, 14, 9, 4, 3, 8, 13, 18, 17, 16, 11, 6

    n = (gridsize - 1) / 2 # number of points = n*(n+1)

    try:
        beamshift_calib = CalibBeamShift.from_file()
    except IOError as e:
        print e
        print " >> Cannot use CalibBeamshfit for selecting spots"
        x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)

        x_grid += beam_center_x
        y_grid += beam_center_y

        xy_coords = np.stack([x_grid, y_grid]).reshape(2,-1).T
    else:
        print " >> Using CalibBeamshift to select spots"
        xres, yres = ctrl.cam.getDimensions()
            
        xstep = int(xres / gridsize)
        ystep = int(yres / gridsize)
    
        x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * xstep, np.arange(-n, n+1) * ystep)

        x_grid += xres / 2
        y_grid += yres / 2
    
        xy_coords = beamshift_calib.pixelcoord_to_beamshift(np.stack([x_grid, y_grid]).reshape(2,-1).T)

    tot = len(pattern)

    for i,j in enumerate(pattern):
        x, y = xy_coords[j]
        ctrl.beamshift.set(x=x, y=y)

        raw_input("{}/{}: Center with PLA and press enter...".format(i+1, tot))

        beam_xy = ctrl.beamshift.get()
        pla_xy = ctrl.diffshift.get()

        print "  ", pla_xy

        plas.append(pla_xy)
        beams.append(beam_xy)

    plas = np.array(plas)
    beams = np.array(beams)

    print "Return to center", beam_center_x, beam_center_y
    ctrl.beamshift.set(beam_center_x, beam_center_y)

    out = open("calibpla.json", "w")
    d = {
        "beams": beams.tolist(),
        "plas": plas.tolist(),
        "xy_coords": xy_coords.tolist(),
        "center": (beam_center_x, beam_center_y)
    }
    json.dump(d, out)
    out.close()

    c = CalibDiffShift.from_data(plas, beams, neutral_beamshift=(beam_center_x, beam_center_y))
    c.plot()

    return c


def calibrate_diffshift_from_file(fn):
    d = json.load(open(fn))

    beams = np.array(d["beams"])
    plas = np.array(d["plas"])
    xy_coords = np.array(d["xy_coords"])
    center = d["center"]

    c = CalibDiffShift.from_data(plas, beams, neutral_beamshift=center)
    c.plot()

    return c


def calibrate_diffshift(ctrl=None, fn=None, confirm=True):
    if fn:
        calib = calibrate_diffshift_from_file(fn)
    elif confirm and not raw_input("\n >> Go to diffraction mode (150x) so that the beam is\n focused and in the middle of the image (fluorescent screen works well for this)\n(type 'go' to start): """) == "go":
        return
    else:
        calib = calibrate_diffshift_live(ctrl)

    print
    print calib

    calib.to_file()


def calibrate_diffshift_entry():
    if "help" in sys.argv:
        print """
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_diffshift
        To start live calibration routine on the microscope
    
    instamatic.calibrate_diffshift calibpla.json
        To perform calibration from saved file
"""
        exit()
    if len(sys.argv[1:]) > 0:
        fn = sys.argv[1]
        calibrate_diffshift_from_file(fn)
    else:
        ctrl = initialize()
        calibrate_diffshift(ctrl=ctrl)
