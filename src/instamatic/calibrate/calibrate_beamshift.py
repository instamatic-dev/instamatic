from __future__ import annotations

import logging
import os
import pickle
import sys

import matplotlib.pyplot as plt
import numpy as np
from skimage.registration import phase_cross_correlation

from instamatic import config
from instamatic.image_utils import autoscale, imgscale
from instamatic.processing.find_holes import find_holes
from instamatic.tools import find_beam_center, printer

from .filenames import *
from .fit import fit_affine_transformation

logger = logging.getLogger(__name__)


class CalibBeamShift:
    """Simple class to hold the methods to perform transformations from one
    setting to another based on calibration results."""

    def __init__(self, transform, reference_shift, reference_pixel):
        super().__init__()
        self.transform = transform
        self.reference_shift = reference_shift
        self.reference_pixel = reference_pixel
        self.has_data = False

    def __repr__(self):
        return f'CalibBeamShift(transform=\n{self.transform},\n   reference_shift=\n{self.reference_shift},\n   reference_pixel=\n{self.reference_pixel})'

    def beamshift_to_pixelcoord(self, beamshift):
        """Converts from beamshift x,y to pixel coordinates."""
        r_i = np.linalg.inv(self.transform)
        pixelcoord = np.dot(self.reference_shift - beamshift, r_i) + self.reference_pixel
        return pixelcoord

    def pixelcoord_to_beamshift(self, pixelcoord):
        """Converts from pixel coordinates to beamshift x,y."""
        r = self.transform
        beamshift = self.reference_shift - np.dot(pixelcoord - self.reference_pixel, r)
        return beamshift.astype(int)

    @classmethod
    def from_data(cls, shifts, beampos, reference_shift, reference_pixel, header=None):
        fit_result = fit_affine_transformation(shifts, beampos)
        r = fit_result.r
        t = fit_result.t

        c = cls(transform=r, reference_shift=reference_shift, reference_pixel=reference_pixel)
        c.data_shifts = shifts
        c.data_beampos = beampos
        c.has_data = True
        c.header = header

        return c

    @classmethod
    def from_file(cls, fn=CALIB_BEAMSHIFT):
        """Read calibration from file."""
        import pickle

        try:
            return pickle.load(open(fn, 'rb'))
        except OSError as e:
            prog = 'instamatic.calibrate_beamshift'
            raise OSError(f'{e.strerror}: {fn}. Please run {prog} first.')

    @classmethod
    def live(cls, ctrl, outdir='.'):
        while True:
            c = calibrate_beamshift(ctrl=ctrl, save_images=True, outdir=outdir)
            if input(' >> Accept? [y/n] ') == 'y':
                return c

    def to_file(self, fn=CALIB_BEAMSHIFT, outdir='.'):
        """Save calibration to file."""
        fout = os.path.join(outdir, fn)
        pickle.dump(self, open(fout, 'wb'))

    def plot(self, to_file=None, outdir=''):
        if not self.has_data:
            return

        if to_file:
            to_file = f'calib_{beamshift}.png'

        beampos = self.data_beampos
        shifts = self.data_shifts

        r_i = np.linalg.inv(self.transform)
        beampos_ = np.dot(beampos, r_i)

        plt.scatter(*shifts.T, marker='>', label='Observed pixel shifts')
        plt.scatter(*beampos_.T, marker='<', label='Positions in pixel coords')
        plt.legend()
        plt.title('BeamShift vs. Direct beam position (Imaging)')
        if to_file:
            plt.savefig(os.path.join(outdir, to_file))
            plt.close()
        else:
            plt.show()

    def center(self, ctrl):
        """Return beamshift values to center the beam in the frame."""
        pixel_center = [val / 2.0 for val in ctrl.cam.get_camera_dimensions()]

        beamshift = self.pixelcoord_to_beamshift(pixel_center)
        if ctrl:
            ctrl.beamshift.set(*beamshift)
        else:
            return beamshift


def calibrate_beamshift_live(
    ctrl, gridsize=None, stepsize=None, save_images=False, outdir='.', **kwargs
):
    """Calibrate pixel->beamshift coordinates live on the microscope.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int` or None
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float` or None
        Size of steps for beamshift along x and y
        Defined at a magnification of 2500, scales stepsize down for other mags.
    exposure: `float` or None
        exposure time
    binsize: `int` or None

    In case paramers are not defined, camera specific default parameters are retrieved

    return:
        instance of Calibration class with conversion methods
    """
    exposure = kwargs.get('exposure', ctrl.cam.default_exposure)
    binsize = kwargs.get('binsize', ctrl.cam.default_binsize)

    if not gridsize:
        gridsize = config.camera.calib_beamshift.get('gridsize', 5)
    if not stepsize:
        stepsize = config.camera.calib_beamshift.get('stepsize', 250)

    img_cent, h_cent = ctrl.get_image(
        exposure=exposure, binsize=binsize, comment='Beam in center of image'
    )
    x_cent, y_cent = beamshift_cent = np.array(h_cent['BeamShift'])

    magnification = h_cent['Magnification']
    stepsize = 2500.0 / magnification * stepsize

    print(f'Gridsize: {gridsize} | Stepsize: {stepsize:.2f}')

    img_cent, scale = autoscale(img_cent)

    outfile = os.path.join(outdir, 'calib_beamcenter') if save_images else None

    pixel_cent = find_beam_center(img_cent) * binsize / scale

    print('Beamshift: x={} | y={}'.format(*beamshift_cent))
    print('Pixel: x={} | y={}'.format(*pixel_cent))

    shifts = []
    beampos = []

    n = int((gridsize - 1) / 2)  # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(
        np.arange(-n, n + 1) * stepsize, np.arange(-n, n + 1) * stepsize
    )
    tot = gridsize * gridsize

    i = 0
    for dx, dy in np.stack([x_grid, y_grid]).reshape(2, -1).T:
        ctrl.beamshift.set(x=x_cent + dx, y=y_cent + dy)

        printer(f'Position: {i + 1}/{tot}: {ctrl.beamshift}')

        outfile = os.path.join(outdir, 'calib_beamshift_{i:04d}') if save_images else None

        comment = f'Calib image {i}: dx={dx} - dy={dy}'
        img, h = ctrl.get_image(
            exposure=exposure,
            binsize=binsize,
            out=outfile,
            comment=comment,
            header_keys='BeamShift',
        )
        img = imgscale(img, scale)

        shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)

        beamshift = np.array(h['BeamShift'])
        beampos.append(beamshift)
        shifts.append(shift)

        i += 1

    print('')
    # print "\nReset to center"

    ctrl.beamshift.set(*beamshift_cent)

    # correct for binsize, store in binsize=1
    shifts = np.array(shifts) * binsize / scale
    beampos = np.array(beampos) - np.array(beamshift_cent)

    c = CalibBeamShift.from_data(
        shifts,
        beampos,
        reference_shift=beamshift_cent,
        reference_pixel=pixel_cent,
        header=h_cent,
    )

    # Calling c.plot with videostream crashes program
    # if not hasattr(ctrl.cam, "VideoLoop"):
    #     c.plot()

    return c


def calibrate_beamshift_from_image_fn(center_fn, other_fn):
    """Calibrate pixel->beamshift coordinates from a set of images.

    center_fn: `str`
        Reference image with the beam at the center of the image
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    print()
    print('Center:', center_fn)

    img_cent, h_cent = load_img(center_fn)
    beamshift_cent = np.array(h_cent['BeamShift'])

    img_cent, scale = autoscale(img_cent, maxdim=512)

    binsize = h_cent['ImageBinsize']

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale

    print('Beamshift: x={} | y={}'.format(*beamshift_cent))
    print('Pixel: x={:.2f} | y={:.2f}'.format(*pixel_cent))

    shifts = []
    beampos = []

    for fn in other_fn:
        img, h = load_img(fn)
        img = imgscale(img, scale)

        beamshift = np.array(h['BeamShift'])
        print()
        print('Image:', fn)
        print('Beamshift: x={} | y={}'.format(*beamshift))

        shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)

        beampos.append(beamshift)
        shifts.append(shift)

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    beampos = np.array(beampos) - beamshift_cent

    c = CalibBeamShift.from_data(
        shifts,
        beampos,
        reference_shift=beamshift_cent,
        reference_pixel=pixel_cent,
        header=h_cent,
    )
    c.plot()

    return c


def calibrate_beamshift(
    center_fn=None, other_fn=None, ctrl=None, save_images=True, outdir='.', confirm=True
):
    if not (center_fn or other_fn):
        if confirm:
            ctrl.store('calib_beamshift')
            while True:
                inp = input("""
Calibrate beamshift
-------------------
 1. Go to desired magnification (e.g. 2500x)
 2. Select desired beam size (BRIGHTNESS)
 3. Center the beam with beamshift

 >> Press <ENTER> to start >> \n""")
                if inp == 'x':
                    ctrl.restore()
                    ctrl.close()
                    sys.exit()
                elif inp == 'r':
                    ctrl.restore('calib_beamshift')
                elif inp == 'go':
                    break
                elif not inp:
                    break
        calib = calibrate_beamshift_live(ctrl, save_images=save_images, outdir=outdir)
    else:
        calib = calibrate_beamshift_from_image_fn(center_fn, other_fn)

    logger.debug(calib)

    calib.to_file(outdir=outdir)
    # calib.plot(to_file=True, outdir=outdir)  # FIXME: this causes a freeze

    return calib


def main_entry():
    import argparse

    description = """Program to calibrate the beamshift of the microscope (Deprecated)."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'args',
        type=str,
        nargs='*',
        metavar='IMG',
        help='Perform calibration using pre-collected images. The first image must be the center image used as the reference position. The other images are cross-correlated to this image to calibrate the translations. If no arguments are given, run the live calibration routine.',
    )

    options = parser.parse_args()
    args = options.args

    if not args:
        from instamatic import controller

        ctrl = controller.initialize()
        calibrate_beamshift(ctrl=ctrl, save_images=True)
    else:
        center_fn = args[0]
        other_fn = args[1:]
        calibrate_beamshift(center_fn=center_fn, other_fn=other_fn)


if __name__ == '__main__':
    main_entry()
