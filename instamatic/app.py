#!/usr/bin/env python

import sys, os
import numpy as np

from pyscope import jeolcom, simtem
from camera import gatanOrius
from find_crystals import find_objects, plot_props
from TEMController import TEMController

from IPython import embed

from calibration import CalibResult, load_img
import matplotlib.pyplot as plt
from find_crystals import find_holes


import pickle

try:
    tem = jeolcom.Jeol()
    cam = gatanOrius()
except WindowsError:
    print " >> Could not connect to JEOL, using SimTEM instead..."
    tem = simtem.SimTEM()
    cam = gatanOrius(simulate=True)
ctrl = TEMController(tem)


def cluster_mean(arr, threshold=0.00005):
    """Simple clustering/averaging routine based on fclusterdata"""
    from scipy.cluster.hierarchy import fclusterdata
    clust = fclusterdata(arr, threshold, criterion="distance")
    
    merged = []
    for i in np.unique(clust):
        merged.append(np.mean(arr[clust==i], axis=0))
    return np.array(merged)


def map_holes_on_grid(fns, calib, plot=True):
    stage_coords = []
    for fn in fns:
        img, header = load_img(fn)
        img = img.astype(int)
        image_pos = np.array([header["StagePosition"]["x"], header["StagePosition"]["y"]])

        holes = find_holes(img, header, plot=False)

        for hole in holes:
            stagepos = calib.pixelcoord_to_stagepos(hole.centroid, image_pos)
            stage_coords.append(stagepos)

    xy = np.array(stage_coords)

    threshold = 0.00005
    xy = cluster_mean(xy, threshold=threshold)
    if plot:
        plt.scatter(*calib.reference_position, c="red", label="Reference position")
        plt.scatter(xy[:,0], xy[:,1], c="blue", label="Hole position")
        plt.legend()
        minval = xy.min()
        maxval = xy.max()
        plt.xlim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
        plt.ylim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
        plt.show()
    print "Found {} unique holes (threshold={})".format(len(xy), threshold)


def map_holes_on_grid_entry():
    if os.path.exists("calib.pickle"):
        d = pickle.load(open("calib.pickle", "r"))
        calib = CalibResult(**d)
    else:
        print "\n >> Please run instamatic.calibrate100x first."
        exit()

    print
    print calib
    print

    fns = sys.argv[1:]
    coords = map_holes_on_grid(fns, calib)
    np.save("hole_coords.npy", coords)


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

    print calib

    pickle.dump({
        "transform": calib.transform,
        "reference_position": calib.reference_position
        }, open("calib.pickle","w"))


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

    