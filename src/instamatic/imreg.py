from __future__ import annotations

import numpy as np
from numpy.fft import fft2, ifft2


def translation(
    im0,
    im1,
    limit_shift: bool = False,
    return_fft: bool = False,
):
    """Return translation vector to register images.

    Parameters
    ----------
    im0, im1 : np.array
        The two images to compare
    limit_shift : bool
        Limit the maximum shift to the minimum array length or width.
    return_fft : bool
        Whether to additionally return the cross correlation array between the 2 images

    Returns
    -------
    shift: list
        Return the 2 coordinates defining the determined image shift
    """
    f0 = fft2(im0)
    f1 = fft2(im1)
    ir = abs(ifft2((f0 * f1.conjugate()) / (abs(f0) * abs(f1))))
    shape = ir.shape

    if limit_shift:
        min_shape = min(shape)
        shift = int(min_shape / 2)
        ir2 = np.roll(ir, (shift, shift), (0, 1))
        ir2 = ir2[:min_shape, :min_shape]
        t0, t1 = np.unravel_index(np.argmax(ir2), ir2.shape)
        t0 -= shift
        t1 -= shift
    else:
        t0, t1 = np.unravel_index(np.argmax(ir), shape)
        if t0 > shape[0] // 2:
            t0 -= shape[0]
        if t1 > shape[1] // 2:
            t1 -= shape[1]

    if return_fft:
        return [t0, t1], ir
    else:
        return [t0, t1]
