import os, sys
import numpy as np
import json

import matplotlib.pyplot as plt

import fileio

from formats import *
from find_crystals import find_crystals, find_crystals_timepix
from calibrate import CalibStage, CalibBeamShift, CalibDirectBeam, get_diffraction_pixelsize
from TEMController import config
from flatfield import remove_deadpixels, apply_flatfield_correction
from tools import printer

import time
import logging
from tqdm import tqdm


def make_grid_on_stage(startpoint, endpoint, padding=2.0):
    """Divide the stage up in a grid, starting at 'startpoint' ending at 'endpoint'"""
    stepsize = np.array((0.016*512, 0.016*512))
    
    x1, y1 = pos1 = np.array((0, 0))
    x2, y2 = pos2 = np.array((1000, 1000))
    
    pos_delta = pos2 - pos1
    
    nx, ny = np.abs(pos_delta / (stepsize + padding)).astype(int)
    
    xgrid, ygrid = np.meshgrid(np.linspace(x1, x2, nx), np.linspace(y1, y2, ny))
    
    return np.stack((xgrid.flatten(), ygrid.flatten())).T


def get_gridpoints_in_hole(nx, ny=0, radius=1, borderwidth=0.8):
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
    # reverse order of every other row for more efficient pathing
    xgrid[1::2] = np.fliplr(xgrid[1::2]) 

    sel = xgrid**2 + ygrid**2 < 1.0*(1-borderwidth)
    xvals = xgrid[sel].flatten()
    yvals = ygrid[sel].flatten()
    return xvals*radius, yvals*radius


def get_offsets_in_hole(box_x, box_y=0, radius=75, padding=2, k=1.0, angle=0, plot=False):
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
       
    x_offsets, y_offsets = get_gridpoints_in_hole(nx=nx, ny=ny, radius=radius, borderwidth=borderwidth)
    
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
    
    return np.vstack((x_offsets, y_offsets)).T


class Experiment(object):
    """docstring for Experiment"""
    def __init__(self, ctrl, config, log=None):
        super(Experiment, self).__init__()
        self.ctrl = ctrl
        self.camera = ctrl.cam.name
        self.log = log

        self.setup_folders()

        self.load_calibration(**config)

        # set flags
        self.ctrl.tem.VERIFY_STAGE_POSITION = False

    def setup_folders(self, expdir=None):
        if not expdir:
            n = 1
            while True:
                drc = "experiment{}".format(n)
                if os.path.exists(drc):
                    n += 1
                else:
                    break
            self.curdir = os.path.abspath(os.path.curdir)
            expdir = os.path.join(drc)
        self.expdir = expdir
        self.calibdir = os.path.join(self.expdir, "calib")
        self.imagedir = os.path.join(self.expdir, "images")
        self.datadir = os.path.join(self.expdir, "data")
        if not os.path.exists(self.expdir):
            os.mkdir(self.expdir)
            os.mkdir(self.calibdir)
            os.mkdir(self.imagedir)
            os.mkdir(self.datadir)
        return self.expdir

    def load_calibration(self, **kwargs):
        """Load user specified config and calibration files"""
        
        try:
            d = fileio.load_experiment()
            self.calib_stage = CalibStage.from_file()
        except IOError:
            self.ctrl.mode_mag1()
            self.ctrl.brightness.max()

            print "\nSelect area to scan"
            print "-------------------"
            raw_input(" >> Move the stage to where you want to start and press <ENTER> to continue")
            x, y, _, _, _ = self.ctrl.stageposition.get()
            self.hole_centers = np.array([[x,y]])            
            self.hole_radius = float(raw_input(" >> Enter the radius (micrometer) of the area to scan: [100] ") or 100)
            border_k = 0
        else:
            self.hole_centers = d["centers"]
            self.hole_radius = d["radius"] / 1000 # nm -> um
            border_k = 1

        self.image_binsize   = kwargs.get("image_binsize",       self.ctrl.cam.default_binsize)
        self.image_exposure  = kwargs.get("image_exposure",      self.ctrl.cam.default_exposure)
        self.image_spotsize  = kwargs.get("image_spotsize",      4   )
        # self.magnification   = kwargs["magnification"]
        self.image_threshold = kwargs.get("image_threshold",     100)
         # do not store brightness to self, as this is set later when calibrating the direct beam
        image_brightness = kwargs.get("diff_brightness", 38000)
        
        try:
            self.calib_beamshift = CalibBeamShift.from_file()
        except IOError:
            self.ctrl.mode_mag1()
            self.ctrl.store("image")
            self.ctrl.brightness.set(image_brightness)
            self.ctrl.tem.setSpotSize(self.image_spotsize)

            self.calib_beamshift = CalibBeamShift.live(self.ctrl, outdir=self.calibdir)
            
            self.magnification = self.ctrl.magnification.value
            self.log.info("Brightness=%s", self.ctrl.brightness)

        self.image_dimensions = config.mag1_camera_dimensions[self.magnification]
        self.log.info("Image dimensions %s", self.image_dimensions)

        self.diff_binsize    = kwargs.get("diff_binsize",        self.ctrl.cam.default_binsize)  # this also messes with calibrate_beamshift class
        self.diff_exposure   = kwargs.get("diff_exposure",       self.ctrl.cam.default_exposure)
        self.diff_spotsize   = kwargs.get("diff_spotsize",       4   )
        # self.diff_cameralength = kwargs.get("diff_cameralength",       800)

        try:
            self.calib_directbeam = CalibDirectBeam.from_file()
        except IOError:
            self.ctrl.mode_diffraction()
            self.ctrl.store("diffraction")
            self.ctrl.tem.setSpotSize(self.diff_spotsize)

            self.calib_directbeam = CalibDirectBeam.live(self.ctrl, outdir=self.calibdir)

            self.diff_brightness = self.ctrl.brightness.value
            self.diff_difffocus = self.ctrl.difffocus.value
            self.diff_cameralength = self.ctrl.magnification.value

        self.diff_pixelsize  = get_diffraction_pixelsize(self.diff_difffocus, self.diff_cameralength, binsize=self.diff_binsize, camera=self.camera)
        self.change_spotsize = self.diff_spotsize != self.image_spotsize
        self.crystal_spread = kwargs.get("crystal_spread", 0.6)

        if self.ctrl.cam.name == "timepix":
            self.find_crystals = find_crystals_timepix
            self.flatfield = kwargs.get("flatfield", "flatfield.tiff")
        else:
            self.find_crystals = find_crystals
            self.flatfield = None

        if self.flatfield is not None:
            self.flatfield, h_flatfield = read_tiff(self.flatfield)
            self.deadpixels = h_flatfield["deadpixels"]

        # self.sample_rotation_angles = ( -10, -5, 5, 10 )
        # self.sample_rotation_angles = (-5, 5)
        self.sample_rotation_angles = ()
    
        self.camera_rotation_angle = config.camera_rotation_vs_stage_xy

        box_x, box_y = self.image_dimensions

        offsets = get_offsets_in_hole(box_x, box_y, self.hole_radius, k=border_k, padding=2, angle=self.camera_rotation_angle, plot=False)
        self.offsets = offsets * 1000

        # store kwargs to experiment drc
        kwargs["diff_brightness"]   = self.diff_brightness
        kwargs["diff_cameralength"] = self.diff_cameralength
        kwargs["diff_difffocus"]    = self.diff_difffocus
        kwargs["hole_radius"]       = self.hole_radius
        kwargs["hole_centers"]      = self.hole_centers.tolist()
        kwargs["hole_positions"]    = len(self.offsets)
        kwargs["image_dimensions"]  = self.image_dimensions

        json.dump(kwargs, open(os.path.join(self.expdir, "params_out.json"), "w"))

    def initialize_microscope(self):
        """Intialize microscope"""

        import atexit
        atexit.register(self.ctrl.restore)

        self.ctrl.mode_diffraction()
        self.ctrl.brightness.set(self.diff_brightness)
        self.ctrl.difffocus.set(self.diff_difffocus)
        self.ctrl.tem.setSpotSize(self.diff_spotsize)
        raw_input("\nPress <ENTER> to get neutral diffraction shift")
        self.neutral_diffshift = np.array(self.ctrl.diffshift.get())
        self.log.info("DiffShift(x=%d, y=%d)", *self.neutral_diffshift)
    
        self.ctrl.mode_mag1()
        self.ctrl.magnification.value = self.magnification
        self.ctrl.brightness.max()
        self.calib_beamshift.center(self.ctrl)
        self.neutral_beamshift = self.ctrl.beamshift.get()
        self.ctrl.tem.setSpotSize(self.image_spotsize)

    def image_mode(self, delay=0.2):
        """Switch to image mode (mag1), reset beamshift/diffshift, spread beam"""
        
        self.log.debug("Switching back to image mode")
        time.sleep(delay)

        self.ctrl.beamshift.set(*self.neutral_beamshift)
        # avoid setting diffshift in image mode, because it messes with the beam position
        if self.ctrl.mode == "diff":
            self.ctrl.diffshift.set(*self.neutral_diffshift)

        self.ctrl.mode_mag1()
        self.ctrl.brightness.max()

    def diffraction_mode(self, delay=0.2):
        """Switch to diffraction mode, focus the beam, and set the correct focus
        """
        self.log.debug("Switching to diffraction mode")
        time.sleep(delay)

        self.ctrl.brightness.set(self.diff_brightness)
        self.ctrl.mode_diffraction()
        self.ctrl.difffocus.value = self.diff_difffocus # difffocus must be set AFTER switching to diffraction mode

    def report_status(self):
        """Report experiment status"""

        print
        print "Output directory:\n{}".format(self.expdir)
        print
        print "Imaging     : binsize = {}".format(self.image_binsize)
        print "              exposure = {}".format(self.image_exposure)
        print "              magnification = {}".format(self.magnification)
        print "              spotsize = {}".format(self.image_spotsize)
        print "Diffraction : binsize = {}".format(self.diff_binsize)
        print "              exposure = {}".format(self.diff_exposure)
        print "              brightness = {}".format(self.diff_brightness)
        print "              spotsize = {}".format(self.diff_spotsize)

    def loop_centers(self):
        """Loop over holes in the copper grid
        Move the stage to all positions defined in centers

        Return
            di: dict, contains information on holes
        """
        ncenters = len(self.hole_centers)

        for i, (x, y) in enumerate(self.hole_centers):
            try:
                self.ctrl.stageposition.set(x=x, y=y)
            except ValueError as e:
                print e
                print " >> Moving to next center..."
                print
                continue
            else:
                self.log.info("Stage position: center %d/%d -> (x=%0.1f, y=%0.1f)", i, ncenters, x, y)
                yield i, (x,y)
            
    def loop_positions(self, delay=0.05):
        """Loop over positions in a hole in the copper grid
        Move the stage to each of the positions in self.offsets

        Return
            dct: dict, contains information on positions
        """
        noffsets = len(self.offsets)

        for i, hole_center in self.loop_centers():
            hole_x, hole_y = hole_center

            t = tqdm(self.offsets, desc="                           ")
            for j, (x_offset, y_offset) in enumerate(t):
                x = hole_x+x_offset
                y = hole_y+y_offset
                try:
                    self.ctrl.stageposition.set(x=x, y=y)
                except ValueError as e:
                    print e
                    print " >> Moving to next position..."
                    print
                    continue
                else:
                    time.sleep(delay)
                    self.log.debug("Imaging: stage position %s/%s -> (x=%.1f, y=%.1f)", j, noffsets, x, y)
                    t.set_description("Stage(x={:7.0f}, y={:7.0f})".format(x, y))

                    dct = {"exp_hole_number": i, "exp_image_number": j, "exp_hole_offset": (x_offset, y_offset), "exp_hole_center": (hole_x, hole_y)}
                    dct["ImageComment"] = "Hole {exp_hole_number} image {exp_image_number}\n".format(**dct)
                    yield dct


    def loop_crystals(self, crystal_coords, delay=0):
        """Loop over crystal coordinates (pixels)
        Switch to diffraction mode, and shift the beam to be on the crystal

        Return
            dct: dict, contains information on beam/diffshift

        """
        ncrystals = len(crystal_coords)
        if ncrystals == 0:
            raise StopIteration("No crystals found.")

        self.diffraction_mode()
        beamshift_coords = self.calib_beamshift.pixelcoord_to_beamshift(crystal_coords)

        t = tqdm(beamshift_coords, desc="                           ")

        for k, beamshift in enumerate(t):
            self.log.debug("Diffraction: crystal %d/%d", k+1, ncrystals)
            self.ctrl.beamshift.set(*beamshift)
        
            # compensate beamshift
            beamshift_offset = beamshift - self.neutral_beamshift
            pixelshift = self.calib_directbeam.beamshift2pixelshift(beamshift_offset)
        
            diffshift_offset = self.calib_directbeam.pixelshift2diffshift(pixelshift)
            diffshift = self.neutral_diffshift - diffshift_offset
        
            self.ctrl.diffshift.set(*diffshift.astype(int))

            t.set_description("BeamShift(x={:5.0f}, y={:5.0f})".format(*beamshift))
            time.sleep(delay)

            dct = {"exp_pattern_number": k, "exp_diffshift_offset": diffshift_offset, "exp_beamshift_offset": beamshift_offset, "exp_beamshift": beamshift, "exp_diffshift": diffshift}

            yield dct

    def apply_corrections(self, img, h):
        if self.flatfield is not None:
            img = remove_deadpixels(img, deadpixels=self.deadpixels)
            h["DeadPixelCorrection"] = True
            img = apply_flatfield_correction(img, flatfield=self.flatfield)
            h["FlatfieldCorrection"] = True
        return img, h

    def run(self, ctrl=None, **kwargs):
        """Run serial electron diffraction experiment"""

        self.initialize_microscope()

        header_keys = kwargs.get("header_keys", None)

        d_image = {
                "exp_neutral_diffshift": self.neutral_beamshift,
                "exp_neutral_beamshift": self.neutral_diffshift,
                "exp_image_spotsize": self.image_spotsize,
                "exp_magnification": self.magnification,
                "ImageDimensions": self.image_dimensions
        }
        d_diff = {
                "exp_neutral_diffshift": self.neutral_beamshift,
                "exp_neutral_beamshift": self.neutral_diffshift,
                "exp_diff_brightness": self.diff_brightness,
                "exp_diff_spotsize": self.diff_spotsize,
                "exp_diff_cameralength": self.diff_cameralength,
                "exp_diff_difffocus": self.diff_difffocus,
                "ImagePixelsize": self.diff_pixelsize
        }

        raw_input("\nPress <ENTER> to start experiment ('Ctrl-C' to interrupt)\n")

        for i, d_pos in enumerate(self.loop_positions()):
   
            outfile = os.path.join(self.imagedir, "image_{:04d}".format(i))
            
            if self.change_spotsize:
                self.ctrl.tem.setSpotSize(self.image_spotsize)
    
            img, h = self.ctrl.getImage(binsize=self.image_binsize, exposure=self.image_exposure, header_keys=header_keys)
    
            if self.change_spotsize:
                self.ctrl.tem.setSpotSize(self.image_spotsize)
    
            self.ctrl.tem.setSpotSize(self.diff_spotsize)

            im_mean = img.mean()
            if im_mean < self.image_threshold:
                self.log.debug("Dark image detected (mean=%f)", im_mean)
                continue

            img, h = self.apply_corrections(img, h)

            crystal_coords = self.find_crystals(img, self.magnification, spread=self.crystal_spread) * self.image_binsize
            
            for d in (d_image, d_pos):
                h.update(d)
            h["exp_crystal_coords"] = crystal_coords.tolist()

            write_hdf5(outfile, img, header=h)

            ncrystals = len(crystal_coords)
            if ncrystals == 0:
                continue

            self.log.info("%d crystals found", ncrystals)
    
            for k, d_cryst in enumerate(self.loop_crystals(crystal_coords)):
                outfile = os.path.join(self.datadir, "image_{:04d}_{:04d}".format(i, k))
                comment = "Image {} Crystal {}".format(i, k)
                img, h = self.ctrl.getImage(binsize=self.diff_binsize, exposure=self.diff_exposure, comment=comment, header_keys=header_keys)
                img, h = self.apply_corrections(img, h)

                for d in (d_diff, d_pos, d_cryst):
                    h.update(d)

                write_hdf5(outfile, img, header=h)
             
                if self.sample_rotation_angles:
                    for rotation_angle in self.sample_rotation_angles:
                        self.log.debug("Rotation angle = %f", rotation_angle)
                        self.ctrl.stageposition.a = rotation_angle
        
                        outfile = os.path.join(self.datadir, "image_{:04d}_{:04d}_{}".format(i, k, rotation_angle))
                        img, h = self.ctrl.getImage(binsize=self.diff_binsize, exposure=self.diff_exposure, comment=comment, header_keys=header_keys)
                        img, h = self.apply_corrections(img, h)
                                                    
                        for d in (d_diff, d_pos, d_cryst):
                            h.update(d)
    
                        write_hdf5(outfile, img, header=h)
                    
                    self.ctrl.stageposition.a = 0
    
            self.image_mode()

        print "\n\nData collection finished."


def main_gui():
    from gui import main
    main.start()


def main():
    import TEMController
    try:
        params = json.load(open("params.json","r"))
    except IOError:
        params = {}

    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename="instamatic.log", 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    ctrl = TEMController.initialize()

    exp = Experiment(ctrl, params, log=log)
    exp.report_status()
    exp.run()

    ctrl.close()


if __name__ == '__main__':
    main()
