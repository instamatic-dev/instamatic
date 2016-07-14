#!/usr/bin/env python

import sys, os
import numpy as np

from pyscope import jeolcom, simtem
from camera import gatanOrius, save_image, save_header
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
        raise IOError("\n >> Please run instamatic.calibrate100x first.")
    return calib


def load_hole_stage_positions():
    HOLE_COORDS = "hole_coords.npy"
    if os.path.exists(HOLE_COORDS):
        coords = np.load(HOLE_COORDS)
    else:
        raise IOError("\n >> Please run instamatic.map_holes_on_grid first.")
    return coords


def load_experiment():
    EXPERIMENT = "experiment.pickle"
    if os.path.exists(EXPERIMENT):
        d = pickle.load(open(EXPERIMENT, "r"))
    else:
        raise IOError("\n >> Please run instamatic.prepare_experiment first.")
    return d


def circle_center(A, B, C):
    """Finds the center of a circle from 3 positions on the circumference

    Adapted from http://stackoverflow.com/a/21597515"""
    Ax, Ay = A
    Bx, By = B
    Cx, Cy = C
    
    yDelta_a = By - Ay
    xDelta_a = Bx - Ax
    yDelta_b = Cy - By
    xDelta_b = Cx - Bx
    
    aSlope = yDelta_a/xDelta_a
    bSlope = yDelta_b/xDelta_b
    
    center_x = (aSlope*bSlope*(Ay - Cy) + bSlope*(Ax + Bx)
        - aSlope*(Bx+Cx) )/(2* (bSlope-aSlope) )
    center_y = -1*(center_x - (Ax+Bx)/2)/aSlope +  (Ay+By)/2
    
    return np.array([center_x, center_y])


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i+n]


def get_grid(n, r, borderwidth=0.8):
    """Make a grid (size=n*n), and return the coordinates of those
    fitting inside a circle (radius=r)
    n: `int`
        Used to define a mesh n*n
    r: `float`
        radius of hole
    borderwidth: `float`, 0.0 - 1.0
        define a border around the circumference not to place any points
        should probably be related to the effective camera size: 
    """
    yr = xr = np.linspace(-1, 1, n)
    xgrid, ygrid = np.meshgrid(xr, yr)
    sel = xgrid**2 + ygrid**2 < 1.0*borderwidth
    xvals = xgrid[sel].flatten()
    yvals = ygrid[sel].flatten()
    return xvals*r, yvals*r 


def find_hole_center_high_mag_from_files(fns):
    centers = []
    vects = []
    print "Now processing:", fns
    for i,fn in enumerate(fns):
        img, header = load_img(fn)
        img = img.astype(int)
        x,y = np.array([header["StagePosition"]["x"], header["StagePosition"]["y"]])
        if i != 3:
            vects.append((x,y))
        
    center = circle_center(*vects)
    r = np.mean([np.linalg.norm(v-center) for v in vects]) # approximate radius
    return center, r


def fake_circle():
    import random
    da = random.randrange(-5,5) * 2.2
    db = random.randrange(-5,5) * 2.2
    vects = []
    for i in range(3):
        a = random.randrange(-100,100)/100.0
        b = (1 - a**2)**0.5
        vects.append((a+da, b+db))
    return vects


def find_hole_center_high_mag_interactive():
    while True:
        print "\nPick 3 points centering the camera on the edge of a hole"
        raw_input(" 1 >> ")
        v1 = ctrl.stageposition.x, ctrl.stageposition.y
        raw_input(" 2 >> ")
        v2 = ctrl.stageposition.x, ctrl.stageposition.y
        raw_input(" 3 >> ")
        v3 = ctrl.stageposition.x, ctrl.stageposition.y
    
        # in case of simulation mode generate a fake circle
        if v1 == (0, 0) and v2 == (0, 0) and v3 == (0, 0):
            v1, v2, v3 = fake_circle()
    
        center = circle_center(v1, v2, v3)
        radius = np.mean([np.linalg.norm(np.array(v)-center) for v in (v1, v2, v3)])
        print "Center:", center
        print "Radius:", radius
        
        answer = raw_input("\nkeep? \n [YES/no/done/exit] >> ")
        
        if "n" in answer:
            continue
        elif "d" in answer:
            raise StopIteration
        elif "x" in answer:
            exit()
        else:
            yield center, radius


def prepare_experiment_entry():
    # fns = sys.argv[1:]
    centers = []
    radii = []
    fns = sys.argv[1:]

    if fns:
        for fns in chunks(sys.argv[1:], 3):
            center, radius = find_hole_center_high_mag_from_files(fns)
            centers.append(center)
            radii.append(radius)
    else:
        for center, radius in find_hole_center_high_mag_interactive():
            centers.append(center)
            radii.append(radius)

    centers = np.array(centers)

    r_mean = np.mean(radii)
    r_std = np.std(radii)
    print "Average radius: {}+-{} ({:.1%})".format(r_mean, r_std, (r_std/r_mean))
    
    x_offsets, y_offsets = get_grid(n=7, r=r_mean)

    pickle.dump({
        "centers": centers,
        "radius": radius,
        "x_offsets": x_offsets,
        "y_offsets": y_offsets
        }, open("experiment.pickle","w"))

    plot_experiment_entry()


def plot_experiment_entry():
    d = load_experiment()
    calib = load_calib()
    centers = d["centers"]
    radius = d["radius"]
    x_offsets = d["x_offsets"]
    y_offsets = d["y_offsets"]
    
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)

    plt.scatter(*calib.reference_position)

    x_offsets, y_offsets = get_grid(n=7, r=radius)
    for x_cent, y_cent in centers:
        plt.scatter(x_cent, y_cent)
        plt.scatter(x_offsets+x_cent, y_offsets+y_cent, s=1)
        circle = plt.Circle((x_cent, y_cent), radius, edgecolor='r', facecolor="none")
        ax.add_artist(circle)
    
    plt.axis('equal')
    
    minval = centers.min()
    maxval = centers.max()
    plt.xlim(minval - abs(minval*0.2), maxval + abs(maxval*0.2))
    plt.ylim(minval - abs(minval*0.2), maxval + abs(maxval*0.2))

    plt.show()


def do_experiment_entry():
    d = load_experiment()
    centers = d["centers"]
    radius = d["radius"]
    x_offsets = d["x_offsets"]
    y_offsets = d["y_offsets"]

    binsize = 1
    exposure = 0.1
    plot = False

    print "binsize = {} | exposure = {}".format(binsize, exposure)
    print
    print "Usage:"
    print "    type 'next' to go to the next hole"
    print "    type 'exit' to interrupt the script"
    print "    type 'auto' to enable automatic mode (until next hole)"
    print "    type 'plot' to toggle plotting mode"

    i = 0
    for x, y in centers:
        ctrl.stageposition.goto(x=x, y=y)
        print "\n >> Going to next hole center \n    ->", ctrl.stageposition

        j = 0
        auto = False
        for x_offset, y_offset in zip(x_offsets, y_offsets):
            ctrl.stageposition.goto(x=x, y=y)

            outfile = "image_{:04d}_{:04d}.npy".format(i,j)

            if not auto:
                answer = raw_input("\n (Press <enter> to save an image and continue) \n >> ")
                if answer == "exit":
                    print " >> Interrupted..."
                    exit()
                elif answer == "next":
                    print " >> Going to next hole"
                    break
                elif answer == "auto":
                    auto = True
                elif answer == "plot":
                    plot = not plot

            comment = "Hole {} image {}\nx_offset={:.2e} y_offset={:.2e}".format(i, j, x_offset, y_offset)

            h = tem.getHeader()
            arr = cam.getImage(binsize=binsize, t=exposure)
            h["ImageExposureTime"] = exposure
            h["ImageBinSize"] = binsize
            h["ImageResolution"] = arr.shape
            h["ImageComment"] = comment
    
            save_image(outfile, arr)
            save_header(outfile, h)

            if plot:
                plt.imshow(arr, cmap="gray")
                plt.title(comment)
                plt.show()

            j += 1

        i += 1


def plot_hole_stage_positions(calib, coords, picker=False):
    fig = plt.figure()
    reflabel = "Reference position"
    holelabel = "Hole position"
    plt.scatter(*calib.reference_position, c="red", label="Reference position", picker=8)
    plt.scatter(coords[:,0], coords[:,1], c="blue", label="Hole position", picker=8)
    for i, (x,y) in enumerate(coords):
        plt.text(x, y, str(i), size=20)

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

    plt.legend()
    plt.axis('equal')
    
    minval = coords.min()
    maxval = coords.max()
    plt.xlim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
    plt.ylim(minval - abs(minval)*0.2, maxval + abs(maxval)*0.2)
    
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
    if not fns:
        print "Usage: instamatic.map_holes IMG1 [IMG2 ...]"
        exit()
    
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
        calib = calibrate_lowmag(ctrl, cam, save_images=True)
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
