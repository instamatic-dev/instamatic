#!/usr/bin/env python

from luke.emformats.mrc import read_image, read_header
import os
import sys
import numpy as np
import json


def load_mrc(fn):
    img = read_image(fn)
    img = np.flipud(img).astype(int)

    root, ext = os.path.splitext(fn)
    headerfile = open(root + ".json", "r")
    h = json.load(headerfile)
    print "shape", img.shape
    print "min:", img.min(), ":", img.max()
    return img, h


def main_entry():
    if not sys.argv[1:]:
        print "Convert mrc images to npy format."
        print
        print "Usage: mrc2npy image.mrc [image.mrc ...]"
        exit()

    for fn in sys.argv[1:]:
        img, h = load_mrc(fn)

        root, ext = os.path.splitext(fn)
        outfile = root + ".npy"

        np.save(outfile, img)

        print "{} -> {}".format(fn, outfile)


if __name__ == '__main__':
    main_entry()
