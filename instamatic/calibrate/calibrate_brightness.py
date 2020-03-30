import logging
import pickle
import sys

import matplotlib.pyplot as plt
import numpy as np

from .filenames import *
from instamatic.image_utils import autoscale
from instamatic.processing.find_holes import find_holes
from instamatic.tools import find_beam_center
logger = logging.getLogger(__name__)


class CalibBrightness:
    """Brightness calibration routine."""

    def __init__(self, slope, intercept):
        self.slope = slope
        self.intercept = intercept
        self.has_data = False

    def __repr__(self):
        return f'CalibBrightness(slope={self.slope}, intercept={self.intercept})'

    def brightness_to_pixelsize(self, val):
        return self.slope * val + self.intercept

    def pixelsize_to_brightness(self, val):
        return int((val - self.intercept) / self.slope)

    @classmethod
    def from_data(cls, brightness, pixeldiameter, header=None):
        slope, intercept, r_value, p_value, std_err = linregress(brightness, pixeldiameter)
        print()
        print(f'r_value: {r_value:.4f}')
        print(f'p_value: {p_value:.4f}')

        c = cls(slope=slope, intercept=intercept)
        c.data_brightness = brightness
        c.data_pixeldiameter = pixeldiameter
        c.has_data = True
        c.header = header
        return c

    @classmethod
    def from_file(cls, fn=CALIB_BRIGHTNESS):
        import pickle
        try:
            return pickle.load(open(fn, 'rb'))
        except OSError as e:
            prog = 'instamatic.calibrate_brightness'
            raise OSError(f'{e.strerror}: {fn}. Please run {prog} first.')

    def to_file(self, fn=CALIB_BRIGHTNESS):
        pickle.dump(self, open(fn, 'wb'))

    def plot(self):
        if not self.has_data:
            pass

        mn = self.data_brightness.min()
        mx = self.data_brightness.max()
        extend = abs(mx - mn) * 0.1
        x = np.linspace(mn - extend, mx + extend)
        y = self.brightness_to_pixelsize(x)

        plt.plot(x, y, 'r-', label='linear regression')
        plt.scatter(self.data_brightness, self.data_pixeldiameter)
        plt.title('Fit brightness')
        plt.legend()
        plt.show()


def calibrate_brightness_live(ctrl, step=1000, save_images=False, **kwargs):
    """Calibrate pixel->brightness coordinates live on the microscope.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    start: `float`
        start value for calibration (0.0 - 1.0)
    end: `float`
        end value for calibration (0.0 - 1.0)
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of CalibBrightness class with conversion methods
    """

    raise NotImplementedError('calibrate_brightness_live function needs fixing...')

    exposure = kwargs.get('exposure', ctrl.cam.default_exposure)
    binsize = kwargs.get('binsize', ctrl.cam.default_binsize)

    values = []
    start = ctrl.brightness.value

    for i in range(10):
        target = start + i * step
        ctrl.brightness.value = int(target)

        outfile = f'calib_brightness_{i:04d}' if save_images else None

        comment = f'Calib image {i}: brightness={target}'
        img, h = ctrl.get_image(exposure=exposure, out=outfile, comment=comment, header_keys='Brightness')

        img, scale = autoscale(img)

        brightness = float(h['Brightness'])

        holes = find_holes(img, plot=False, verbose=False, max_eccentricity=0.8)

        if len(holes) == 0:
            print(' >> No holes found, continuing...')
            continue

        size = max(hole.equivalent_diameter for hole in holes) * binsize / scale

        print(f'Brightness: {brightness:.f}, equivalent diameter: {size:.1f}')
        values.append((brightness, size))

    values = np.array(values)
    c = CalibBrightness.from_data(*values.T)

    # Calling c.plot with videostream crashes program
    if not hasattr(ctrl.cam, 'VideoLoop'):
        c.plot()

    return c


def calibrate_brightness_from_image_fn(fns):
    """Calibrate pixel->brightness (size of beam) from a set of images.

    fns: `str`
        Set of images to determine size of beam from

    return:
        instance of Calibration class with conversion methods
    """

    values = []

    for fn in fns:
        print()
        print('Image:', fn)
        img, h = load_img(fn)
        brightness = float(h['Brightness'])
        binsize = float(h['ImageBinsize'])

        img, scale = autoscale(img)

        holes = find_holes(img, plot=False, fname=None, verbose=False, max_eccentricity=0.8)

        size = max(hole.equivalent_diameter for hole in holes) * binsize / scale

        print(f'Brightness: {brightness:.0f}, equivalent diameter: {size:.1f}px')
        values.append((brightness, size))

    values = np.array(values)
    c = CalibBrightness.from_data(*values.T)
    c.plot()

    return c


def calibrate_brightness(fns=None, ctrl=None, confirm=True):
    if not fns:
        if confirm and not input("\n >> Go too 2500x mag (type 'go' to start): "'') == 'go':
            return
        else:
            calib = calibrate_brightness_live(ctrl, save_images=True)
    else:
        calib = calibrate_brightness_from_image_fn(fns)

    logger.debug(calib)

    calib.to_file()


def main_entry():
    import argparse
    description = """Program to calibrate the brightness of the microscope (Deprecated)."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('args',
                        type=str, nargs='*', metavar='IMG',
                        help='Perform calibration using pre-collected images. If no arguments are given, run the live calibration routine.')

    options = parser.parse_args()
    args = options.args

    if not args:
        from instamatic import TEMController
        ctrl = TEMController.initialize()
        calibrate_brightness(ctrl, save_images=True)
    else:
        calibrate_brightness(args)


if __name__ == '__main__':
    main_entry()
