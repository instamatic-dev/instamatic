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


def load_calib():
    CALIB100X = "calib.pickle"
    if os.path.exists(CALIB100X):
        d = pickle.load(open(CALIB100X, "r"))
        calib = CalibResult(**d)
    else:
        print "\n >> Please run instamatic.calibrate100x first."
        exit()
    return calib


def load_hole_stage_positions():
    HOLE_COORDS = "hole_coords.npy"
    if os.path.exists(HOLE_COORDS):
        coords = np.load(HOLE_COORDS)
    else:
        print "\n >> Please run instamatic.map_holes_on_grid first."
        exit()
    return coords


def plot_hole_stage_positions(calib, coords, picker=False):
    fig = plt.figure()
    reflabel = "Reference position"
    holelabel = "Hole position"
    plt.scatter(*calib.reference_position, c="red", label="Reference position", picker=8)
    plt.scatter(coords[:,0], coords[:,1], c="blue", label="Hole position", picker=8)
    for i, (x,y) in enumerate(coords):
        plt.text(x, y, str(i), size=20)
    plt.legend()
    minval = coords.min()
    maxval = coords.max()
    plt.xlim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
    plt.ylim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
    
    def onclick(event):
        ind = event.ind[0]
        
        label = event.artist.get_label()
        if label == reflabel:
            xval, yval = calib.reference_position
        else:
            xval, yval = coords[ind]

        print "Pick event -> {} -> ind: {}, xdata: {:.3e}, ydata: {:.3e}".format(label, ind, xval, yval)
        ctrl.stageposition.goto(x=xval, y=yval)
        print ctrl.stageposition
        print

    if picker:
        fig.canvas.mpl_connect('pick_event', onclick)

    plt.show()


def goto_hole_entry():
    calib = load_calib()
    coords = load_hole_stage_positions()

    try:
        num = int(sys.argv[1])
    except IndexError:
        print "\nUsage: instamatic.goto_hole [N]"
        print
        plot_hole_stage_positions(calib, coords, picker=True)
        # num = int(raw_input( "Which number to go to? \n >> [0-{}] ".format(len(coords))))
    else:
        if num > len(coords):
            print " >> '{}' not in coord list (max={})".format(num, len(coords))
            exit()
        stage_x, stage_y = coords[num]

        ctrl.stageposition.goto(x=stage_x, y=stage_y)
        print ctrl.stageposition


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
        print "Now processing:", fn
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
    xy = xy[xy[:,0].argsort(axis=0)]

    if plot:
        plot_hole_stage_positions(calib, xy)
    print "Found {} unique holes (threshold={})".format(len(xy), threshold)
    return xy


def map_holes_on_grid_entry():
    calib = load_calib()

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
