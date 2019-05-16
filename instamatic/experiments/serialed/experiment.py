import os, sys
import numpy as np
import json

import matplotlib.pyplot as plt

from instamatic.formats import *
from instamatic.processing.find_crystals import find_crystals, find_crystals_timepix
from instamatic.processing.flatfield import remove_deadpixels, apply_flatfield_correction
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam
from instamatic import config
from instamatic import neural_network

import time
import logging
from tqdm import tqdm
from pathlib import Path


def make_grid_on_stage(startpoint, endpoint, padding=2.0):
    """Divide the stage up in a grid, starting at 'startpoint' ending at 'endpoint'"""
    stepsize = np.array((0.016*512, 0.016*512))
    
    x1, y1 = pos1 = np.array((0, 0))
    x2, y2 = pos2 = np.array((1000, 1000))
    
    pos_delta = pos2 - pos1
    
    nx, ny = np.abs(pos_delta / (stepsize + padding)).astype(int)
    
    xgrid, ygrid = np.meshgrid(np.linspace(x1, x2, nx), np.linspace(y1, y2, ny))
    
    return np.stack((xgrid.flatten(), ygrid.flatten())).T


def get_gridpoints_in_circle(nx, ny=0, radius=1, borderwidth=0.8):
    """Make a grid (size=n*n), and return the coordinates of those
    fitting inside a circle (radius=r)
    nx: `int`
    ny: `int` (optional)
        Used to define a mesh nx*ny, if ny is missing, nx*nx is used
    radius: `float`
        radius of circle
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


def get_offsets_in_scan_area(box_x, box_y=0, radius=75, padding=2, k=1.0, angle=0, plot=False):
    """
    box_x: float or int,
        x-dimensions of the box in micrometers. 
        if box_y is missing, box_y = box_x
    box_y: float or int,
        y-dimension of the box in micrometers (optional)
    radius: int or float,
        radius of the scan_area in micrometer
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
       
    x_offsets, y_offsets = get_gridpoints_in_circle(nx=nx, ny=ny, radius=radius, borderwidth=borderwidth)
    
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
        
        print()
        print(textstr)
        
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
    def __init__(self, ctrl, params, scan_radius=None, begin_here=False, expdir=None, log=None):
        super(Experiment, self).__init__()
        self.ctrl = ctrl
        self.camera = ctrl.cam.name
        self.log = log

        self.scan_radius = scan_radius
        self.begin_here = begin_here

        self.setup_folders(expdir=expdir)

        self.load_calibration(**params)

        # set flags
        self.ctrl.tem.VERIFY_STAGE_POSITION = False

    def setup_folders(self, expdir=None, name="experiment"):
        if not expdir:
            n = 1
            while True:
                expdir = Path(f"{name}_{n}")
                if expdir.exists():
                    n += 1
                else:
                    break
        
        self.expdir = expdir
        self.calibdir = self.expdir / "calib"
        self.imagedir = self.expdir / "images"
        self.datadir = self.expdir / "data"

        for drc in self.expdir, self.calibdir, self.imagedir, self.datadir:
            drc.mkdir(exist_ok=True, parents=True)

        return self.expdir

    def load_calibration(self, **kwargs):
        """Load user specified config and calibration files"""
        
        self.ctrl.mode_mag1()
        self.ctrl.brightness.max()

        if (not self.begin_here) or (not self.scan_radius):
            print("\nSelect area to scan")
            print("-------------------")
        if not self.begin_here:
            input(" >> Move the stage to where you want to start and press <ENTER> to continue")
        x, y, _, _, _ = self.ctrl.stageposition.get()
        self.scan_centers = np.array([[x,y]])            
        if not self.scan_radius:
            self.scan_radius = float(input(" >> Enter the radius (micrometer) of the area to scan: [100] ") or 100)
        border_k = 0

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

        self.pixelsize_mag1 = config.calibration.pixelsize_mag1[self.magnification] / 1000  # nm -> um
        xdim, ydim = config.camera.dimensions
        self.image_dimensions = self.pixelsize_mag1 * xdim, self.pixelsize_mag1 * ydim
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

        self.diff_pixelsize  = config.calibration.pixelsize_diff[self.diff_cameralength]
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
    
        self.camera_rotation_angle = config.camera.camera_rotation_vs_stage_xy

        box_x, box_y = self.image_dimensions

        offsets = get_offsets_in_scan_area(box_x, box_y, self.scan_radius, k=border_k, padding=2, angle=self.camera_rotation_angle, plot=False)
        self.offsets = offsets * 1000

        # store kwargs to experiment drc
        kwargs["diff_brightness"]   = self.diff_brightness
        kwargs["diff_cameralength"] = self.diff_cameralength
        kwargs["diff_difffocus"]    = self.diff_difffocus
        kwargs["scan_radius"]       = self.scan_radius
        kwargs["scan_centers"]      = self.scan_centers.tolist()
        kwargs["stage_positions"]   = len(self.offsets)
        kwargs["image_dimensions"]  = self.image_dimensions

        self.log.info("params", kwargs)

        json.dump(kwargs, open(self.expdir / "params_out.json", "w"), indent=2)

    def initialize_microscope(self):
        """Intialize microscope"""

        import atexit
        atexit.register(self.ctrl.restore)

        self.ctrl.mode_diffraction()
        self.ctrl.brightness.set(self.diff_brightness)
        self.ctrl.difffocus.set(self.diff_difffocus)
        self.ctrl.tem.setSpotSize(self.diff_spotsize)
        input("\nPress <ENTER> to get neutral diffraction shift")
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
        
        # self.log.debug("Switching back to image mode")
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
        # self.log.debug("Switching to diffraction mode")
        time.sleep(delay)

        self.ctrl.brightness.set(self.diff_brightness)
        self.ctrl.mode_diffraction()
        self.ctrl.difffocus.value = self.diff_difffocus # difffocus must be set AFTER switching to diffraction mode

    def report_status(self):
        """Report experiment status"""

        print()
        print("Output directory:\n{}".format(self.expdir))
        print()
        print("Imaging     : binsize = {}".format(self.image_binsize))
        print("              exposure = {}".format(self.image_exposure))
        print("              magnification = {}".format(self.magnification))
        print("              spotsize = {}".format(self.image_spotsize))
        print("Diffraction : binsize = {}".format(self.diff_binsize))
        print("              exposure = {}".format(self.diff_exposure))
        print("              brightness = {}".format(self.diff_brightness))
        print("              spotsize = {}".format(self.diff_spotsize))

    def loop_centers(self):
        """Loop over scan centers defined
        Move the stage to all positions defined in centers

        Return
            di: dict, contains information on scan areas
        """
        ncenters = len(self.scan_centers)

        for i, (x, y) in enumerate(self.scan_centers):
            try:
                self.ctrl.stageposition.set(x=x, y=y)
            except ValueError as e:
                print(e)
                print(" >> Moving to next center...")
                print()
                continue
            else:
                self.log.info("Stage position: center %d/%d -> (x=%0.1f, y=%0.1f)", i, ncenters, x, y)
                yield i, (x,y)
            
    def loop_positions(self, delay=0.05):
        """Loop over positions defined
        Move the stage to each of the positions in self.offsets

        Return
            dct: dict, contains information on positions
        """
        noffsets = len(self.offsets)

        for i, scan_center in self.loop_centers():
            center_x, center_y = scan_center

            t = tqdm(self.offsets, desc="                           ")
            for j, (x_offset, y_offset) in enumerate(t):
                x = center_x + x_offset
                y = center_y + y_offset
                try:
                    self.ctrl.stageposition.set(x=x, y=y)
                except ValueError as e:
                    print(e)
                    print(" >> Moving to next position...")
                    print()
                    continue
                else:
                    time.sleep(delay)
                    # self.log.debug("Imaging: stage position %s/%s -> (x=%.1f, y=%.1f)", j, noffsets, x, y)
                    t.set_description(f"Stage(x={x:7.0f}, y={y:7.0f})")

                    dct = {"exp_scan_number": i, "exp_image_number": j, "exp_scan_offset": (x_offset, y_offset), "exp_scan_center": (center_x, center_y), "exp_stage_position": (x, y)}
                    dct["ImageComment"] = "scan {exp_scan_number} image {exp_image_number}".format(**dct)
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
            # self.log.debug("Diffraction: crystal %d/%d", k+1, ncrystals)
            self.ctrl.beamshift.set(*beamshift)
        
            # compensate beamshift
            beamshift_offset = beamshift - self.neutral_beamshift
            pixelshift = self.calib_directbeam.beamshift2pixelshift(beamshift_offset)
        
            diffshift_offset = self.calib_directbeam.pixelshift2diffshift(pixelshift)
            diffshift = self.neutral_diffshift - diffshift_offset
        
            self.ctrl.diffshift.set(*diffshift.astype(int))

            t.set_description("BeamShift(x={:5.0f}, y={:5.0f})".format(*beamshift))
            time.sleep(delay)

            dct = {"exp_pattern_number": k, 
                   "exp_diffshift_offset": diffshift_offset, 
                   "exp_beamshift_offset": beamshift_offset, 
                   "exp_beamshift": beamshift, 
                   "exp_diffshift": diffshift}

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

        self.log.info("d_image", d_image)
        self.log.info("d_tiff", d_diff)

        input("\nPress <ENTER> to start experiment ('Ctrl-C' to interrupt)\n")

        for i, d_pos in enumerate(self.loop_positions()):
   
            outfile = self.imagedir / f"image_{i:04d}"
            
            if self.change_spotsize:
                self.ctrl.tem.setSpotSize(self.image_spotsize)
    
            img, h = self.ctrl.getImage(exposure=self.image_exposure, binsize=self.image_binsize, header_keys=header_keys)
    
            if self.change_spotsize:
                self.ctrl.tem.setSpotSize(self.image_spotsize)
    
            self.ctrl.tem.setSpotSize(self.diff_spotsize)

            im_mean = img.mean()
            if im_mean < self.image_threshold:
                # self.log.debug("Dark image detected (mean=%f)", im_mean)
                continue

            img, h = self.apply_corrections(img, h)

            crystal_positions = self.find_crystals(img, self.magnification, spread=self.crystal_spread) * self.image_binsize
            crystal_coords = [(crystal.x, crystal.y) for crystal in crystal_positions]

            for d in (d_image, d_pos):
                h.update(d)
            h["exp_crystal_coords"] = crystal_coords

            write_hdf5(outfile, img, header=h)

            ncrystals = len(crystal_coords)
            if ncrystals == 0:
                continue

            self.log.info("%d crystals found in %s", ncrystals, outfile)
    
            for k, d_cryst in enumerate(self.loop_crystals(crystal_coords)):
                outfile = self.datadir / f"image_{i:04d}_{k:04d}"
                comment = "Image {} Crystal {}".format(i, k)
                img, h = self.ctrl.getImage(binsize=self.diff_binsize, exposure=self.diff_exposure, comment=comment, header_keys=header_keys)
                img, h = self.apply_corrections(img, h)

                for d in (d_diff, d_pos, d_cryst):
                    h.update(d)

                h["crystal_is_isolated"]   = crystal_positions[k].isolated
                h["crystal_clusters"]      = crystal_positions[k].n_clusters
                h["total_area_micrometer"] = crystal_positions[k].area_micrometer
                h["total_area_pixel"]      = crystal_positions[k].area_pixel

                # img_processed = neural_network.preprocess(img.astype(np.float))
                # quality = neural_network.predict(img_processed)
                # h["crystal_quality"] = quality

                write_hdf5(outfile, img, header=h)
             
                if self.sample_rotation_angles:
                    for rotation_angle in self.sample_rotation_angles:
                        self.log.debug("Rotation angle = %f", rotation_angle)
                        self.ctrl.stageposition.a = rotation_angle
        
                        outfile = self.datadir / f"image_{i:04d}_{k:04d}_{rotation_angle}"
                        img, h = self.ctrl.getImage(exposure=self.diff_exposure, binsize=self.diff_binsize, comment=comment, header_keys=header_keys)
                        img, h = self.apply_corrections(img, h)
                                                    
                        for d in (d_diff, d_pos, d_cryst):
                            h.update(d)
    
                        write_hdf5(outfile, img, header=h)
                    
                    self.ctrl.stageposition.a = 0
    
            self.image_mode()

        print("\n\nData collection finished.")


def main_gui():
    from gui import main
    main.start()


def main():
    from instamatic import TEMController
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
