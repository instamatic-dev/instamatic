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

plt.rcParams['image.cmap'] = 'gray'


def denoise(img, sigma=3, method="median"):
    """Denoises the image using a gaussian or median filter.
    median filter is better at preserving edges"""
    if method == "gaussian":
        return ndimage.gaussian_filter(img, sigma)
    else:
        return ndimage.median_filter(img, sigma)


def enhance_contrast(img):
    """Enhance contrast by histogram equalization"""
    return exposure.equalize_hist(img)


def get_markers_bounds(img, lower=100, upper=180, dark_on_bright=True):
    """Get markers using simple thresholds"""
    background = 1
    features = 2

    if dark_on_bright:
        background, features = features, background

    markers = np.zeros_like(img)

    print "\nbounds:", lower, upper
    
    markers[img < lower] = background
    markers[img > upper] = features
    
    print "\nother     ", np.sum(markers == 0)
    print "background", np.sum(markers == background)
    print "features  ", np.sum(markers == features)

    return markers


def get_markers_gradient(img, radius=10, threshold=40):
    """Get markers using the gradient method
    http://scikit-image.org/docs/dev/auto_examples/plot_marked_watershed.html"""
    markers = filters.rank.gradient(
        img, morphology.disk(radius)) < threshold
    markers = ndimage.label(markers)[0]
    return markers


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


def find_crystals(img, method="watershed", markers=None, plot=False, **kwargs):
    """Find crystals using the watershed or random_walker methods"""

    clear_border = kwargs.get("clear_border", True)
    min_size = kwargs.get("min_size", 100)
    fill_holes = kwargs.get("fill_holes", False)

    if isinstance(markers, np.ndarray):
        assert img.shape == markers.shape, "Shape of markers ({}) does not match image ({})".format(
            markers.shape, img.shape)
    elif markers == "bounds":
        otsu = filters.threshold_otsu(img)
        lower_bound = otsu*0.5
        upper_bound = otsu
        markers = get_markers_bounds(img, lower=lower_bound, upper=upper_bound)
    elif markers == "gradient":
        radius = kwargs.get("radius", 10)
        threshold = kwargs.get("threshold", 40)
        markers = get_markers_gradient(img, radius=radius, threshold=threshold)
    else:
        markers = get_markers_bounds(img, lower=100, upper=180)

    if method == "watershed":
        elevation_map = filters.sobel(img)
        segmented = morphology.watershed(elevation_map, markers)
    elif method == "random_walker":
        segmented = segmentation.random_walker(
            img, markers, beta=10, mode='bf')
    else:
        raise ValueError("Don't know method: {}".format(method))

    # plt.imsave("a.png", img)
    # plt.imsave("b.png", markers)
    # plt.imsave("c.png", segmented)

    if fill_holes:
        segmented = ndimage.binary_fill_holes(segmented - 1)
    else:
        segmented = segmented.astype(int)

    # plt.imsave("d.png", segmented)

    if min_size > 0:
        print " >> Removing objects smaller than {} pixels".format(min_size)
        morphology.remove_small_objects(segmented, min_size=min_size, connectivity=1, in_place=True)

    if clear_border:
        print " >> Removing crystals touching the edge of the frame"
        segmentation.clear_border(segmented, buffer_size=0, bgval=0, in_place=True)

    if plot:
        plot_features(img, segmented)

    labels, numlabels = ndimage.label(segmented)
    print " >> {} crystals found in image".format(numlabels)
    props = measure.regionprops(labels, img)

    image_label_overlay = color.label2rgb(labels, image=img, bg_label=0)
    plt.imsave("e.png", image_label_overlay)

    return props


def plot_props(img, props):
    """Take image and plot props on top of them"""
    from matplotlib.patches import Rectangle

    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    plt.imshow(img, interpolation="none")

    ymax, xmax = img.shape
    for prop in props:
        y1, x1, y2, x2 = prop.bbox

        color = "red"

        rect = Rectangle((x1 - 1, y1 - 1), x2 - x1 + 1,
                         y2 - y1 + 1, fc='none', ec=color, lw=2)
        ax.add_patch(rect)

        cy, cx = prop.weighted_centroid
        plt.scatter([cx], [cy], c=color, s=10, edgecolor='none')

        plt.axis('off')

        plt.xlim(0, xmax)
        plt.ylim(ymax, 0)

        s = " {:d} {:d}\n".format(int(cx), int(cy))
        plt.text(x2, y2, s=s, color="black", size=15)

    plt.show()


def reject_bad_crystals(props, **kwargs):
    """
    Reject crystals if:
    1. they touch the image boundary
    2. they are too small
        min_size = 75
    3. they are too eccentric
        max_eccentricity = 0.99
    """
    min_size = kwargs.get("min_size", 75)
    max_eccentricity = kwargs.get("max_eccentricity", 0.99)

    # hack to easily retrieve image size
    ymax, xmax = props[0]._intensity_image.shape
    newprops = []
    for prop in props:
        y1, x1, y2, x2 = prop.bbox
        # reject because they are on the edge of the image
        if (x1 == 0) or (x2 == xmax) or (y1 == 0) or (y2 == ymax):
            continue
        # reject if too small
        if prop.area < min_size:
            continue
        # reject if too eccentric
        if prop.eccentricity >= max_eccentricity:
            continue
        newprops.append(prop)
    print " >> Rejected {} / {} crystals, {} left".format(len(props)-len(newprops), len(props), len(newprops))
    return newprops


def props2xy(props):
    """Takes regionprops and returns xy coords in numpy array"""
    return np.array([prop.weighted_centroid for prop in props])


def invert_image(img):
    """Naive way of inverting image color, should probably be imporoved"""
    return (img * -1) + 255


def load_image(fn):
    """Load image. Replace this with function from fabio/snapkit for mrc files

    TODO: check if leginon has implemented mrc or other electron microscopy formats
    """
    return data.imread(fn)


def find_crystals_entry():
    for fn in sys.argv[1:]:
        img = color.rgb2gray(load_image(fn))

        crystals = find_crystals(img, plot=False, markers="bounds")

        # crystals = reject_bad_crystals(crystals) ## implemented in find_crystals

        plot_props(img, crystals)

        xy = props2xy(crystals)

        # print xy

        # plt.imshow(img)
        # plt.scatter(xy[:, 1], xy[:, 0], color="red")
        # plt.show()


if __name__ == '__main__':
    find_crystals_entry()
