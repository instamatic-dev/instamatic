from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage as ndi

from instamatic.formats import read_adsc, write_adsc

# Script to center the beam
#
# Finds the beam center as the maximum intensity
# after applying a gaussian convolution

directory = './smv'
pattern = '*.img'
binning = 2
scale = 1 / binning

# Load data

fns = list(Path(directory).glob(pattern))
n = len(fns)
print(n)


def find_beam_center_blur(z: np.ndarray, sigma: int = 30) -> np.ndarray:
    """Estimate direct beam position by blurring the image with a large
    Gaussian kernel and finding the maximum.

    Parameters
    ----------
    sigma : float
        Sigma value for Gaussian blurring kernel.
    Returns
    -------
    center : np.array
        np.array containing indices of estimated direct beam positon.
    """
    blurred = ndi.gaussian_filter(z, sigma, mode='wrap')
    center = np.unravel_index(blurred.argmax(), blurred.shape)
    return np.array(center)


centers = []

# Loop over all images and center them using the shift function in scipy.ndimage

for i, fn in enumerate(fns):
    print(f'{i} / {n}', end='     \r')
    img, header = read_adsc(str(fn))

    beam_x, beam_y = find_beam_center_blur(img)
    centers.append((beam_x, beam_y))

    # get image center
    center_x, center_y = (np.array(img.shape) / 2).astype(int)

    shift_x = center_x - beam_x
    shift_y = center_y - beam_y

    # shift the beam to the center of the image
    shifted = ndi.shift(img, (shift_x, shift_y))

    if binning > 1:
        shifted = ndi.zoom(shifted, scale)
        pixel_size = float(header['PIXEL_SIZE'])
        header['PIXEL_SIZE'] = str(pixel_size / binning)
        header['SIZE1'] = str(shifted.shape[0])
        header['SIZE2'] = str(shifted.shape[1])
        header['BEAM_CENTER_X'] = str(center_x / binning)
        header['BEAM_CENTER_Y'] = str(center_y / binning)

    out = fn.stem + '-centered.img'
    write_adsc(fname=str(out), data=shifted, header=header)

# Plot centers of the direct beam

beam_x, beam_y = np.array(centers).T
plt.plot(beam_x, beam_y)
plt.xlabel('X axis (px)')
plt.ylabel('Y axis (px)')
plt.show()
