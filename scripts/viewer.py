#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
import sys

from instamatic.formats import read_image


def main():
    try:
        fn = sys.argv[1]
    except:
        print "Usage: instamatic.viewer IMG.tiff"
        exit()

    img, h = read_image(fn)

    print """Loading data: {}
        size: {} kB
       shape: {}
       range: {}-{}
""".format(fn, img.nbytes / 1024, img.shape, img.min(), img.max())

    max_len = max([len(s) for s in h.keys()])

    fmt = "{{:{}s}} = {{}}".format(max_len)
    for key in sorted(h.keys()):
        print fmt.format(key, h[key])

    plt.imshow(img, cmap="gray")
    plt.title(fn)
    plt.show()

if __name__ == '__main__':
    main()
