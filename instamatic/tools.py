from instamatic.formats import read_tiff, write_tiff
import sys, os
import numpy as np
import glob
from skimage import exposure
from scipy import ndimage, interpolate


def find_subranges(lst: list) -> (int, int):
    """Takes a range of sequential numbers (possibly with gaps) and 
    splits them in sequential sub-ranges defined by the minimum and maximum value.
    """
    from operator import itemgetter
    from itertools import groupby

    for key, group in groupby(enumerate(lst), lambda i: i[0] - i[1]):
        group = list(map(itemgetter(1), group))
        yield min(group), max(group)


def autoscale(img: np.ndarray, maxdim: int=512) -> (np.ndarray, float):
    """Scale the image to fit the maximum dimension given by `maxdim`
    Returns the scaled image, and the image scale"""
    if maxdim:
        scale = float(maxdim) / max(img.shape)

    return ndimage.zoom(img, scale, order=1), scale


def imgscale(img: np.ndarray, scale: float) -> np.ndarray:
    """Scale the image by the given scale"""
    if scale == 1:
        return img
    return ndimage.zoom(img, scale, order=1)


def denoise(img: np.ndarray, sigma: int=3, method: str="median") -> np.ndarray:
    """Denoises the image using a gaussian or median filter.
    median filter is better at preserving edges"""
    if method == "gaussian":
        return ndimage.gaussian_filter(img, sigma)
    else:
        return ndimage.median_filter(img, sigma)


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """Enhance contrast by histogram equalization"""
    return exposure.equalize_hist(img)


def find_peak_max(arr: np.ndarray, sigma: int, m: int=50, w: int=10, kind: int=3) -> (float, float):
    """Find the index of the pixel corresponding to peak maximum in 1D pattern `arr`
    First, the pattern is smoothed using a gaussian filter with standard deviation `sigma`
    The initial guess takes the position corresponding to the largest value in the resulting pattern
    A window of size 2*w+1 around this guess is taken and expanded by factor `m` to to interpolate the
    pattern to get the peak maximum position with subpixel precision."""
    y1 = ndimage.filters.gaussian_filter1d(arr, sigma)
    c1 = np.argmax(y1)  # initial guess for beam center

    win_len = 2*w+1
    
    try:
        r1 = np.linspace(c1-w, c1+w, win_len)
        f  = interpolate.interp1d(r1, y1[c1-w: c1+w+1], kind=kind)
        r2 = np.linspace(c1-w, c1+w, win_len*m)  # extrapolate for subpixel accuracy
        y2 = f(r2)
        c2 = np.argmax(y2) / m  # find beam center with `m` precision
    except ValueError as e:  # if c1 is too close to the edges, return initial guess
        return c1

    return c2 + c1 - w


def find_beam_center(img: np.ndarray, sigma: int=30, m: int=100, kind: int=3) -> (float, float):
    """Find the center of the primary beam in the image `img`
    The position is determined by summing along X/Y directions and finding the position along the two
    directions independently. Uses interpolation by factor `m` to find the coordinates of the pimary
    beam with subpixel accuracy."""
    xx = np.sum(img, axis=1)
    yy = np.sum(img, axis=0)
    
    cx = find_peak_max(xx, sigma, m=m, kind=kind) 
    cy = find_peak_max(yy, sigma, m=m, kind=kind) 

    center = np.array([cx, cy])
    return center


def get_files(file_pat: str) -> list:
    """Grab files from globbing pattern or stream file"""
    from instamatic.formats import read_ycsv
    if os.path.exists(file_pat):
        root, ext = os.path.splitext(file_pat)
        if ext.lower() == ".ycsv":
            df, d = read_ycsv(file_pat)
            fns = df.index.tolist()
        else:
            f = open(file_pat, "r")
            fns = [line.split("#")[0].strip() for line in f if not line.startswith("#")]
    else:
        fns = glob.glob(file_pat)

    if len(fns) == 0:
        raise IOError("No files matching '{}' were found.".format(file_pat))

    return fns


def printer(data) -> None:
    """Print things to stdout on one line dynamically"""
    sys.stdout.write("\r\x1b[K"+data.__str__())
    sys.stdout.flush()


def find_defocused_image_center(image: np.ndarray, treshold: int=1):
    """Find the center of a defocused diffraction pattern"""
    X = np.mean(image, axis=0)
    Y = np.mean(image, axis=1)
    im_mean = np.mean(X)
    rads = np.zeros(2)
    center = np.zeros(2)
    for n, XY in enumerate([X,Y]):
        over = np.where(XY>(im_mean*treshold))[0]
        rads[n] = (over[-1] - over[0])/2
        center[n] = over[0] + rads[n]
    return center, rads

