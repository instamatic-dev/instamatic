from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage import exposure

from instamatic import config


def autoscale(img: np.ndarray, maxdim: int = 512) -> (np.ndarray, float):
    """Scale the image to fit the maximum dimension given by `maxdim` Returns
    the scaled image, and the image scale."""
    if maxdim:
        scale = float(maxdim) / max(img.shape)

    return ndimage.zoom(img, scale, order=1), scale


def imgscale(img: np.ndarray, scale: float) -> np.ndarray:
    """Scale the image by the given scale."""
    if scale == 1:
        return img
    return ndimage.zoom(img, scale, order=1)


def rotate_image(arr, mode: str, mag: int) -> np.array:
    """Rotate and flip image according to the configuration for that mode/mag.
    This ensures all images have the same orientation across mag modes/ranges.

    Parameters
    ----------
    arr : np.array
        2D image array.
    mode : str
        Magnification mode
    mag : int
        Magnification value.

    Returns
    -------
    arr : np.array
        Flipped and rotated image array
    """
    try:
        k = config.calibration[mode]['rot90'][mag]
    except KeyError:
        k = 0

    flipud = config.calibration[mode].get('flipud', False)
    fliplr = config.calibration[mode].get('fliplr', False)

    if flipud:
        arr = np.flipud(arr)
    if fliplr:
        arr = np.fliplr(arr)

    arr = np.rot90(arr, k)

    return arr


def bin_ndarray(ndarray, new_shape=None, binning=1, operation='mean'):
    """Bins an ndarray in all axes based on the target shape, by summing or
    averaging. If no target shape is given, calculate the target shape by the
    given binning.

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
    if not new_shape:
        shape_x, shape_y = ndarray.shape
        new_shape = int(shape_x / binning), int(shape_y / binning)

    if new_shape == ndarray.shape:
        return ndarray

    operation = operation.lower()
    if operation not in ['sum', 'mean']:
        raise ValueError('Operation not supported.')
    if ndarray.ndim != len(new_shape):
        raise ValueError(f'Shape mismatch: {ndarray.shape} -> {new_shape}')
    compression_pairs = [(d, c // d) for d, c in zip(new_shape, ndarray.shape)]
    flattened = [val for pair in compression_pairs for val in pair]
    ndarray = ndarray.reshape(flattened)
    for i in range(len(new_shape)):
        op = getattr(ndarray, operation)
        ndarray = op(-1 * (i + 1))
    return ndarray
