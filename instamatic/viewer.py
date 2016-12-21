#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt
import sys

from formats import read_tiff

markers = []
fig = plt.figure()

image_keys = (
 "ImageBinSize",
 "ImageComment",
 "ImageExposureTime",
 "ImageResolution",
 "Time" )

microscope_keys = (
 "FunctionMode",
 "Magnification",
 "StagePosition",
 "BeamShift",
 "BeamTilt",
 "Brightness",
 "DiffFocus",
 "DiffShift",
 "GunShift",
 "GunTilt",
 "ImageShift" )


def onclick(event):
    # print event.x, event.y, event.xdata, event.ydata
    print event.xdata, event.ydata
    x, y = event.xdata, event.ydata

    if event.button == 1:
        plt.scatter(x, y, color="red", edgecolor="white")
        markers.append((int(event.xdata), int(event.ydata)))
        fig.canvas.draw()


def main():
    try:
        fn = sys.argv[1]
    except:
        print "Usage: instamatic.viewer IMG.tiff"
        exit()

    img, h = read_tiff(fn)

    print """Loading data: {}
        size: {} kB
       shape: {}
       range: {}-{}
""".format(fn, img.nbytes / 1024, img.shape, img.min(), img.max())

    l1 = max([len(s) for s in image_keys])
    l2 = max([len(s) for s in microscope_keys])

    fmt1 = "{{:{}s}} = {{}}".format(l1)
    fmt2 = "{{:{}s}} = {{}}".format(l2)

    for key in image_keys:
        try:
            print fmt1.format(key, h[key])
        except KeyError:
            pass
    print
    for key in microscope_keys:
        try:
            print fmt2.format(key, h[key])
        except KeyError:
            pass

    fig.canvas.mpl_connect('button_press_event', onclick)
    plt.imshow(img, cmap="gray")
    plt.title(fn)
    plt.show()

    global markers
    if len(markers) > 0:
        markers = np.array(markers)
        np.save("clicked.npy", markers)


if __name__ == '__main__':
    main()
