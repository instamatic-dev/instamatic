from scipy.cluster.vq import kmeans2
from scipy._lib._util import _asarray_validated
from scipy import ndimage

import matplotlib.pyplot as plt
import numpy as np
import sys

from skimage import morphology
from skimage import filters
from skimage import segmentation
from skimage import measure

from instamatic.tools import autoscale
from instamatic.config import calibration
from collections import namedtuple


CrystalPosition = namedtuple('CrystalPosition', ['x', 'y', 'isolated', 'n_clusters', 'area_micrometer', 'area_pixel', ])


def isedge(prop):
    """Simple edge detection routine. Checks if the bbox of the prop matches the shape of the array.
    Uses a histogram to determine if an edge is detected. If the lowest bin is the dominant one,
    assume black area is measured (the edge)"""
    if  (prop._slice[0].start == 0) or \
        (prop._slice[1].start == 0) or \
        (prop._slice[0].stop == prop._intensity_image.shape[0]) or \
        (prop._slice[1].stop == prop._intensity_image.shape[1]):

        hist, edges = np.histogram(prop.intensity_image[prop.image])
        if np.sum(hist) // hist[0] < 2:
            # print " >> Edge detected"
            return True
    return False


def whiten(obs, check_finite=False):
    """
    Adapted from c:/python27/lib/site-packages/skimage/filters/thresholding.py
        to return array and std_dev
    """
    obs = _asarray_validated(obs, check_finite=check_finite)
    std_dev = np.std(obs, axis=0)
    zero_std_mask = std_dev == 0
    if zero_std_mask.any():
        std_dev[zero_std_mask] = 1.0
        raise RuntimeWarning("Some columns have standard deviation zero. The values of these columns will not change.")
    return obs / std_dev, std_dev


def segment_crystals(img, r=101, offset=5, footprint=5, remove_carbon_lacing=True):
    """
    r: `int`
       blocksize to calculate local threshold value
    footprint: `int`
       radius for disksize for erosion/dilation operations
    offset: `int`
    Constant subtracted from weighted mean of neighborhood to calculate
        the local threshold value
    """
    # workaround, because segmentation.random_walker no longer accepts floats from 0-255.0
    offset = offset / 255.0

    # normalize
    img = img * (1.0/img.max())
    
    # adaptive thresholding, because contrast is not equal over image
    arr = img > filters.threshold_local(img, r, method="mean", offset=offset)
    arr = np.invert(arr)
    # arr = morphology.binary_opening(arr, morphology.disk(3))

    arr = morphology.remove_small_objects(arr, min_size=4*4, connectivity=0) # remove noise

    # magic
    arr = morphology.binary_closing(arr, morphology.disk(footprint)) # dilation + erosion
    arr = morphology.binary_erosion(arr, morphology.disk(footprint)) # erosion
    
    # remove carbon lines
    if remove_carbon_lacing:
        arr = morphology.remove_small_objects(arr, min_size=8*8, connectivity=0)
        arr = morphology.remove_small_holes(arr, min_size=32*32, connectivity=0)
    arr = morphology.binary_dilation(arr, morphology.disk(footprint)) # dilation
    
    # get background pixels
    bkg = np.invert(morphology.binary_dilation(arr, morphology.disk(footprint*2)) | arr)

    # 2: features
    # 1: background
    # 0: unlabeled
    markers = arr*2 + bkg
    
    # segment using random_walker
    segmented = segmentation.random_walker(img, markers, beta=50, spacing=(5,5), mode='bf')
    segmented = segmented.astype(int) -1

    return arr, segmented


def find_crystals_timepix(img, magnification, spread=0.6, plot=False, **kwargs):
    """Specialized function with better defaults for timepix camera"""
    r = kwargs.get("r", 75)

    # 'offset' determines sensitivity of thresholding
    #   higher = less sensitive to noise
    #   lower = more sensitive to noise
    offset = kwargs.get("offset", 15) 
    footprint = kwargs.get("footprint", 3)
    
    return find_crystals(img=img, 
                         magnification=magnification, 
                         spread=spread, 
                         plot=plot, 
                         footprint=footprint, 
                         offset=offset, 
                         r=r,
                         remove_carbon_lacing=False)


def find_crystals(img, magnification, spread=2.0, plot=False, **kwargs):
    """Function for finding crystals in a low contrast images.
    Used adaptive thresholds to find local features.
    Edges are detected, and rejected, on the basis of a histogram.
    Kmeans clustering is used to spread points over the segmented area.
    
    img: 2d np.ndarray
        Input image to locate crystals on
    magnification: float
        value indicating the magnification used, needed in order to determine the size of the crystals
    spread: float
        Value in micrometer to roughly indicate the desired spread of centroids over individual regions
    plot: bool
        Whether to plot the results or not
    **kwargs:
    keywords to pass to segment_crystals
    """
    img, scale = autoscale(img, maxdim=256)  # scale down for faster
    
    # segment the image, and find objects
    arr, seg = segment_crystals(img, **kwargs)
    
    labels, numlabels = ndimage.label(seg)
    props = measure.regionprops(labels, img)
    
    # calculate the pixel dimensions in micrometer
    px, py = calibration.pixelsize_mag1[magnification] / 1000  # nm -> um
    
    iters = 20
    
    crystals = []
    for prop in props:
        area = prop.area*px*py
        bbox = np.array(prop.bbox)
        
        # origin of the prop
        origin = bbox[0:2]
        
        # edge detection
        if isedge(prop):
            continue

        # number of centroids for kmeans clustering
        nclust = int(area // spread) + 1
            
        if nclust > 1:
            # use skmeans clustering to segment large blobs
            coordinates = np.argwhere(prop.image)
            
            # kmeans needs normalized data (w), store std to calculate coordinates after
            w, std = whiten(coordinates)

            # nclust must be an integer for some reason
            cluster_centroids, closest_centroids = kmeans2(w, nclust, iter=iters, minit='points')

            # convert to image coordinates
            xy = (cluster_centroids*std + origin[0:2]) / scale
            crystals.extend([CrystalPosition(x, y, False, nclust, area, prop.area) for x, y in xy])
        else:
            x, y = prop.centroid
            crystals.append(CrystalPosition(x/scale, y/scale, True, nclust, area, prop.area))
    
    if plot:
        plt.imshow(img)
        plt.contour(seg, [0.5], linewidths=1.2, colors="yellow")
        if len(crystals) > 0:
            x,y = np.array([(crystal.x*scale, crystal.y*scale) for crystal in crystals]).T
            plt.scatter(y,x, color="red")
        ax = plt.axes()
        ax.set_axis_off()
        plt.show()

    return crystals


def main_entry():
    from instamatic.formats import read_image
    import warnings
    warnings.simplefilter('ignore')

    for fn in sys.argv[1:]:
        img, h = read_image(fn)
        
        crystals = find_crystals_timepix(img, h["exp_magnification"], plot=True)
    
        for crystal in crystals:
            print(crystal)


if __name__ == '__main__':
    main_entry()
