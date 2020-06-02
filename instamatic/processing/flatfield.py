import glob
import os
import time
import warnings
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm

from instamatic import config
from instamatic import TEMController
from instamatic.formats import *


def apply_corrections(img, deadpixels=None):
    """Apply image corrections."""
    if deadpixels is None:
        deadpixels = get_deadpixels(img)
    img = remove_deadpixels(img, deadpixels)
    img = apply_center_pixel_correction(img)
    return img


def remove_deadpixels(img, deadpixels, d=1):
    """Remove dead pixels from the images by replacing them with the average of
    neighbouring pixels."""
    d = 1
    for (i, j) in deadpixels:
        neighbours = img[i - d:i + d + 1, j - d:j + d + 1].flatten()
        img[i, j] = np.mean(neighbours)
    return img


def get_deadpixels(img):
    """Get coordinates of dead pixels in the image."""
    return np.argwhere(img == 0)


def apply_center_pixel_correction(img, k=1.19870594245):
    """Correct the intensity of the center pixels."""
    img[255:261, 255:261] = img[255:261, 255:261] * k
    return img


def get_center_pixel_correction(img):
    """Get the correction factor for the center pixels."""
    center = np.sum(img[255:261, 255:261])
    edge = np.sum(img[254:262, 254:262]) - center

    avg1 = center / 36.0
    avg2 = edge / 28.0
    k = avg2 / avg1

    print('timepix central pixel correction factor:', k)
    return k


def apply_flatfield_correction(img, flatfield, darkfield=None):
    """Apply flatfield correction to image.

    https://en.wikipedia.org/wiki/Flat-field_correction
    """

    if flatfield.shape != img.shape:
        msg = f'Flatfield not applied: image {img.shape} and flatfield {flatfield.shape} do not match shapes.'
        warnings.warn(msg)
        return img

    if darkfield is None:
        ret = img * np.mean(flatfield) / flatfield
    else:
        gain = np.mean(flatfield - darkfield) / (flatfield - darkfield)
        ret = (img - darkfield) * gain

    # print(f"flatfield {img.dtype} / {ret.dtype} => {flatfield.dtype}")
    return ret


def collect_flatfield(ctrl=None, frames=100, save_images=False, collect_darkfield=True, drc='.', **kwargs):
    """Routine to collect flatfield correction files.

    Spread the beam and focus on an a vacuum area
    The routine will collect a number of images and average them for the flatfield correction images
    The optimal exposure time for each image is calculated automatically so that the response is at approximately
        1/10 the dynamic range

    `frames`: number of frames to average for correction image(s)
    `save_images`: save the collected images
    `collect_darkfield`: additionally collect darkfield correction (by blanking the beam)
    `drc`: output directory
    """
    exposure = kwargs.get('exposure', ctrl.cam.default_exposure)
    binsize = kwargs.get('binsize', ctrl.cam.default_binsize)
    confirm = kwargs.get('confirm', True)
    date = time.strftime('%Y-%m-%d')

    drc = Path(drc).absolute()

    # ctrl.brightness.max()
    if confirm:
        input(f'\n >> Press <ENTER> to continue to collect {frames} flat field images')

    img, h = ctrl.get_image(exposure=exposure, binsize=binsize, header_keys=None)

    exposure = exposure * (config.camera.dynamic_range / 10.0) / img.mean()
    print('exposure:', exposure)

    ctrl.cam.block()

    buffer = []

    print('\nCollecting flatfield images')
    for n in tqdm(range(frames)):
        outfile = drc / f'flatfield_{n:04d}.tiff' if save_images else None
        img, h = ctrl.get_image(exposure=exposure, binsize=binsize, out=outfile, comment=f'Flat field #{n:04d}', header_keys=None)
        buffer.append(img)

    f = np.mean(buffer, axis=0)
    deadpixels = get_deadpixels(f)
    get_center_pixel_correction(f)
    f = remove_deadpixels(f, deadpixels=deadpixels)
    ff = drc / f'flatfield_{ctrl.cam.name}_{date}.tiff'
    write_tiff(ff, f, header={'deadpixels': deadpixels})

    fp = drc / f'deadpixels_tpx_{date}.npy'
    np.save(fp, deadpixels)

    if collect_darkfield:
        ctrl.beam.blank()

        buffer = []

        print('\nCollecting darkfield images')
        for n in tqdm(range(frames)):
            outfile = drc / f'darkfield_{n:04d}.tiff' if save_images else None
            img, h = ctrl.get_image(exposure=exposure, binsize=binsize, out=outfile, comment=f'Dark field #{n:04d}', header_keys=None)
            buffer.append(img)

        d = np.mean(buffer, axis=0)
        d = remove_deadpixels(d, deadpixels=deadpixels)

        ctrl.beam.unblank()

        fd = drc / f'darkfield_{ctrl.cam.name}_{date}.tiff'
        write_tiff(fd, d, header={'deadpixels': deadpixels})

    ctrl.cam.unblock()

    print(f'\nFlatfield collection finished ({drc}).')


def main_entry():
    import argparse
    description = """
This is a program that can collect and apply flatfield/darkfield corrections [link](https://en.wikipedia.org/wiki/Flat-field_correction). To do so, use a spread, bright beam on a hole in the carbon, or a clear piece of carbon film, and run:

    instamatic.flatfield --collect

This will collect 100 images and average them to determine the flatfield image. A darkfield image is also collected by applying the same routine with the beam blanked. Dead pixels are identified as pixels with 0 intensities. To apply these corrections:

    instamatic.flatfield image.tiff [image.tiff ..] -f flatfield.tiff [-d darkfield.tiff] [-o drc]

This will apply the flatfield correction (`-f`) and optionally the darkfield correction (`-d`) to images given as argument, and place the corrected files in directory `corrected` or as specified using `-o`."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('args',
                        type=str, nargs='*', metavar='image.tiff',
                        help='Image file paths/pattern')

    parser.add_argument('-f', '--flatfield',
                        action='store', type=str, metavar='flatfield.tiff', dest='flatfield',
                        help="""Path to flatfield file""")

    parser.add_argument('-d', '--darkfield',
                        action='store', type=str, metavar='darkfield.tiff', dest='darkfield',
                        help="""Path to darkfield file""")

    parser.add_argument('-o', '--output',
                        action='store', type=str, metavar='DRC', dest='drc',
                        help="""Output directory for image files""")

    parser.add_argument('-c', '--collect',
                        action='store_true', dest='collect',
                        help="""Collect flatfield/darkfield images on microscope""")

    parser.set_defaults(
        flatfield=None,
        darkfield=None,
        drc='corrected',
        collect=False,
    )

    options = parser.parse_args()
    args = options.args

    if options.collect:
        ctrl = TEMController.initialize()
        collect_flatfield(ctrl=ctrl, save_images=False)
        ctrl.close()
        exit()

    if options.flatfield:
        flatfield, h = read_tiff(options.flatfield)
        deadpixels = h['deadpixels']
    else:
        print('No flatfield file specified')
        exit()

    if options.darkfield:
        darkfield, h = read_tiff(options.darkfield)
    else:
        darkfield = np.zeros_like(flatfield)

    if len(args) == 1:
        fobj = args[0]
        if not os.path.exists(fobj):
            args = glob.glob(fobj)

    drc = Path(options.drc)
    drc.mkdir(exist_ok=True, parents=True)

    for f in args:
        img, h = read_tiff(f)

        img = apply_corrections(img, deadpixels=deadpixels)
        img = apply_flatfield_correction(img, flatfield, darkfield=darkfield)

        name = Path(f).name
        fout = drc / name

        print(name, '->', fout)
        write_tiff(fout, img, header=h)


if __name__ == '__main__':
    main_entry()
