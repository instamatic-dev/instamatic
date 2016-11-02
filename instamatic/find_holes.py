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

from tools import *

def get_best_mag_for_feature(xsize, ysize=None, verbose=False):
    """Not used, outdated"""
    if not ysize:
        ysize = xsize
    bestmag = 0
    for mag,(pxx, pxy) in lowmag_dimensions.items():
        if pxx == pxy == 0:
            pxx = pxy = 600 * 0.0746331 / mag
        
        tx = 2048
        ty = 2048
        add = ""
        if (xsize/pxx < tx) and (ysize/pxy < ty):
            if mag > bestmag:
                bestmag = mag
                add = "**"
        if verbose:
            print "{:6d} {:8.0f} {:8.0f} {}".format(mag, xsize/pxx, ysize/pxy, add)
    return bestmag


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


def get_markers_bounds(img, lower=100, upper=180, dark_on_bright=True, verbose=True):
    """Get markers using simple thresholds"""
    background = 1
    features = 2
    
    markers = np.zeros_like(img)
    if verbose:
        print "\nbounds:", lower, upper

    if dark_on_bright:
        markers[img < lower] = features
        markers[img > upper] = background  
    else:
        markers[img < lower] = background
        markers[img > upper] = features
    
    if verbose:
        print "\nother      {:6.2%}".format(1.0*np.sum(markers == 0) / markers.size)
        print   "background {:6.2%}".format(1.0*np.sum(markers == background) / markers.size)
        print   "features   {:6.2%}".format(1.0*np.sum(markers == features) / markers.size)

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


def find_objects(img, method="watershed", markers=None, plot=False, verbose=True, **kwargs):
    """Find crystals using the watershed or random_walker methods"""

    clear_border = kwargs.get("clear_border", True)
    min_size = kwargs.get("min_size", 500)
    fill_holes = kwargs.get("fill_holes", True)

    if isinstance(markers, np.ndarray):
        assert img.shape == markers.shape, "Shape of markers ({}) does not match image ({})".format(
            markers.shape, img.shape)
    elif markers == "bounds":
        otsu = filters.threshold_otsu(img)
        n = 0.33
        l = otsu - (otsu - np.min(img))*n
        u = otsu + (np.max(img) - otsu)*n
        markers = get_markers_bounds(img, lower=l, upper=u, verbose=verbose)
    elif markers == "gradient":
        radius = kwargs.get("radius", 10)
        threshold = kwargs.get("threshold", 40)
        markers = get_markers_gradient(img, radius=radius, threshold=threshold)
    else:
        markers = get_markers_bounds(img, lower=100, upper=180, verbose=verbose)

    # if plot:
    #     plt.imshow(markers)
    #     plt.show()

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
        if verbose:
            print " >> Removing objects smaller than {} pixels".format(round(min_size))
        # plt.imsave("before.png", segmented)
        morphology.remove_small_objects(segmented, min_size=min_size, connectivity=1, in_place=True)
        # plt.imsave("after.png", segmented)

    if clear_border:
        if verbose:
            print " >> Removing objects touching the edge of the frame"
        segmentation.clear_border(segmented, buffer_size=0, bgval=0, in_place=True)

    if plot:
        plot_features(img, segmented)

    labels, numlabels = ndimage.label(segmented)
    print " >> {} objects found in image".format(numlabels)
    props = measure.regionprops(labels, img)

    # image_label_overlay = color.label2rgb(labels, image=img, bg_label=0)
    # plt.imsave("e.png", image_label_overlay)

    return props


def find_crystals(img, header=None, plot=False, verbose=True):
    raise DeprecationWarning("Deprecated: Use find_crystals.py:find_crystals instead.")

    otsu = filters.threshold_otsu(img)
    # nl = 0.50
    # nu = 0.00

    nl = 0.15
    nu = 0.05

    l = otsu - (otsu - np.min(img))*nl
    u = otsu + (np.max(img) - otsu)*nu
    if verbose:
        print "img range: {} - {}".format(img.min(), img.max())
        print "otsu: {:.0f} ({:.0f} - {:.0f})".format(otsu, l, u)

    markers = get_markers_bounds(img, lower=l, upper=u, verbose=verbose)

    crystals = find_objects(img, method="random_walker", markers=markers, plot=plot, verbose=verbose)
    return crystals


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

    pxx, pxy = lowmag_pixeldimensions[magnification]
    pxx *= (binsize / img_scale)
    pxy *= (binsize / img_scale)
    hole_area = (np.pi*(diameter/2.0)**2) / (pxx * pxy)
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
        print "img range: {} - {}".format(img.min(), img.max())
        print "otsu: {:.0f} ({:.0f} - {:.0f})".format(otsu, l, u)
    
    markers = get_markers_bounds(img, lower=l, upper=u, dark_on_bright=False, verbose=verbose)
    # plt.imshow(markers)
    props = find_objects(img, markers=markers, fill_holes=True, plot=plot, verbose=verbose)

    newprops = []
    for prop in props:
        # print prop.eccentricity, prop.area, prop.area*pxx*pxy, hole_area
        if prop.eccentricity > max_eccentricity:
            continue
        # FIXME .convex_area crashes here with skimage-0.12.3, use .area instead
        if prop.area < area*0.75:  
            continue

        # print "fa", prop.filled_area
        # print "a", prop.area
        # print "d", prop.equivalent_diameter

        newprops.append(prop)
    
    if plot:
        plot_props(img, newprops)
    if fname:
        plot_props(img, newprops, fname)

    return newprops


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
        print fname
        plt.savefig(fname)
        plt.close()
    else:
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


def plot_hists(img):
    from skimage import data, img_as_float
    from skimage import exposure
    def plot_img_and_hist(img, axes, bins=256):
        """Plot an image along with its histogram and cumulative histogram.
    
        """
        img = img_as_float(img)
        ax_img, ax_hist = axes
        ax_cdf = ax_hist.twinx()
    
        img_show = img.copy()
        img_show[img > 0.065] = 1
        
        # Display image
        ax_img.imshow(img_show, cmap=plt.cm.gray)
        ax_img.set_axis_off()
        ax_img.set_adjustable('box-forced')
    
        # Display histogram
        ax_hist.hist(img.ravel(), bins=bins, histtype='step', color='black')
        ax_hist.ticklabel_format(axis='y', style='scientific', scilimits=(0, 0))
        ax_hist.set_xlabel('Pixel intensity')
        ax_hist.set_xlim(0, 1)
        ax_hist.set_yticks([])
    
        # Display cumulative distribution
        img_cdf, bins = exposure.cumulative_distribution(img, bins)
        ax_cdf.plot(bins, img_cdf, 'r')
        ax_cdf.set_yticks([])
    
        return ax_img, ax_hist, ax_cdf
    
    img = img.astype(np.uint16)
    
    # Contrast stretching
    p2, p98 = np.percentile(img, (2, 98))
    img_rescale = exposure.rescale_intensity(img, in_range=(p2, p98))
    
    # Equalization
    img_eq = exposure.equalize_hist(img)
    
    # Adaptive Equalization
    img_adapteq = exposure.equalize_adapthist(img, clip_limit=0.03)
    
    # Display results
    fig = plt.figure(figsize=(15, 10))
    axes = np.zeros((2,4), dtype=np.object)
    axes[0,0] = fig.add_subplot(2, 4, 1)
    for i in range(1,4):
        axes[0,i] = fig.add_subplot(2, 4, 1+i, sharex=axes[0,0], sharey=axes[0,0])
    for i in range(0,4):
        axes[1,i] = fig.add_subplot(2, 4, 5+i)
    
    ax_img, ax_hist, ax_cdf = plot_img_and_hist(img, axes[:, 0])
    ax_img.set_title('Low contrast image')
    
    y_min, y_max = ax_hist.get_ylim()
    ax_hist.set_ylabel('Number of pixels')
    ax_hist.set_yticks(np.linspace(0, y_max, 5))
    
    ax_img, ax_hist, ax_cdf = plot_img_and_hist(img_rescale, axes[:, 1])
    ax_img.set_title('Contrast stretching')
    
    ax_img, ax_hist, ax_cdf = plot_img_and_hist(img_eq, axes[:, 2])
    ax_img.set_title('Histogram equalization')
    
    ax_img, ax_hist, ax_cdf = plot_img_and_hist(img_adapteq, axes[:, 3])
    ax_img.set_title('Adaptive equalization')
    
    ax_cdf.set_ylabel('Fraction of total intensity')
    ax_cdf.set_yticks(np.linspace(0, 1, 5))
    
    # prevent overlap of y-axis labels
    fig.subplots_adjust(wspace=0.4)
    plt.show()


def props2xy(props):
    """Takes regionprops and returns xy coords in numpy array"""
    return np.array([prop.weighted_centroid for prop in props])


def invert_image(img):
    """Naive way of inverting image color, should probably be imporoved"""
    return (img * -1) + 255


def load_image_file(fn):
    """Load image. Replace this with function from fabio/snapkit for mrc files

    TODO: check if leginon has implemented mrc or other electron microscopy formats
    """
    return data.imread(fn)


def find_crystals_entry():
    for fn in sys.argv[1:]:
        print "\n >> Processing {}...".format(fn)
        try:
            img = color.rgb2gray(load_image_file(fn))
        except IOError:
            img, header = load_img(fn)
            img = img.astype(int)

        # plot_hists(img)

        img, scale = autoscale(img, maxdim=512)

        print
        print "scale", scale
        print

        plot = False
        crystals = find_crystals(img, plot=plot)
        if plot:
            plot_props(img, crystals)

        root, ext = os.path.splitext(fn)
        plot_props(img, crystals, fname=root+"_crystals.png")

        # crystals = reject_bad_crystals(crystals) ## implemented in find_objects

        xy = props2xy(crystals)

        # print xy

        # plt.imshow(img)
        # plt.scatter(xy[:, 1], xy[:, 0], color="red")
        # plt.show()

def find_holes_entry():
    for fn in sys.argv[1:]:
        img = np.load(fn)
        img = img.astype(int)

        scale = 1024.0 / max(img.shape) # ensure zoom so that max dimension == 1024
        img = ndimage.zoom(img, scale, order=1)
        
        root, ext = os.path.splitext(fn)
        header = json.load(open(root+".json", "r"))

        holes = find_holes(img, header, plot=True)

        xy = props2xy(holes)

        print xy




if __name__ == '__main__':
    # find_crystals_entry()
    find_holes_entry()
