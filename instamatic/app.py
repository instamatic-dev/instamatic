#!/usr/bin/env python

import sys, os
import numpy as np

from find_crystals import find_crystals
from find_holes import plot_props, find_holes, calculate_hole_area
import TEMController

from tools import *
from calibration import CalibStage, CalibBrightness, CalibBeamShift, CalibDiffShift, CalibDirectBeam
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


def get_grid(nx, ny=0, radius=1, borderwidth=0.8):
    """Make a grid (size=n*n), and return the coordinates of those
    fitting inside a circle (radius=r)
    nx: `int`
    ny: `int` (optional)
        Used to define a mesh nx*ny, if ny is missing, nx*nx is used
    radius: `float`
        radius of hole
    borderwidth: `float`, 0.0 - 1.0
        define a border around the circumference not to place any points
        should probably be related to the effective camera size: 
    """
    xr = np.linspace(-1, 1, nx)
    if ny:
        yr = np.linspace(-1, 1, ny)
    else:
        yr = xr
    xgrid, ygrid = np.meshgrid(xr, yr)
    sel = xgrid**2 + ygrid**2 < 1.0*(1-borderwidth)
    xvals = xgrid[sel].flatten()
    yvals = ygrid[sel].flatten()
    return xvals*radius, yvals*radius


def get_offsets(box_x, box_y=0, radius=75, padding=2, k=1.0, angle=0, plot=False):
    """
    box_x: float or int,
        x-dimensions of the box in micrometers. 
        if box_y is missing, box_y = box_x
    box_y: float or int,
        y-dimension of the box in micrometers (optional)
    radius: int or float,
        size of the hole in micrometer
    padding: int or float
        distance between boxes in micrometers
    k: float,
        scaling factor for the borderwidth
    """
    nx = 1 + int(2.0*radius / (box_x+padding))
    if box_y:
        ny = 1 + int(2.0*radius / (box_y+padding))
        diff = 0.5*(2*max(box_x, box_y)**2)**0.5
    else:
        diff = 0.5*(2*(box_x)**2)**0.5
        ny = 0
    
    borderwidth = k*(1.0 - (radius - diff) / radius)
       
    x_offsets, y_offsets = get_grid(nx=nx, ny=ny, radius=radius, borderwidth=borderwidth)
    
    if angle:
        sin = np.sin(angle)
        cos = np.cos(angle)
        r = np.array([
                    [ cos, -sin],
                    [ sin,  cos]])
        x_offsets, y_offsets = np.dot(np.vstack([x_offsets, y_offsets]).T, r).T

    if plot:
        from matplotlib import patches
        num = len(x_offsets)
        textstr = "grid: {} x {}\nk: {}\nborder: {:.2f}\nradius: {:.2f}\nboxsize: {:.2f} x {:.2f} um\nnumber: {}".format(nx, ny, k, borderwidth, radius, box_x, box_y, num)
        
        print
        print textstr
        
	cx, cy = (box_x/2.0, box_y/2.0)
        if angle:
            cx, cy = np.dot((cx, cy), r)
        
        if num < 1000:
            fig = plt.figure(figsize=(10,5))
            ax = fig.add_subplot(111)
            plt.scatter(0, 0)
            plt.scatter(x_offsets, y_offsets, picker=8, marker="+")
            circle = plt.Circle((0, 0), radius, fill=False, color="blue")
            ax.add_artist(circle)
            circle = plt.Circle((0, 0), radius*(1-borderwidth/2), fill=False, color="red")
            ax.add_artist(circle)
            
            for dx, dy in zip(x_offsets, y_offsets):
                rect = patches.Rectangle((dx - cx, dy - cy), box_x, box_y, fill=False, angle=np.degrees(-angle))
                ax.add_artist(rect)
            
	    ax.text(1.05, 0.95, textstr, transform=ax.transAxes, fontsize=14,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

            ax.set_xlim(-100, 100)
            ax.set_ylim(-100, 100)
            ax.set_aspect('equal')
            plt.show()
    
    return x_offsets, y_offsets


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
    print " >> Wrote {} coordinates to file".format(len(coords))


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
    
    x_offsets, y_offsets = get_grid(nx=7, radius=r_mean)

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

    args = sys.argv[1:]
    if "gui" in args:
        from gui import prepare_experiment
        ctrl = TEMController.initialize()
        centers, radii = prepare_experiment.start(ctrl)
    elif args:
        fns = sys.argv[1:]
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

def do_experiment(ctrl=None, **kwargs):
    d = fileio.load_experiment()
    centers = d["centers"]
    radius = d["radius"] / 1000 # nm -> um

    calib_stage = CalibStage.from_file()
    calib_beamshift = CalibBeamShift.from_file()
    calib_directbeam = CalibDirectBeam.from_file()

    magnification   = kwargs["magnification"]
    image_binsize   = kwargs.get("image_binsize",       2   )
    image_exposure  = kwargs.get("image_exposure",      0.1 )
    image_spotsize  = kwargs.get("image_spotsize",      1   )
    diff_binsize    = kwargs.get("diff_binsize",        2   )
    diff_exposure   = kwargs.get("diff_exposure",       0.1 )
    diff_brightness = kwargs["diff_brightness"]
    diff_difffocus  = kwargs["diff_difffocus"]
    diff_spotsize   = kwargs.get("diff_spotsize",       5   )
    angle = kwargs["angle"]
    
    import atexit
    atexit.register(ctrl.restore)

    ctrl.mode_diffraction()
    print raw_input(" >> Getting neutral diffraction shift, press enter to continue")
    neutral_diffshift = np.array(ctrl.diffshift.get())
    print neutral_diffshift
    print "DiffShift(x={}, y={})".format(*neutral_diffshift)

    ctrl.mode_mag1()
    ctrl.magnification.value = magnification
    ctrl.brightness.max()
    neutral_beamshift = calib_beamshift.center()
    ctrl.beamshift.set(*neutral_beamshift) # calib_beamshift.reference_shift?

    from config import mag1_dimensions
    box_x, box_y = mag1_dimensions[magnification]

    x_offsets, y_offsets = get_offsets(box_x, box_y, radius, k=1, padding=2, angle=angle, plot=False)
    x_offsets *= 1000
    y_offsets *= 1000

    plot = False
    print
    print "Imaging     : binsize = {}".format(image_binsize)
    print "              exposure = {}".format(image_exposure)
    print "              magnification = {}".format(magnification)
    print "              spotsize = {}".format(image_spotsize)
    print "Diffraction : binsize = {}".format(diff_binsize)
    print "              exposure = {}".format(diff_exposure)
    print "              brightness = {}".format(diff_brightness)
    print "              spotsize = {}".format(diff_spotsize)
    print
    print "Usage:"
    print "    type 'next' to go to the next hole"
    print "    type 'auto' to enable automatic data collection (until next hole)"
    print "    type 'plot' to toggle plotting mode"
    print "    type 'exit' to quit"
    print "    hit 'Ctrl+C' to interrupt the script"

    for i, (x, y) in enumerate(centers):

        try:
            ctrl.stageposition.set(x=x, y=y)
        except ValueError as e:
            print e
            print " >> Moving to next hole..."
            print
            continue

        print "\n >> Going to next hole center \n    ->", ctrl.stageposition

        auto = False
        for j, (x_offset, y_offset) in enumerate(zip(x_offsets, y_offsets)):
            try:
                ctrl.stageposition.set(x=x+x_offset, y=y+y_offset)
            except ValueError as e:
                print e
                print " >> Moving to next position..."
                print
                continue

            print ctrl.stageposition
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

            ctrl.tem.setSpotSize(image_spotsize)
            img, h = ctrl.getImage(binsize=image_binsize, exposure=image_exposure, comment=comment)
            ctrl.tem.setSpotSize(diff_spotsize)

            crystal_coords = find_crystals(img, h["Magnification"], spread=2.5, plot=False) * image_binsize

            h["exp_crystal_coords"] = crystal_coords.tolist()
            h["exp_neutral_diffshift"] = neutral_beamshift
            h["exp_neutral_beamshift"] = neutral_diffshift
            h["exp_hole_number"] = i
            h["exp_image_number"] = j
            h["exp_offset"] = (x_offset, y_offset)
            write_tiff(outfile, img, header=h)

            # plot_props(img, crystals, fname=outfile+".png")

            ncrystals = len(crystal_coords)

            if ncrystals == 0:
                continue

            beamshift_coords = calib_beamshift.pixelcoord_to_beamshift(crystal_coords)

            print
            print " >> Switching to diffraction mode"
            for k, beamshift in enumerate(beamshift_coords):
                ctrl.brightness.set(diff_brightness)
                ctrl.beamshift.set(*beamshift)
                ctrl.mode_diffraction()
                ctrl.difffocus.value = diff_difffocus

                # compensate beamshift
                beamshift_offset = beamshift - neutral_beamshift
                pixelshift = calib_directbeam.beamshift2pixelshift(beamshift_offset)

                diffshift_offset = calib_directbeam.pixelshift2diffshift(pixelshift)
                diffshift = neutral_diffshift - diffshift_offset

                print "bs", beamshift_offset, "ds", diffshift_offset
                
                # diffshift[0] += 1750               
                # diffshift[1] += 5000                
                    
                ctrl.diffshift.set(*diffshift.astype(int))

                outfile = "image_{:04d}_{:04d}_{:04d}".format(i, j, k)
                comment = "Hole {} image {} Crystal {}".format(i, j, k)
                print "{}/{}:".format(k+1, ncrystals),
                img, h = ctrl.getImage(binsize=diff_binsize, exposure=diff_exposure, comment=comment)
                
                h["exp_neutral_diffshift"] = neutral_beamshift
                h["exp_neutral_beamshift"] = neutral_diffshift
                h["exp_diffshift_offset"] = diffshift_offset
                h["exp_beamshift_offset"] = beamshift_offset
                h["exp_hole_number"] = i
                h["exp_image_number"] = j
                h["exp_pattern_number"] = k
                write_tiff(outfile, img, header=h)

            print
            print " >> Switching back to image mode"

            ctrl.beamshift.set(*neutral_beamshift)
            ctrl.diffshift.set(*neutral_diffshift)

            ctrl.mode_mag1()
            ctrl.brightness.max()


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

        binsize = h["ImageBinSize"]
        area = calculate_hole_area(150.0, h["Magnification"], img_scale=scale, binsize=binsize)
        holes = find_holes(img, area=area, plot=plot, fname=outfile, verbose=False)

        for hole in holes:
            centroid = np.array(hole.centroid) * binsize / scale
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


def get_status():
    status = {"stage_lowmag": {"name":"Stage (lowmag)", "ok":False, "msg":"no, please run instamatic.calibrate_stage_lowmag"},
                "stage_mag1": {"name":"Stage (mag1)", "ok":False, "msg":"no, please run instamatic.calibrate_mag1"},
                "beamshift": {"name":"BeamShift", "ok":False, "msg":"no, please run instamatic.calibrate_beamshift"},
                "directbeam": {"name":"DirectBeam", "ok":False, "msg":"no, please run instamatic.calibrate_directbeam"},
                "holes": {"name":"Holes", "ok":False, "msg": "no, please run instamatic.map_holes"},
                "radius": {"name":"Radius", "ok":False, "msg": "no, please run instamatic.prepare_experiment"},
                "params": {"name":"Params", "ok":False, "msg": "no"},
                "ready": {"name":"Ready", "ok":True, "msg": "Experiment is ready!!"}
            }

    try:
        calib = CalibStage.from_file()
    except IOError:
        pass
    else:
        status["stage_lowmag"].update({"ok":True, "msg": "OK"})

    try:
        calib = CalibBeamShift.from_file()
    except IOError:
        pass
    else:
        status["beamshift"].update({"ok":True, "msg": "OK"})

    try:
        calib = CalibDirectBeam.from_file()
    except IOError:
        pass
    else:
        status["directbeam"].update({"ok":True, "msg": "OK"})

    try:
        params = json.load(open("params.json","r"))
    except IOError:
        pass
    else:
        if "angle" in params:
            status["stage_mag1"].update({"ok":True, "msg":"OK, angle={:.2f} deg.".format(np.degrees(params["angle"]))})
        keys = "magnification", "diff_difffocus", "diff_brightness"
        missing_keys = [key for key in keys if key not in params]
        if missing_keys:
            status["params"].update({"ok":False, "msg":"no, missing {}".format(", ".join(missing_keys))})
        else:
            status["params"].update({"ok":True, "msg":"OK"})

    try:
        experiment = fileio.load_experiment()
    except Exception as e:
        pass
    else:
        status["radius"].update({"ok":True, "msg":"OK, {:.2f} um".format(experiment["radius"] / 1000.0)})

    try:
        hole_coords = fileio.load_hole_stage_positions()
    except Exception:
        pass
    else:
        status["holes"].update({"ok":True, "msg":"OK, {} locations stored".format(len(hole_coords))})

    if not all([status[key]["ok"] for key in status]):
        status["ready"].update({"ok":False, "msg":"Experiment is NOT ready!!"})

    return status


def main_gui():
    from gui import main
    main.start()


def main():
    status = get_status()

    print "\nCalibration:"
    for key in "stage_lowmag", "stage_mag1", "beamshift", "directbeam":
        print "    {name:20s}: {msg:s}".format(**status[key])

    print "\nExperiment"
    for key in "holes", "radius", "params", "ready":
        print "    {name:20s}: {msg:s}".format(**status[key])

    ready = status["ready"]["ok"]

    if ready:
        params = json.load(open("params.json","r"))
        if raw_input("\nExperiment ready. Enter 'go' to start. >> ") != "go":
            exit()
        print
        ctrl = TEMController.initialize()
        do_experiment(ctrl, **params)
    else:
        print "\nExperiment not ready yet!!"

if __name__ == '__main__':
    main()
