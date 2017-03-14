import os,sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

from instamatic.formats import *

from skimage.feature import canny
from skimage.measure import label, regionprops
from scipy.ndimage import morphology
from scipy.ndimage import interpolation
import math


def apply_transform_to_image(img, transform, center=None):
    """Applies transformation matrix to image and recenters it
    http://docs.sunpy.org/en/stable/_modules/sunpy/image/transform.html
    http://stackoverflow.com/q/20161175
    """

    if center is None:
        center = (np.array(img.shape)[::-1]-1)/2.0
    # shift = (center - center.dot(transform)).dot(np.linalg.inv(transform))
    
    displacement = np.dot(transform, center)
    shift = center - displacement
    
    img_tf = interpolation.affine_transform(img, transform, offset=shift, mode="constant", order=3, cval=0.0)
    return img_tf


def affine_transform_ellipse_to_circle(azimuth, stretch, inverse=False):
    """Usage: 

    e2c = circle_to_ellipse_affine_transform(azimuth, stretch):
    np.dot(arr, e2c) # arr.shape == (n, 2)
       or
    apply_transform_to_image(img, e2c)

    http://math.stackexchange.com/q/619037
    """
    sin = np.sin(azimuth)
    cos = np.cos(azimuth)
    sx    = 1 - stretch
    sy    = 1 + stretch
    
    # apply in this order
    rot1 = np.array((cos, -sin,  sin, cos)).reshape(2,2)
    scale = np.array((sx, 0, 0, sy)).reshape(2,2)
    rot2 = np.array((cos,  sin, -sin, cos)).reshape(2,2)
    
    composite = rot1.dot(scale).dot(rot2)
    
    if inverse:
        return np.linalg.inv(composite)
    else:
        return composite


def affine_transform_circle_to_ellipse(azimuth, stretch):
    """Usage: 

    c2e = circle_to_ellipse_affine_transform(azimuth, stretch):
    np.dot(arr, c2e) # arr.shape == (n, 2)
       or
    apply_transform_to_image(img, c2e)
    """
    return affine_transform_ellipse_to_circle(azimuth, stretch, inverse=True)


def make_title(prop):
    azimuth = np.degrees(prop.orientation)
    stretch = -1 + prop.major_axis_length/prop.minor_axis_length
    minlen, maxlen = prop.minor_axis_length, prop.major_axis_length
    s = "Azimuth: {:.2f}, Stretch: {:.2%}\nmin/max length: {:.1f}, {:.1f}".format(azimuth, stretch, minlen, maxlen)
    return s


def get_sigma_interactive(img, sigma=20):
    edges = canny(img, sigma=sigma, low_threshold=None, high_threshold=None)
    
    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.25)

    prop = get_ring_props(edges)[0]
    ax.set_title(make_title(prop))

    im1 = ax.imshow(img, interpolation=None)
    im2 = ax.imshow(edges, alpha=0.5, interpolation=None)
    
    axsigma = fig.add_axes([0.25, 0.10, 0.5, 0.03])
    axvmax  = fig.add_axes([0.25, 0.15, 0.5, 0.03])
    
    scaled_min, scaled_max = np.percentile(img, q=(0.2, 99.8))
    slsigma = Slider(axsigma, 'Sigma',    0, 50,   valinit=sigma)
    slvmax  = Slider(axvmax,  'Contrast', scaled_min, scaled_max, valinit=(scaled_min + scaled_max) / 2)
    
    def update_vmax(val):
        im1.set_clim(vmax=slvmax.val)
        fig.canvas.draw()
    
    def update_sigma(val):
        edges = canny(img, sigma=slsigma.val, low_threshold=None, high_threshold=None)
        im2.set_data(edges)
        prop = get_ring_props(edges)[0]
        ax.set_title(make_title(prop))
        fig.canvas.draw()
    
    slsigma.on_changed(update_sigma)
    slvmax.on_changed(update_vmax)
    
    plt.show()
    
    return slsigma.val


def plot_props(edges, props):
    plt.imshow(edges)
    for prop in props:
        print "centroid = ({:.2f}, {:.2f})".format(*prop.centroid)
        print "eccentricity = {:.2f}".format(prop.eccentricity)
        print "stretch azimuth = {:.2f} degrees".format(np.degrees(prop.orientation))
        print "stretch percent = {:.2%}".format(-1 + prop.major_axis_length/prop.minor_axis_length)
        print "min/max lengths = ({:.2f}, {:.2f})".format(prop.minor_axis_length, prop.major_axis_length)
        print "avg. diameter = {:.2f}".format(prop.equivalent_diameter)
        print
        y0, x0 = prop.centroid
        orientation = prop.orientation
        x1 = x0 + math.cos(orientation) * 0.5 * prop.major_axis_length
        y1 = y0 - math.sin(orientation) * 0.5 * prop.major_axis_length
        x2 = x0 - math.sin(orientation) * 0.5 * prop.minor_axis_length
        y2 = y0 - math.cos(orientation) * 0.5 * prop.minor_axis_length
    
        plt.plot((x0, x1), (y0, y1), '-r', linewidth=2.5)
        plt.plot((x0, x2), (y0, y2), '-g', linewidth=2.5)
        plt.plot(x0, y0, '+y', markersize=15)
    
        minr, minc, maxr, maxc = prop.bbox
        bx = (minc, maxc, maxc, minc, minc)
        by = (minr, minr, maxr, maxr, minr)
        plt.plot(bx, by, '-b', linewidth=2.5)
    plt.show()


def get_ring_props(edges):

    # label edges
    labeled = label(edges)
    
    props = []
    for i in range(1, labeled.max()+1):
        obj = labeled == i

        # fill holes so that regionprops can calculate inertia tensor correctly
        obj = morphology.binary_fill_holes(obj)
        
        props.extend(regionprops(obj.astype(int)))
    
    # filter ugly/small props
    props = [prop for prop in props if (prop.eccentricity < 0.5 and prop.area > 10)]
    
    # sort by size
    props = sorted(props, key=lambda x: x.area, reverse=True)

    return props


def main(sigma=None):
    if len(sys.argv) != 2:
        print "Program to find microscope stretch percent/azimuth from a powder pattern"
        print
        print "Usage: python find_stretch_correction.py powder_pattern.tiff"
        exit()

    fname = sys.argv[1]
    img,h = read_tiff(fname)

    if not sigma:
        sigma = get_sigma_interactive(img)

    # edge detection
    edges = canny(img, sigma=sigma, low_threshold=None, high_threshold=None)

    # get regionprops
    props = get_ring_props(edges)

    # parse results
    plot_props(edges, props)


if __name__ == '__main__':
    main()
