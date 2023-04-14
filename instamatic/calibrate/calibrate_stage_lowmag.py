import logging
import pickle
import sys

import matplotlib.pyplot as plt
import numpy as np
from skimage.registration import phase_cross_correlation

from instamatic.formats import read_image
from instamatic.image_utils import autoscale, imgscale

from .filenames import *
from .fit import fit_affine_transformation

logger = logging.getLogger(__name__)


class CalibStage:
    """Simple class to hold the methods to perform transformations from one
    setting to another based on calibration results."""

    def __init__(self, rotation, camera_dimensions, translation=np.array([0, 0]), reference_position=np.array([0, 0])):
        super().__init__()
        self.has_data = False
        self.rotation = rotation
        self.translation = translation
        self.reference_position = reference_position
        self.center_pixel = np.array(camera_dimensions) / 2.0

    def __repr__(self):
        return f'CalibStage(rotation=\n{self.rotation},\n translation=\n{self.translation},\n reference_position=\n{self.reference_position})'

    def _reference_setting_to_pixelcoord(self, px_ref, image_pos, r, t, reference_pos):
        """Function to transform stage position to pixel coordinates.

        px_ref: `list`
            stage position (x,y) to transform to pixel coordinates on
            current image
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)
        px_ref = np.array(px_ref)

        # do the inverse transoformation here
        r_i = np.linalg.inv(r)

        # get stagepos vector from reference image (center) to current image
        vect = image_pos - reference_pos

        # px_ref -> pixel coords, and add offset for pixel position
        px = px_ref - np.dot(vect - t, r_i)

        return px

    def _pixelcoord_to_reference_setting(self, px, image_pos, r, t, reference_pos):
        """Function to transform pixel coordinates to pixel coordinates in
        reference setting.

        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)
        px = np.array(px)

        # do the inverse transoformation here
        r_i = np.linalg.inv(r)

        # get stagepos vector from reference image (center) to current image
        vect = image_pos - reference_pos

        # stagepos -> pixel coords, and add offset for pixel position
        px_ref = np.dot(vect - t, r_i) + np.array(px)

        return px_ref

    def _pixelcoord_to_stagepos(self, px, image_pos, r, t, reference_pos):
        """Function to transform pixel coordinates to stage position.

        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        reference_pos = np.array(reference_pos)

        px_ref = self._pixelcoord_to_reference_setting(px, image_pos, r, t, reference_pos)

        stagepos = np.dot(px_ref - self.center_pixel, r) + t + reference_pos

        return stagepos

    def _stagepos_to_pixelcoord(self, stagepos, image_pos, r, t, reference_pos):
        """Function to transform pixel coordinates to stage position.

        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        stagepos = np.array(stagepos)
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)

        # do the inverse transoformation here
        r_i = np.linalg.inv(r)

        px_ref = np.dot(stagepos - t - reference_pos, r_i) + self.center_pixel

        px = self._reference_setting_to_pixelcoord(px_ref, image_pos, r, t, reference_pos)

        return px

    def reference_setting_to_pixelcoord(self, px_ref, image_pos):
        """Function to transform pixel coordinates in reference setting to
        current frame."""
        return self._reference_setting_to_pixelcoord(px_ref, image_pos, self.rotation, self.translation, self.reference_position)

    def pixelcoord_to_reference_setting(self, px, image_pos):
        """Function to transform pixel coordinates in current frame to
        reference setting."""
        return self._pixelcoord_to_reference_setting(px, image_pos, self.rotation, self.translation, self.reference_position)

    def pixelcoord_to_stagepos(self, px, image_pos):
        """Function to transform pixel coordinates to stage position
        coordinates."""
        return self._pixelcoord_to_stagepos(px, image_pos, self.rotation, self.translation, self.reference_position)

    def stagepos_to_pixelcoord(self, stagepos, image_pos):
        """Function to stage position coordinates to pixel coordinates on
        current frame."""
        return self._stagepos_to_pixelcoord(stagepos, image_pos, self.rotation, self.translation, self.reference_position)

    def pixelshift_to_stageshift(self, pixelshift, binsize=1):
        """Convert from a pixel distance to a stage shift."""
        dx, dy = pixelshift
        dx = (dx * binsize) + self.center_pixel[0]
        dy = (dy * binsize) + self.center_pixel[1]
        return self.pixelcoord_to_stagepos((dx, dy), image_pos=(0, 0))

    @classmethod
    def from_data(cls, shifts, stagepos, reference_position, camera_dimensions=None, header=None):
        fit_result = fit_affine_transformation(shifts, stagepos, verbose=True, translation=True)
        r = fit_result.r
        t = fit_result.t

        if not camera_dimensions:
            if header:
                camera_dimensions = header['ImageCameraDimensions']
            else:
                raise NameError("name 'camera_dimensions' is not defined.")

        c = cls(rotation=r, camera_dimensions=camera_dimensions, translation=t, reference_position=reference_position)
        c.data_shifts = shifts
        c.data_stagepos = stagepos
        c.has_data = True
        c.header = header

        return c

    @classmethod
    def from_file(cls, fn=CALIB_STAGE_LOWMAG):
        try:
            return pickle.load(open(fn, 'rb'))
        except OSError as e:
            prog = 'instamatic.calibrate_stage_lowmag/mag1'
            raise OSError(f'{e.strerror}: {fn}. Please run {prog} first.')

    def to_file(self, fn=CALIB_STAGE_LOWMAG):
        pickle.dump(self, open(fn, 'wb'))

    def plot(self):
        if not self.has_data:
            return

        stagepos = self.data_stagepos
        shifts = self.data_shifts

        r_i = np.linalg.inv(self.rotation)

        stagepos_ = np.dot(stagepos - self.translation, r_i)

        plt.scatter(*shifts.T, label='Observed pixel shifts')
        plt.scatter(*stagepos_.T, label='Positions in pixel coords')

        for i, (x, y) in enumerate(shifts):
            plt.text(x + 5, y + 5, str(i), size=14)

        plt.legend()
        plt.show()


def calibrate_stage_lowmag_live(ctrl, gridsize=5, stepsize=50000, save_images=False, **kwargs):
    """Calibrate pixel->stageposition coordinates live on the microscope.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """
    exposure = kwargs.get('exposure', ctrl.cam.default_exposure)
    binsize = kwargs.get('binsize', ctrl.cam.default_binsize)

    outfile = 'calib_start' if save_images else None

    # Accurate reading fo the center positions is needed so that we can come back to it,
    #  because this will be our anchor point
    img_cent, h_cent = ctrl.get_image(exposure=exposure, binsize=binsize, out=outfile, comment='Center image (start)')

    x_cent, y_cent, _, _, _ = h_cent['StagePosition']
    xy_cent = np.array([x_cent, y_cent])

    img_cent, scale = autoscale(img_cent)

    stagepos = []
    shifts = []

    n = int((gridsize - 1) / 2)  # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n + 1) * stepsize, np.arange(-n, n + 1) * stepsize)
    tot = gridsize * gridsize

    i = 0
    for dx, dy in np.stack([x_grid, y_grid]).reshape(2, -1).T:
        print()
        print(f'Position {i+1}/{tot}: x: {x_cent+dx:.0f}, y: {y_cent+dy:.0f}')

        ctrl.stage.set(x=x_cent + dx, y=y_cent + dy)
        print(ctrl.stage)

        outfile = f'calib_{i:04d}' if save_images else None

        comment = comment
        img, h = ctrl.get_image(exposure=exposure, binsize=binsize, out=outfile, comment=comment, header_keys='StagePosition')

        img = imgscale(img, scale)

        shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)

        xobs, yobs, _, _, _ = h['StagePosition']
        stagepos.append((xobs, yobs))
        shifts.append(shift)

        i += 1

    print(' >> Reset to center')
    ctrl.stage.set(x=x_cent, y=y_cent)
    ctrl.stage.reset_xy()

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))

    m = gridsize**2 // 2
    if gridsize % 2 and stagepos[m].max() > 50:
        print(f' >> Warning: Large difference between image {m}, and center image. These should be close for a good calibration.')
        print('    Difference:', stagepos[m])
        print()

    if save_images:
        ctrl.get_image(exposure=exposure, binsize=binsize, out='calib_end', comment='Center image (end)')

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent, header=h_cent)

    # Calling c.plot with videostream crashes program
    if not hasattr(ctrl.cam, 'VideoLoop'):
        c.plot(key)

    return c


def calibrate_stage_lowmag_from_image_fn(center_fn, other_fn):
    """Calibrate pixel->stageposition coordinates from a set of images.

    center_fn: `str`
        Reference image at the center of the grid (with the clover in the middle)
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    img_cent, h_cent = read_image(center_fn)

    img_cent, scale = autoscale(img_cent, maxdim=512)

    x_cent, y_cent, _, _, _ = h_cent['StagePosition']
    xy_cent = np.array([x_cent, y_cent])
    print('Center:', center_fn)
    print('Stageposition: x={:.0f} | y={:.0f}'.format(*xy_cent))
    print()

    binsize = h_cent['ImageBinsize']

    shifts = []
    stagepos = []

    for fn in other_fn:
        img, h = read_image(fn)

        img = imgscale(img, scale)

        xobs, yobs, _, _, _ = h['StagePosition']
        print('Image:', fn)
        print(f'Stageposition: x={xobs:.0f} | y={yobs:.0f}')
        print()

        shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)

        stagepos.append((xobs, yobs))
        shifts.append(shift)

    # correct for binsize, store as binsize=1
    shifts = np.array(shifts) * binsize / scale
    stagepos = np.array(stagepos) - xy_cent

    c = CalibStage.from_data(shifts, stagepos, reference_position=xy_cent, header=h_cent)
    c.plot()

    return c


def calibrate_stage_lowmag(center_fn=None, other_fn=None, ctrl=None, confirm=True, save_images=False):
    if not (center_fn or other_fn):
        if confirm and not input("\n >> Go to 100x mag, and move the sample stage\nso that the grid center (clover) is in the\nmiddle of the image (type 'go'): "'') == 'go':
            return
        else:
            calib = calibrate_stage_lowmag_live(ctrl, save_images=True)
    else:
        calib = calibrate_stage_lowmag_from_image_fn(center_fn, other_fn)

    logger.debug(calib)

    calib.to_file()


def main_entry():
    import argparse
    description = """Program to calibrate the lowmag mode (100x) of the microscope (Deprecated)."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('args',
                        type=str, nargs='*', metavar='IMG',
                        help='Perform calibration using pre-collected images. The first image must be the center image used as the reference position. The other images are cross-correlated to this image to calibrate the translations. If no arguments are given, run the live calibration routine.')

    options = parser.parse_args()
    args = options.args

    if not args:
        from instamatic import TEMController
        ctrl = TEMController.initialize()
        calibrate_stage_lowmag(ctrl=ctrl, save_images=True)
    else:
        center_fn = args[0]
        other_fn = args[1:]
        calibrate_stage_lowmag(center_fn, other_fn)


if __name__ == '__main__':
    main_entry()
