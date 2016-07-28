#!/usr/bin/env python

import numpy as np
import json
import matplotlib.pyplot as plt
import os
import sys

# from IPython import embed

markers = []
fig = plt.figure()


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
        print "Usage: instamatic.viewer fn.npy"

    arr = np.load(fn)

    print "shape", arr.shape
    print "min:", arr.min(), ":", arr.max()

    root, ext = os.path.splitext(fn)
    fnh = root + ".json"

    if os.path.exists(fnh):
        d = json.load(open(fnh, "r"))
        json.dump(d, sys.stdout, indent=2)

    fig.canvas.mpl_connect('button_press_event', onclick)
    plt.imshow(arr, cmap="gray")
    plt.show()

    global markers
    if len(markers) > 0:
        markers = np.array(markers)
        np.save("clickmarkers.npy", markers)


if __name__ == '__main__':
    main()
