from instamatic.formats import read_tiff, write_tiff
import sys, os
import numpy as np
import glob
from skimage import exposure
from skimage.measure import regionprops
from scipy import ndimage, interpolate


def to_xds_untrusted_area(kind: str, coords: list) -> str:
    """Takes coordinate list and turns it into an XDS untrusted area
    kind: rectangle, ellipse, quadrilateral
    coords: coordinates corresponding to the untrusted area

    For definitions, see:
    http://xds.mpimf-heidelberg.mpg.de/html_doc/xds_parameters.html#UNTRUSTED_ELLIPSE=

    `coords` corresponds to a list of (x, y) coordinates of the corners of the quadrilateral / rectangle
    """
    if kind == "quadrilateral":
        coords = np.round(coords).astype(int)
        s = "UNTRUSTED_QUADRILATERAL="
        for x, y in coords:   
            s += f" {y} {x}"  # coords are flipped in XDS
        
        return s

    elif kind == "rectangle":
        coords = np.round(coords).astype(int)
        s = "UNTRUSTED_RECTANGLE="
        (x1, y1), (x2, y2) = coords
        s += f" {y1} {y2} {x1} {x2}"  # coords are flipped in XDS
        
        return s

    elif kind == "ellipse":
        coords = np.round(coords).astype(int)
        s = "UNTRUSTED_ELLIPSE="
        (x1, y1), (x2, y2) = coords
        s += f" {y1} {y2} {x1} {x2}"  # coords are flipped in XDS
        
        return s

    else:
        raise ValueError("Only quadrilaterals are supported for now")


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


def find_beam_center_with_beamstop(img, z: int=None, method="thresh", plot=False) -> (float, float):
    """Find the beam center when a beam stop is present. 

    methods: gauss, thresh

    `thresh` uses a threshold to segment the image. The largest blob then corresponds to the
    primary beam. The center of the bounding box of the blob defines the beam center.

    `gauss` applies a gaussian filter with a very large standard deviation in an attempt
    to smooth out the beam stop. The position of the largest pixel corresponds to the 
    beam center.

    z = thresh: percentile to segment the image at (99)
        gauss: standard deviation for the gaussian blurring (50)"""
    
    if method == "gauss":
        if not z:
            z = 50
        blurred = ndimage.filters.gaussian_filter(img, z)
        cx, cy = np.unravel_index(blurred.argmax(), blurred.shape)
    
    elif method == "thresh":
        if not z:
            z = 99
        seg = img > np.percentile(img, z)
        labeled, _ = ndimage.label(seg)
        
        props = regionprops(labeled)
        props.sort(key=lambda x: x.area, reverse=True)
        prop = props[0]

        dx = (prop.bbox[0] + prop.bbox[2]) / 2
        dy = (prop.bbox[1] + prop.bbox[3]) / 2

        if plot:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            fig, (ax1, ax2) = plt.subplots(ncols=2)

            ax1.imshow(labeled, vmax=5)
            ax2.imshow(img, vmax=np.percentile(img, z))

            ax1.scatter(dy, dx)
            ax2.scatter(dy, dx)

            plt.title(f"Beam center: {dx:.2f} {dy:.2f}")

            minr, minc, maxr, maxc = prop.bbox

            rect = mpatches.Rectangle((minc, minr), maxc - minc, maxr - minr, fill=False, edgecolor='red', linewidth=2)
            ax2.add_patch(rect)
            
            plt.show()
    
    return np.array((dx, dy))


def bin_ndarray(ndarray, new_shape, operation='mean'):
    """
    Bins an ndarray in all axes based on the target shape, by summing or
        averaging.

    Number of output dimensions must match number of input dimensions and 
        new axes must divide old ones.

    Example
    -------
    >>> m = np.arange(0,100,1).reshape((10,10))
    >>> n = bin_ndarray(m, new_shape=(5,5), operation='sum')
    >>> print(n)

    [[ 22  30  38  46  54]
     [102 110 118 126 134]
     [182 190 198 206 214]
     [262 270 278 286 294]
     [342 350 358 366 374]]

    """
    operation = operation.lower()
    if not operation in ['sum', 'mean']:
        raise ValueError("Operation not supported.")
    if ndarray.ndim != len(new_shape):
        raise ValueError("Shape mismatch: {} -> {}".format(ndarray.shape,
                                                           new_shape))
    compression_pairs = [(d, c//d) for d,c in zip(new_shape,
                                                  ndarray.shape)]
    flattened = [l for p in compression_pairs for l in p]
    ndarray = ndarray.reshape(flattened)
    for i in range(len(new_shape)):
        op = getattr(ndarray, operation)
        ndarray = op(-1*(i+1))
    return ndarray


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


def get_acquisition_time(timestamps: tuple, exp_time: float, plot: bool=True, savefig: bool=True, fn: str=None) -> object:
    """take a list of timestamps and return the acquisition time and overhead
    exp_time in s"""

    from scipy.stats import linregress
    from types import SimpleNamespace

    timestamps = np.array(timestamps)

    x = np.arange(len(timestamps))
    res = linregress(x, timestamps)

    y = x * res.slope + res.intercept
    
    acq_time = res.slope * 1000
    overhead = acq_time - exp_time

    if plot or savefig:
        import matplotlib.pyplot as plt
        plt.plot(x, y, color="red")
        plt.scatter(x, timestamps, color="blue", marker="+")
        plt.title(f"f(x)={res.intercept:.3f} + {res.slope:.3f}*x\nAcq. time: {acq_time:.0f} ms | Exp. time: {exp_time:.0f} ms | overhead: {overhead:.0f} ms")
        plt.xlabel("Frame number")
        plt.ylabel("Timestamp (s)")

        if savefig:
            if not fn:
                fn = "acquisition_time.png"
            plt.savefig(fn, dpi=150)
        if plot:
            plt.show()
        plt.clf()

    return SimpleNamespace(acquisition_time=acq_time/1000, exposure_time=exp_time/1000, overhead=overhead/1000, units="s")

