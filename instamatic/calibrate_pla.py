#!/usr/bin/env python

import sys, os
import numpy as np

from cross_correlate import cross_correlate

from camera import save_image_and_header
from TEMController import initialize

import fileio
from calibration import load_img, lsq_rotation_scaling_matrix, CalibBeamShift


def calibrate_pla_live(ctrl, gridsize=5, stepsize=2500):

    beam_center_x, beam_center_y = ctrl.beamshift.get()

    plas = []
    beams = []

    pattern = 7, 2, 1, 0, 5, 10, 15, 20, 21, 22, 23, 24, 19, 14, 9, 4, 3, 8, 13, 18, 17, 16, 11, 6, 12

    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    xy_coords = np.stack([x_grid, y_grid]).reshape(2,-1).T

    for i,j in enumerate(pattern):
        dx, dy = pattern[i]
        ctrl.beamshift.set(x=beam_center_x+dx, y=beam_center_y+dy)

        raw_input("{}. Center with PLA and press enter...".format(i))

        beam_xy = ctrl.beamshift.get()
        pla_xy = ctrl.diffshift.get()

        print "  ", pla_xy

        plas.append(pla_xy)
        beams.append(beam_xy)

    print "Return to center", beam_center_x, beam_center_y
    ctrl.beamshift.set(beam_center_x, beam_center_y)

    r, t = lsq_rotation_scaling_trans_shear_matrix(plas, beams, x0=[180, 1, 1, 0, 0, 1, 1])

    #c = CalibBeamShift(transform=r, reference_shift=beamshift_cent, reference_pixel=pixel_cent)

    return r, t

def calibrate_pla(ctrl=None):
    calibrate_pla_live(ctr)

    if confirm and not raw_input("\n >> Go to diffraction mode (150x) so that the beam is\n focused and in the middle of the image (fluorescent screen works well for this)\n(type 'go' to start): """) == "go":
        return
    else:
        calib = calibrate_pla_live(ctrl)

    print
    print calib

    fileio.write_calib_pla(calib)

def calibrate_stage_lowmag_entry():
     if "help" in sys.argv:
        print """
Program to calibrate PLA to compensate for beamshift movements

Usage: 
    instamatic.calibrate_pla
        To start live calibration routine on the microscope
"""
        exit()
    else:
        ctrl = initialize()
        calibrate_pla(ctrl=ctrl)
