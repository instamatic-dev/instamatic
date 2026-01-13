from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import yaml
from skimage.registration import phase_cross_correlation
from tqdm import tqdm
from typing_extensions import Self

from instamatic import config
from instamatic._typing import AnyPath
from instamatic.calibrate.filenames import *
from instamatic.calibrate.fit import fit_affine_transformation
from instamatic.formats import read_tiff
from instamatic.image_utils import autoscale, imgscale
from instamatic.processing.find_holes import find_holes
from instamatic.tools import find_beam_center
from instamatic.utils.yaml import Numpy2DDumper

if TYPE_CHECKING:
    from instamatic.gui.videostream_processor import DeferredImageDraw, VideoStreamProcessor


logger = logging.getLogger(__name__)


Vector2 = np.ndarray  # numpy array with two float (or int) elements
VectorNx2 = np.ndarray  # numpy array with N Vector2-s
Matrix2x2 = np.ndarray  # numpy array of shape (2, 2) with float elements


@dataclass
class CalibBeamShift:
    """Simple class to hold the methods to perform transformations from one
    setting to another based on calibration results.

    Throughout this class, the following two terms are used consistently:
    - pixel: the (x, y) beam position in pixels as determined from camera image
    - shift: the unitless (x, y) value pair reported by the BeamShift deflector
    """

    transform: Matrix2x2
    reference_pixel: Vector2
    reference_shift: Vector2
    pixels: Optional[VectorNx2] = field(default=None, repr=False)
    shifts: Optional[VectorNx2] = field(default=None, repr=False)
    images: Optional[list[np.ndarray]] = field(default=None, repr=False)

    def __repr__(self):
        return f'CalibBeamShift(transform=\n{self.transform},\n   reference_shift=\n{self.reference_shift},\n   reference_pixel=\n{self.reference_pixel})'

    def beamshift_to_pixelcoord(self, beamshift: Sequence[float]) -> Vector2:
        """Converts from beamshift x,y to pixel coordinates."""
        r_i = np.linalg.inv(self.transform)
        return np.dot(self.reference_shift - np.array(beamshift), r_i) + self.reference_pixel

    def pixelcoord_to_beamshift(self, pixelcoord: Sequence[float]) -> Vector2:
        """Converts from pixel coordinates to beamshift x,y."""
        pc = np.array(pixelcoord)
        return self.reference_shift - np.dot(pc - self.reference_pixel, self.transform)

    @classmethod
    def from_data(
        cls,
        pixels: VectorNx2,
        shifts: VectorNx2,
        reference_pixel: Vector2,
        reference_shift: Vector2,
        images: Optional[list[np.ndarray]] = None,
    ) -> Self:
        return cls(
            transform=fit_affine_transformation(pixels, shifts).r,
            reference_pixel=reference_pixel,
            reference_shift=reference_shift,
            pixels=pixels,
            shifts=shifts,
            images=images,
        )

    @classmethod
    def from_file(cls, fn: AnyPath = CALIB_BEAMSHIFT) -> Self:
        """Read calibration from file."""
        try:
            with open(Path(fn), 'r') as yaml_file:
                return cls(**{k: np.array(v) for k, v in yaml.safe_load(yaml_file).items()})
        except OSError as e:
            prog = 'instamatic.calibrate_beamshift'
            raise OSError(f'{e.strerror}: {fn}. Please run {prog} first.')

    @classmethod
    def live(
        cls, ctrl, outdir: AnyPath = '.', vsp: Optional[VideoStreamProcessor] = None
    ) -> Self:
        while True:
            c = calibrate_beamshift(ctrl=ctrl, save_images=True, outdir=outdir)
            binsize = ctrl.cam.default_binsize
            with c.annotate_videostream(vsp, binsize) if vsp else nullcontext():
                if input(' >> Accept? [y/n] ') == 'y':
                    return c

    def to_file(self, fn: AnyPath = CALIB_BEAMSHIFT, outdir: AnyPath = '.') -> None:
        """Save calibration to file."""
        yaml_path = Path(outdir) / fn
        yaml_dict = asdict(self)  # type: ignore[arg-type]
        yaml_dict = {k: v.tolist() for k, v in yaml_dict.items() if k != 'images'}
        with open(yaml_path, 'w') as yaml_file:
            yaml.dump(yaml_dict, yaml_file, Dumper=Numpy2DDumper, default_flow_style=None)

    def plot(self, to_file: Optional[AnyPath] = None):
        """Assuming the data is present, plot the data."""
        shifts = np.dot(self.shifts, np.linalg.inv(self.transform))
        plt.scatter(*self.pixels.T, marker='>', label='Observed pixel shifts')
        plt.scatter(*shifts.T, marker='<', label='Reconstructed pixel shifts')
        plt.legend()
        plt.title('BeamShift vs. Direct beam position (Imaging)')
        if to_file:
            plt.savefig(Path(to_file) / 'calib_beamshift.png')
            plt.close()
        else:
            plt.show()

    @contextmanager
    def annotate_videostream(self, vsp: VideoStreamProcessor, binsize: int = 1) -> None:
        shifts = np.dot(self.shifts, np.linalg.inv(self.transform))
        ins: list[DeferredImageDraw.Instruction] = []

        vsp.temporary_frame = np.max(self.images, axis=0)
        print('Determined (blue) vs calibrated (orange) beam positions:')
        for p, s in zip(self.pixels, shifts):
            p = (p + self.reference_pixel)[::-1] / binsize  # xy coords inverted for plot
            s = (s + self.reference_pixel)[::-1] / binsize  # xy coords inverted for plot
            ins.append(vsp.draw.circle(p, radius=3, fill='blue'))
            ins.append(vsp.draw.circle(s, radius=3, fill='orange'))
        ins.append(vsp.draw.circle(self.reference_pixel[::-1], radius=3, fill='black'))
        yield
        vsp.temporary_frame = None
        for i in ins:
            vsp.draw.instructions.remove(i)

    def center(self, ctrl) -> Optional[np.ndarray]:
        """Return beamshift values to center the beam in the frame."""
        pixel_center = [val / 2.0 for val in ctrl.cam.get_image_dimensions()]

        beamshift = self.pixelcoord_to_beamshift(pixel_center)
        if ctrl:
            ctrl.beamshift.set(*(float(b) for b in beamshift))
        else:
            return beamshift


def calibrate_beamshift_live(
    ctrl,
    gridsize: Optional[int] = None,
    stepsize: Optional[float] = None,
    save_images: bool = False,
    outdir: AnyPath = '.',
    **kwargs,
) -> CalibBeamShift:
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
    gridsize = gridsize or config.camera.calib_beamshift.get('gridsize', 5)
    stepsize = stepsize or config.camera.calib_beamshift.get('stepsize', 250)
    outfile = Path(outdir) / 'calib_beamshift_center' if save_images else None
    kwargs = {'exposure': exposure, 'binsize': binsize, 'out': outfile}

    comment = 'Beam in the center of the image'
    img_cent, h_cent = ctrl.get_image(comment=comment, **kwargs)
    x_cent, y_cent = beamshift_cent = np.array(h_cent['BeamShift'])

    stepsize = 2500.0 / h_cent['Magnification'] * stepsize

    print(f'Gridsize: {gridsize} | Stepsize: {stepsize:.2f}')

    img_cent, scale = autoscale(img_cent)
    pixel_cent = find_beam_center(img_cent) * binsize / scale

    print('Beamshift: x={} | y={}'.format(*beamshift_cent))
    print('Pixel: x={} | y={}'.format(*pixel_cent))

    images, pixels, shifts = [], [], []
    dx_dy = ((np.indices((gridsize, gridsize)) - gridsize // 2) * stepsize).reshape(2, -1).T

    progress_bar = tqdm(dx_dy, desc='Beamshift calibration')
    for i, (dx, dy) in enumerate(progress_bar):
        ctrl.beamshift.set(x=float(x_cent + dx), y=float(y_cent + dy))
        progress_bar.set_postfix_str(ctrl.beamshift)
        time.sleep(config.camera.calib_beamshift.get('delay', 0.0))

        kwargs['out'] = Path(outdir) / f'calib_beamshift_{i:04d}' if save_images else None
        comment = f'Calib image {i}: dx={dx} - dy={dy}'
        img, h = ctrl.get_image(comment=comment, header_keys=('BeamShift',), **kwargs)
        img = imgscale(img, scale)

        images.append(img)
        pixels.append(phase_cross_correlation(img_cent, img, upsample_factor=10)[0])
        shifts.append(np.array(h['BeamShift']))

    print('')
    ctrl.beamshift.set(*(float(_) for _ in beamshift_cent))

    # normalize to binsize = 1 and 512-pixel image scale before initializing
    c = CalibBeamShift.from_data(
        np.array(pixels) * binsize / scale,
        np.array(shifts) - beamshift_cent,
        reference_pixel=pixel_cent,
        reference_shift=beamshift_cent,
        images=images,
    )
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

    img_cent, h_cent = read_tiff(center_fn)
    beamshift_cent = np.array(h_cent['BeamShift'])

    img_cent, scale = autoscale(img_cent, maxdim=512)

    binsize = h_cent['ImageBinsize']

    holes = find_holes(img_cent, plot=False, verbose=False, max_eccentricity=0.8)
    pixel_cent = np.array(holes[0].centroid) * binsize / scale

    print('Beamshift: x={} | y={}'.format(*beamshift_cent))
    print('Pixel: x={:.2f} | y={:.2f}'.format(*pixel_cent))

    images = []
    shifts = []
    beampos = []

    for fn in other_fn:
        img, h = read_tiff(fn)
        img = imgscale(img, scale)

        beamshift = np.array(h['BeamShift'])
        print()
        print('Image:', fn)
        print('Beamshift: x={} | y={}'.format(*beamshift))

        shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)

        images.append(img)
        beampos.append(beamshift)
        shifts.append(shift)

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    beampos = np.array(beampos) - beamshift_cent

    c = CalibBeamShift.from_data(
        shifts,
        beampos,
        reference_pixel=pixel_cent,
        reference_shift=beamshift_cent,
        images=images,
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
