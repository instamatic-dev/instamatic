#!/usr/bin/env python

import sys, os
import numpy as np
import time
from instamatic.formats import *
from instamatic import TEMController
import glob
from tqdm import tqdm

__version__ = "2017-01-31"

def apply_corrections(img, deadpixels=None):
    if deadpixels is None:
        deadpixels = get_deadpixels(img)
    img = remove_deadpixels(img, deadpixels)
    img = apply_center_pixel_correction(img)
    return img


def remove_deadpixels(img, deadpixels, d=1):
    d = 1
    for (i,j) in deadpixels:
        neighbours = img[i-d:i+d+1, j-d:j+d+1].flatten()
        img[i,j] = np.mean(neighbours)
    return img


def get_deadpixels(img):
    return np.argwhere(img == 0)


def apply_center_pixel_correction(img, k=1.19870594245):
    img[255:261,255:261] = img[255:261,255:261] * k
    return img


def get_center_pixel_correction(img):
    center = np.sum(img[255:261,255:261])
    edge = np.sum(img[254:262,254:262]) - center

    avg1 = center/36.0
    avg2 = edge/28.0
    k = avg2/avg1
    
    print "timepix central pixel correction factor:", k
    return k


def apply_flatfield_correction(img, flatfield, darkfield=None):
    """
    Apply flatfield correction to image

    https://en.wikipedia.org/wiki/Flat-field_correction"""
    
    if darkfield is None:
        ret = img * np.mean(flatfield) / flatfield
    else:
        gain = np.mean(flatfield - darkfield) / (flatfield - darkfield)
        ret = (img - darkfield) * gain
    return ret.astype(int)


def collect_flatfield(ctrl=None, frames=100, save_images=False, **kwargs):
    exposure = kwargs.get("exposure", ctrl.cam.default_exposure)
    binsize = kwargs.get("binsize", ctrl.cam.default_binsize)    
    
    # ctrl.brightness.max()
    raw_input("\n >> Press <ENTER> to continue to collect {} flat field images".format(frames))
    
    print "\nCollecting flatfield images"
    for n in tqdm(range(frames)):
        outfile = "flatfield_{:04d}.tiff".format(n) if save_images else None
        img,h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment="Flat field #{:04d}".format(n), header_keys=None)
        if n == 0:
            f = img
        else:
            f += img
    
    f = f/frames
    deadpixels = get_deadpixels(f)
    get_center_pixel_correction(f)
    f = remove_deadpixels(f, deadpixels=deadpixels)

    ctrl.beamblank = True

    print "\nCollecting darkfield images"
    for n in tqdm(range(frames)):
        outfile = "darkfield_{:04d}.tiff".format(n) if save_images else None
        img,h = ctrl.getImage(exposure=exposure, binsize=binsize, out=outfile, comment="Dark field #{:04d}".format(n), header_keys=None)

        if n == 0:
            d = img
        else:
            d += img
    
    d = d/frames
    d = remove_deadpixels(d, deadpixels=deadpixels)

    ctrl.beamblank = False

    date = time.strftime("%Y-%m-%d")
    ff = "flatfield_tpx_{}.tiff".format(date)
    fd = "darkfield_tpx_{}.tiff".format(date)
    print "\n >> Writing {} and {}...".format(ff, fd)
    write_tiff(ff, f, header={"deadpixels": deadpixels})
    write_tiff(fd, d, header={"deadpixels": deadpixels})

    fp = "deadpixels_tpx_{}.npy".format(date)
    np.save(fp, deadpixels)

    print "\n >> DONE << "


def main_entry():
    import argparse
    description = """Program to collect and apply flatfield/darkfield corrections"""

    epilog = 'Updated: {}'.format(__version__)

    parser = argparse.ArgumentParser(  # usage=usage,
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        version=__version__)

    parser.add_argument("args",
                        type=str, nargs="*", metavar="image.tiff",
                        help="Image file paths/pattern")

    parser.add_argument("-f", "--flatfield",
                        action="store", type=str, metavar="flatfield.tiff", dest="flatfield",
                        help="""Path to flatfield file""")

    parser.add_argument("-d", "--darkfield",
                        action="store", type=str, metavar="darkfield.tiff", dest="darkfield",
                        help="""Path to darkfield file""")

    parser.add_argument("-o", "--output",
                        action="store", type=str, metavar="DRC", dest="drc",
                        help="""Output directory for image files""")

    parser.add_argument("-c", "--collect",
                        action="store_true", dest="collect",
                        help="""Collect flatfield/darkfield images on microscope""")

    
    parser.set_defaults(
        flatfield=None,
        darkfield=None,
        drc="corrected",
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
        flatfield,h = read_tiff(options.flatfield)
        deadpixels = h["deadpixels"]
    else:
        print "No flatfield file specified"
        exit()

    if options.darkfield:
        darkfield,h = read_tiff(options.darkfield)
    else:
        darkfield = np.zeros_like(flatfield)

    if len(args) == 1:
        fobj = args[0]
        if not os.path.exists(fobj):
            args = glob.glob(fobj)

    if not os.path.isdir(options.drc):
        os.mkdir(options.drc)

    for f in args:
        img,h = read_tiff(f)

        img = apply_corrections(img, deadpixels=deadpixels)
        img = apply_flatfield_correction(img, flatfield, darkfield=darkfield)

        name = os.path.basename(f)
        fout = os.path.join(options.drc, name)
        
        print name, "->", fout
        write_tiff(fout, img, header=h)



if __name__ == '__main__':
    main_entry()
