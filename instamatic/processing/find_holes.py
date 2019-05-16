#!/usr/bin/env python

import os
import sys

import matplotlib.pyplot as plt
import numpy as np

from scipy import ndimage

from skimage import data
from skimage import color
from skimage import filters
from skimage import morphology
from skimage import segmentation
from skimage import exposure
from skimage import measure
import json

plt.rcParams['image.cmap'] = 'gray'

from instamatic.config import calibration
from instamatic.tools import *


def plot_features(img, segmented):
    """Take image and plot segments on top of them"""
    labels, numlabels = ndimage.label(segmented)
    image_label_overlay = color.label2rgb(labels, image=img, bg_label=0)

    # plt.imsave("a2.png", img)
    # plt.imsave("c2.png", segmented)
    # plt.imsave("d2.png", image_label_overlay)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(15, 10), sharex=True, sharey=True)
    ax1.imshow(img, interpolation='nearest')
    ax1.contour(segmented, [0.5], linewidths=1.2, colors='r')

    ax1.axis('off')
    ax1.set_adjustable('box-forced')
    ax2.imshow(image_label_overlay, interpolation='nearest')
    ax2.axis('off')
    ax2.set_adjustable('box-forced')

    margins = dict(hspace=0.01, wspace=0.01, top=1, bottom=0, left=0, right=1)
    fig.subplots_adjust(**margins)
    plt.show()


def plot_props(img, props, fname=None, scale=1):
    """Take image and plot props on top of them"""
    from matplotlib.patches import Rectangle

    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    plt.imshow(img, interpolation="none")

    for i,prop in enumerate(props):
        y1, x1, y2, x2 = [x*scale for x in prop.bbox]

        color = "red"

        rect = Rectangle((x1 - 1, y1 - 1), x2 - x1 + 1,
                         y2 - y1 + 1, fc='none', ec=color, lw=2)
        ax.add_patch(rect)

        cy, cx = prop.weighted_centroid*scale
        plt.scatter([cx], [cy], c=color, s=10, edgecolor='none')

        # s = " {}".format(i, int(cx), int(cy))
        s = " {}:\n {:d}\n {:d}".format(i, int(cx), int(cy))
        # s = " {}:\n {:f}".format(i, prop.eccentricity)
        plt.text(x2, y2, s=s, color="red", size=15)

    ymax, xmax = img.shape
    plt.axis('off')
    plt.xlim(0, xmax)
    plt.ylim(ymax, 0)

    if fname:
        print(fname)
        plt.savefig(fname)
        plt.close()
    else:
        plt.show()


def get_markers_bounds(img, lower=100, upper=180, dark_on_bright=True, verbose=True):
    """Get markers using simple thresholds"""
    background = 1
    features = 2
    
    markers = np.zeros_like(img)
    if verbose:
        print("\nbounds:", lower, upper)

    if dark_on_bright:
        markers[img < lower] = features
        markers[img > upper] = background  
    else:
        markers[img < lower] = background
        markers[img > upper] = features
    
    if verbose:
        print("\nother      {:6.2%}".format(1.0*np.sum(markers == 0) / markers.size))
        print("background {:6.2%}".format(1.0*np.sum(markers == background) / markers.size))
        print("features   {:6.2%}".format(1.0*np.sum(markers == features) / markers.size))

    return markers


def calculate_hole_area(diameter, magnification, img_scale=1, binsize=1):
    """Approximate the size of the feature to locate

    diameter: float,
        target diameter of feature to locate (in micrometer)
    magnification: int,
        Magnification used for the determination
    img_scale: float,
        If the image has been scaled down, the scale can be given here to accurately calculate the hole area in pixels
    binsize: int,
        binning used for the data collection (1, 2, or 4)
    
    Returns:
        area: float,
            apprximate feature size in pixels
    """

    px = py = calibration.pixelsize_lowmag[magnification] / 1000  # nm -> um
    px *= (binsize / img_scale)
    py *= (binsize / img_scale)
    hole_area = (np.pi*(diameter/2.0)**2) / (px * py)
    return hole_area


def find_holes(img, area=0, plot=True, fname=None, verbose=True, max_eccentricity=0.4):
    """Hole size as diameter in micrometer

    img: np.ndarray,
        image as 2d numpy array
    area: int or float,
        approximate size in pixels of the feature to locate
    plot: bool,
        plot intermediate stages of hole finding routine
    verbose: bool,
        increase verbosity of output if True
    max_eccentricity: float,
        the maximum allowed eccentricity for hole detection (0.0: perfect circle to 1.0: prefect eccentric)

    Returns:
        props: list,
            list of props of the objects found

    """
    otsu = filters.threshold_otsu(img)
    n = 0.25
    l = otsu - (otsu - np.min(img))*n
    u = otsu + (np.max(img) - otsu)*n
    if verbose:
        print("img range: {} - {}".format(img.min(), img.max()))
        print("otsu: {:.0f} ({:.0f} - {:.0f})".format(otsu, l, u))
    
    markers = get_markers_bounds(img, lower=l, upper=u, dark_on_bright=False, verbose=verbose)
    segmented = segmentation.random_walker(img, markers, beta=10, mode='bf')

    disk = morphology.disk(4)
    segmented = morphology.binary_closing(segmented - 1, disk)

    # segmented = ndimage.binary_fill_holes(segmented - 1)

    segmentation.clear_border(segmented, buffer_size=0, bgval=0, in_place=True)

    labels, numlabels = ndimage.label(segmented)
    props = measure.regionprops(labels, img)

    newprops = []
    for prop in props:
        # print prop.eccentricity, prop.area, prop.area*pxx*pxy, hole_area
        if prop.eccentricity > max_eccentricity:
            continue
        # FIXME .convex_area crashes here with skimage-0.12.3, use .area instead
        if prop.area < area*0.75:  
            continue

        newprops.append(prop)
    
    print(" >> {} holes found in {} objects.".format(len(newprops), numlabels))
    
    if plot:
        plot_props(img, newprops)
    if fname:
        plot_props(img, newprops, fname)

    return newprops


def find_holes_entry():
    from formats import read_image

    for fn in sys.argv[1:]:
        img, h = read_image(fn)

        img_zoomed, scale = autoscale(img, maxdim=512)
        
        binsize = h["ImageBinSize"]
        magnification = h["Magnification"]
        d = 150

        area = calculate_hole_area(d, magnification, img_scale=scale, binsize=binsize)
        holes = find_holes(img_zoomed, area=area, plot=True)

        print()
        for hole in holes:
            x,y = hole.centroid
            px = py = calibration.pixelsize_lowmag[magnification] / 1000  # nm -> um
            area = hole.area*px*py / scale**2
            d = 2*(area/np.pi)**0.5
            print("x: {:.2f}, y: {:.2f}, d: {:.2f} um".format(x*scale, y*scale, d))


if __name__ == '__main__':
    find_holes_entry()
