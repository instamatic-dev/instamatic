#!/usr/bin/env python

import sys, os
import numpy as np

from pyscope import jeolcom, simtem
from camera import gatanOrius
from find_crystals import find_objects, plot_props
from TEMController import TEMController

from IPython import embed

try:
    tem = jeolcom.Jeol()
    cam = gatanOrius()
except WindowsError:
    print " >> Could not connect to JEOL, using SimTEM instead..."
    tem = simtem.SimTEM()
    cam = gatanOrius(simulate=True)
ctrl = TEMController(tem)


def calibrate100x_entry():
    from calibration import calibrate_lowmag, calibrate_lowmag_from_image_fn


    if "help" in sys.argv:
        print """
Program to calibrate lowmag (100x) of microscope

Usage: 

    instamatic.calibrate100x
        To start live calibration routine on the microscope
    
    instamatic.calibrate100x CENTER_IMAGE (CALIBRATION_IMAGE ...)
       To perform calibration using pre-collected images
"""
        exit()
    elif len(sys.argv) == 1:
        r, t = calibrate_lowmag(ctrl, cam)
    else:
        fn_center = sys.argv[1]
        fn_other = sys.argv[2:]
        calib = calibrate_lowmag_from_image_fn(fn_center, fn_other)
    
    print "\nRotation/scalint matrix:\n", calib.transform
    print "Reference stagepos:", calib.reference_position


def main():
    print "High tension:", tem.getHighTension()
    print

    if True:
        for d in tem.getCapabilities():
            if 'get' in d["implemented"]:
                print "{:30s} : {}".format(d["name"], getattr(tem, "get"+d["name"])())

    if True:
        img = cam.getImage()

        # img = color.rgb2gray(img)
        img = np.invert(img)
        print img.min(), img.max()
        crystals = find_crystals(img)
        plot_props(img, crystals)

    # embed()


if __name__ == '__main__':
    main()

    