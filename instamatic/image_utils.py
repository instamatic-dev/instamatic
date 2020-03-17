import numpy as np

from instamatic import config


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
