#!/usr/bin/env python

import sys, os
import numpy as np

from TEMController import initialize
from camera import save_image_and_header

import fileio
from calibration import load_img, lsq_rotation_scaling_trans_shear_matrix, CalibDiffShift


def calibrate_diffshift_live(ctrl, gridsize=5, stepsize=2500):

    if not ctrl.mode == "diff":
        print " >> Switching to diffraction mode"
        ctrl.mode_diffraction()

    beam_center_x, beam_center_y = ctrl.beamshift.get()

    plas = []
    beams = []

    pattern = 12, 7, 2, 1, 0, 5, 10, 15, 20, 21, 22, 23, 24, 19, 14, 9, 4, 3, 8, 13, 18, 17, 16, 11, 6

    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    xy_coords = np.stack([x_grid, y_grid]).reshape(2,-1).T
    tot = len(pattern)

    for i,j in enumerate(pattern):
        dx, dy = xy_coords[j]
        ctrl.beamshift.set(x=beam_center_x+dx, y=beam_center_y+dy)

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

    out = open("calibpla.txt", "w")
    print >> out, "plas"
    print >> out, plas
    print >> out, "beams"
    print >> out, beams
    print >> out, "xy_coords"
    print >> out, xy_coords
    print >> out, "center"
    print >> out, beam_center_x, beam_center_y

    out.close()

    r, t = lsq_rotation_scaling_trans_shear_matrix(plas, beams, x0=[180, 1, 1, 0, 0, 1, 1])

    c = CalibDiffShift(rotation=r, translation=t, neutral_beamshift=(beam_center_x, beam_center_y))

    return c

def calibrate_diffshift(ctrl=None, confirm=True):
    if confirm and not raw_input("\n >> Go to diffraction mode (150x) so that the beam is\n focused and in the middle of the image (fluorescent screen works well for this)\n(type 'go' to start): """) == "go":
        return
    else:
        calib = calibrate_diffshift_live(ctrl)

    print
    print calib

    fileio.write_calib_diffshift(calib)

def calibrate_diffshift_entry():
    if "help" in sys.argv:
        print """
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_diffshift
        To start live calibration routine on the microscope
"""
        exit()
    else:
        ctrl = initialize()
        calibrate_diffshift(ctrl=ctrl)
