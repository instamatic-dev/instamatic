#!/usr/bin/env python

import sys, os
import numpy as np

from camera import save_image_and_header
from find_crystals import find_crystals, plot_props, find_holes, calculate_hole_area
import TEMController

from tools import *
from calibration import CalibStage, CalibBrightness, CalibBeamShift, CalibDiffShift
import matplotlib.pyplot as plt
import fileio

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


def seek_and_destroy_from_image_fn(img, calib, ctrl=None, plot=False):
    """Routine that handles seeking crystals, and shooting them with the beam"""

    calib_brightness, calib_beamshift = calib

    exposure = 1.0
    binsize = 1

    img = img.astype(int)
    crystals = find_crystals(img)
    if plot:
        plot_props(img, crystals)

    for i, crystal in enumerate(crystals):
        x, y = crystal.centroid
        d = crystal.equivalent_diameter
        print
        print "Crystal #{}".format(i)
        print "Pixel - x: {}, y: {}, d: {}".format(x,y,d)

        bd = calib_brightness.pixelsize_to_brightness(d)
        bx, by = calib_beamshift.pixelcoord_to_beamshift((x,y))

        bd = int(bd)
        bx = int(bx)
        by = int(by)

        print "Beam  - x: {}, y: {}, d: {}".format(bx,by,bd)

        ctrl.beamshift.set(bx, by)
        ctrl.brightness.set(bd)

        raw_input(" >> Press enter to take diffraction pattern and go to next crystal...")
        
        # ctrl.mode_diffraction()

        # arr, h = ctrl.getImage(binsize=binsize, exposure=exposure, out="seekdestroy_{:04d}".format(i), comment="Diffraction data")

        # ctrl.mode_mag1()



def seek_and_destroy_entry():
    exposure = 0.2
    binsize = 1

    calib = (CalibBrightness.from_file(), CalibBeamShift.from_file())
    ctrl = TEMController.initialize()

    fns = sys.argv[1:]
    if fns:
        for fn in fns:
            arr, header = load_img(fn)
            seek_and_destroy_from_image_fn(arr, calib, ctrl=ctrl, plot=True)
    else:
        arr, header = ctrl.getImage(binsize=binsize, exposure=exposure, comment="Seek and destroy")
    
        seek_and_destroy_from_image_fn(arr, calib, ctrl=ctrl, plot=True)
    
        # save_image(outfile, arr)
        # save_header(outfile, h)


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


def find_hole_center_highmag_interactive(ctrl=None):
    if not ctrl:
        ctrl = TEMController.initialize()
    while True:
        print "\nPick 3 points centering the camera on the edge of a hole"
        print " 1 >> ",
        raw_input()
        v1 = ctrl.stageposition.x, ctrl.stageposition.y
        print v1
        print " 2 >> ",
        raw_input()
        v2 = ctrl.stageposition.x, ctrl.stageposition.y
        print v2
        print " 3 >> ",
        raw_input()
        v3 = ctrl.stageposition.x, ctrl.stageposition.y
        print v3
    
        # in case of simulation mode generate a fake circle
        if v1 == (0, 0) and v2 == (0, 0) and v3 == (0, 0):
            v1, v2, v3 = fake_circle()
        
        try:
            center = circle_center(v1, v2, v3)
            radius = np.mean([np.linalg.norm(np.array(v)-center) for v in (v1, v2, v3)])
        except:
            print "Could not determine circle center/radius... Try again"
            continue
        print "Center:", center
        print "Radius:", radius
        
        answer = raw_input("\ncontinue? \n [YES/no/redo] >> ")
        
        if "n" in answer:
            yield center, radius
            raise StopIteration
        elif "r" in answer:
            continue
        else:
            yield center, radius

def update_experiment_with_hole_coords(coords):
    experiment = fileio.load_experiment()

    radius = experiment["radius"]

    shifts = []
    print "\n >> Trying to find shift correction factor lowmag -> mag1 coords..."
    for xy in experiment["centers"]:
        dist_sq = np.sum((coords - xy)**2, axis=1)
        nearest = np.argmin(dist_sq)
        val = dist_sq[nearest]
    
        if val**0.5 < radius:
            shift = coords[nearest] - xy
            shifts.append(shift)
            print "Shift:", shift

    mean_shift = np.mean(np.array(shifts), axis=0)
    print " >> Correction factor (mean shift): {}".format(mean_shift)

    corrected = coords - mean_shift

    plot = False
    if plot:
        plt.scatter(*coords.T, color="grey", label="original lowmag coords")
        plt.scatter(*corrected.T, color="blue", label="corrected lowmag coords")
        plt.scatter(*experiment["centers"].T, color="red", label="picked mag1 coords")
        plt.legend()
        plt.show()

    experiment["centers_mag1"] = experiment["centers"]
    experiment["stagepos_shift"] = mean_shift 
    experiment["centers"] = corrected

    fileio.write_experiment(experiment)
    print " >> Wrote {} coordinates to file {}".format(len(coords), EXPERIMENT)



def update_experiment_with_hole_coords_entry():
    if len(sys.argv) == 1:
        coords = fileio.load_hole_stage_positions()
    else:
        fn = sys.argv[1]
        coords = np.load(fn)

    update_experiment_with_hole_coords(coords)


def prepare_experiment(centers, radii):
    centers = np.array(centers)

    r_mean = np.mean(radii)
    r_std = np.std(radii)
    print "Average radius: {}+-{} ({:.1%})".format(r_mean, r_std, (r_std/r_mean))
    
    x_offsets, y_offsets = get_grid(n=7, r=r_mean)

    experiment = {
        "centers": centers,
        "radius": r_mean,
        "x_offsets": x_offsets,
        "y_offsets": y_offsets
        }

    fileio.write_experiment(experiment)


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
        for center, radius in find_hole_center_highmag_interactive():
            centers.append(center)
            radii.append(radius)

    prepare_experiment(centers, radii)

    try:
        plot_experiment_entry()
    except IOError:
        pass

def plot_experiment(ctrl=None):
    d = fileio.load_experiment()
    calib = CalibStage.from_file()
    centers = d["centers"]
    radius = d["radius"]
    x_offsets = d["x_offsets"]
    y_offsets = d["y_offsets"]
    
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)

    plt.scatter(*calib.reference_position)

    for i, (x_cent, y_cent) in enumerate(centers):
        plt.scatter(x_cent, y_cent)
        plt.scatter(x_offsets+x_cent, y_offsets+y_cent, s=1, picker=8, label=str(i))
        circle = plt.Circle((x_cent, y_cent), radius, edgecolor='r', facecolor="none", alpha=0.5)
        ax.add_artist(circle)

    skiplist = []    
    def onclick(event):
        click = event.mouseevent.button
        ind = event.ind[0]
        label = int(event.artist.get_label())

        if click == 1:
            x_cent, y_cent = centers[label]
            x_offset = x_offsets[ind]
            y_offset = y_offsets[ind]
    
            x = x_cent+x_offset
            y = y_cent+y_offset
    
            print "Pick event -> {} -> ind: {}, xdata: {:.3e}, ydata: {:.3e}".format(label, ind, x, y)
            ctrl.stageposition.set(x=x, y=y)
            print ctrl.stageposition
            print
        elif click == 3:
            alpha = event.artist.get_alpha()
            if (not alpha) or alpha == 1.0:
                skiplist.append(int(label))
                event.artist.set_alpha(0.2)
            else:
                skiplist.remove(int(label))
                event.artist.set_alpha(None)

            fig.canvas.draw()
            # print skiplist

    fig.canvas.mpl_connect('pick_event', onclick)
    # fig.canvas.mpl_connect('button_press_event', onpress)


    plt.axis('equal')
    
    minval = centers.min()
    maxval = centers.max()
    plt.xlim(minval - abs(minval*0.2), maxval + abs(maxval*0.2))
    plt.ylim(minval - abs(minval*0.2), maxval + abs(maxval*0.2))

    plt.show()

def plot_experiment_entry():
    ctrl = TEMController.initialize()
    plot_experiment(ctrl=ctrl)

def do_experiment(ctrl=None):
    d = fileio.load_experiment()
    centers = d["centers"]
    radius = d["radius"]
    x_offsets = d["x_offsets"]
    y_offsets = d["y_offsets"]

    binsize = 1
    exposure = 0.2
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
        try:
            ctrl.stageposition.set(x=x, y=y)
        except ValueError as e:
            print e
            print " >> Moving to next hole..."
            print
            i += 1
            continue

        print "\n >> Going to next hole center \n    ->", ctrl.stageposition

        j = 0
        auto = False
        for x_offset, y_offset in zip(x_offsets, y_offsets):
            try:
                ctrl.stageposition.set(x=x+x_offset, y=y+y_offset)
            except ValueError as e:
                print e
                print " >> Moving to next position..."
                print
                j += 1
                continue

            outfile = "image_{:04d}_{:04d}".format(i,j)

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

            arr, h = ctrl.getImage(binsize=binsize, exposure=exposure, comment=comment)
    
            save_image_and_header(outfile, img=arr, header=h)

            if plot:
                plt.imshow(arr, cmap="gray")
                plt.title(comment)
                plt.show()

            j += 1

        i += 1


def do_experiment_entry():
    ctrl = TEMController.initialize()
    do_experiment(ctrl)


def plot_hole_stage_positions(coords=None, calib=None, ctrl=None, picker=False):
    if calib is None:
        calib = CalibStage.from_file()
    if coords is None:
        coords = fileio.load_hole_stage_positions()
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
        ctrl.stageposition.set(x=xval, y=yval)
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
    ctrl = TEMController.initialize()

    calib = CalibStage.from_file()
    coords = fileio.load_hole_stage_positions()

    try:
        num = int(sys.argv[1])
    except IndexError:
        print "\nUsage: instamatic.goto_hole [N]"
        print
        plot_hole_stage_positions(coords, calib, ctrl=ctrl, picker=True)
        # num = int(raw_input( "Which number to go to? \n >> [0-{}] ".format(len(coords))))
    else:
        if num > len(coords):
            print " >> '{}' not in coord list (max={})".format(num, len(coords))
            exit()
        stage_x, stage_y = coords[num]

        ctrl.stageposition.set(x=stage_x, y=stage_y)
        print ctrl.stageposition


def cluster_mean(arr, threshold=0.00005):
    """Simple clustering/averaging routine based on fclusterdata"""
    from scipy.cluster.hierarchy import fclusterdata
    clust = fclusterdata(arr, threshold, criterion="distance")
    
    merged = []
    for i in np.unique(clust):
        merged.append(np.mean(arr[clust==i], axis=0))
    return np.array(merged)


def map_holes_on_grid(fns, plot=False, save_images=False, callback=None):
    calib = CalibStage.from_file()
    print
    print calib
    stage_coords = []
    for fn in fns:
        print
        print "Now processing:", fn
        img, h = load_img(fn)
        img = img.astype(int)

        img, scale = autoscale(img)

        image_pos = np.array(h["StagePosition"][:2])

        if callback:
            callback(img=img, header=h, name=fn)

        outfile = os.path.splitext(fn)[0] + ".tiff" if save_images else None

        area = calculate_hole_area(150.0, h["Magnification"], img_scale=scale)
        holes = find_holes(img, area=area, plot=plot, fname=outfile, verbose=False)

        for hole in holes:
            centroid = np.array(hole.centroid) / scale
            stagepos = calib.pixelcoord_to_stagepos(centroid, image_pos)
            stage_coords.append(stagepos)

    xy = np.array(stage_coords)

    threshold = 10000

    xy = cluster_mean(xy, threshold=threshold)
    xy = xy[xy[:,0].argsort(axis=0)]

    if plot:
        plot_hole_stage_positions(calib, xy)

    print
    print "Found {} unique holes (threshold={})".format(len(xy), threshold)
    np.save(fileio.HOLE_COORDS, xy)


def map_holes_on_grid_entry():
    fns = sys.argv[1:]
    if not fns:
        print "Usage: instamatic.map_holes IMG1 [IMG2 ...]"
        exit()
    
    map_holes_on_grid(fns)


def main():
    print "High tension:", tem.getHighTension()
    print

    if True:
        for d in tem.getCapabilities():
            if 'get' in d["implemented"]:
                print "{:30s} : {}".format(d["name"], getattr(tem, "get"+d["name"])())

    if True:
        img, h = ctrl.getImage()

        # img = color.rgb2gray(img)
        img = np.invert(img)
        print img.min(), img.max()
        crystals = find_crystals(img)
        plot_props(img, crystals)

    # embed()


if __name__ == '__main__':
    main()
