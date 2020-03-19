from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy import stats
from skimage.feature import register_translation

from .fit import fit_affine_transformation
from instamatic import config
from instamatic.formats import read_tiff
from instamatic.formats import write_tiff
from instamatic.image_utils import rotate_image

np.set_printoptions(suppress=True)

write = False


def getImage(ctrl, drc, j, i, mode, mag):
    if write:
        img, h = ctrl.getImage()
        if drc:
            write_tiff(drc / f'{j}_{i}.tiff', img)
    else:
        img, h = read_tiff(drc / f'{j}_{i}.tiff')
        img = rotate_image(img, mode=mode, mag=mag)

    return img, h


def get_outlier_filter(data, threshold: float = 2.0) -> list:
    """Simple outlier filter based on zscore.

    `threshold` defines the cut-off value for which zscores are still
    accepted as an inlier. Returns an boolean numpy array.
    """
    zscore = stats.zscore(np.linalg.norm(data, axis=1))
    sel = abs(zscore) < threshold

    if not np.all(sel):
        print(f'Filtered {len(sel) - np.sum(sel)} outliers.')

    return sel


def calibrate_stage_from_stagepos(ctrl,
                                  *args,
                                  plot: bool = False,
                                  drc=None,
                                  ) -> np.array:
    """Run the calibration algorithm on the given X/Y ranges. An image will be
    taken at each position for cross correlation with the previous. An affine
    transformation matrix defines the relation between the pixel shift and the
    difference in stage position.

    The stagematrix takes the image binning into account.

    Parameters
    ----------
    ctrl: `TEMController`
        TEM control object to allow stage movement to different coordinates.
    ranges: np.array (Nx2)
        Each range is a List of tuples with X/Y stage movements (i.e.
        displacements from the current position). Multiple ranges can be
        specified to be run in sequence.
    plot: bool
        Plot the fitting result.

    Returns
    -------
    stagematrix: np.ndarray (2x2)
        Stage matrix used to transform the camera coordinates to stage
        coordinates

    Usage
    -----
    >>> x_shifts = [(0, 0), (10000, 0), (20000, 0)]
    >>> y_shifts = [(0, 0), (0, 10000), (0, 20000)]
    >>> stagematrix = calibrate_stage_from_stagepos(ctrl, x_shifts, y_shifts)
    """
    if drc:
        drc = Path(drc)

    stage_x, stage_y = ctrl.stage.xy

    stage_shifts = []  # um
    translations = []  # pixels

    mag = ctrl.magnification.value
    mode = ctrl.mode
    binning = ctrl.cam.getBinning()[0]

    pairs = []

    for i, (n_steps, step) in enumerate(args):
        last_img, _ = getImage(ctrl, drc, 0, i, mode, mag)
        current_stage_pos = ctrl.stage
        dx, dy = step

        for j in range(1, n_steps + 1):
            new_x_pos = current_stage_pos.x + dx
            new_y_pos = current_stage_pos.y + dy
            ctrl.stage.set_xy_with_backlash_correction(x=new_x_pos, y=new_y_pos)

            img, _ = getImage(ctrl, drc, j, i, mode, mag)

            pairs.append((last_img, img))
            stage_shifts.append((dx, dy))

            current_stage_pos = ctrl.stage

            print(current_stage_pos)

            last_img = img

        # return to original position
        ctrl.stage.xy = (stage_x, stage_y)

    # Cross correlation
    translations = []
    for img0, img1 in pairs:
        translation, error, phasediff = register_translation(img0, img1, upsample_factor=10)
        print(f'shift {translation} error {error:.4f} phasediff {phasediff:.4f}')
        translations.append(translation)

    # Filter outliers
    sel = get_outlier_filter(translations)
    stage_shifts = np.array(stage_shifts)[sel]
    translations = np.array(translations)[sel]

    # Fit stagematrix
    fit_result = fit_affine_transformation(translations, stage_shifts, verbose=True)
    r = fit_result.r / binning
    t = fit_result.t

    if write:
        if drc:
            d = {
                'n_ranges': len(args),
                'stage_x': stage_x,
                'stage_y': stage_y,
                'mode': mode,
                'magnification': mag,
                'args': args,
                'translations': translations,
                'stage_shifts': stage_shifts,
                'r': r,
                't': t,
            }
            yaml.dump(d, open(drc / 'log.yaml', 'w'))

    if plot:
        r_i = np.linalg.inv(r)
        translations_ = np.dot(stage_shifts, r_i)

        plt.scatter(*translations.T, marker='<', label='Pixel translations (CC)')
        plt.scatter(*translations_.T, marker='>', label='Calculated pixel coordinates')
        plt.legend()

    stagematrix = r

    return stagematrix


def calibrate_stage(ctrl,
                    mode: str = None,
                    mag: int = None,
                    overlap: float = 0.5,
                    stage_length: int = 40_000,
                    min_n_step: int = 3,
                    max_n_step: int = 15,
                    plot: bool = False,
                    drc: str = None,
                    ) -> np.array:
    """Calibrate the stage movement (nm) and the position of the camera
    (pixels) at a specific magnification.

    The stagematrix takes the image binning into account.

    Parameters
    ----------
    mode: str
        Select the imaging mode (mag1/mag2/lowmag/samag).
        If the imaging mode and magnification are not given, the current
        values are used.
    mag: int
        Select the imaging magnification.
    overlap: float
        Specify the approximate overlap between images for cross
        correlation.
    stage_length: int
        Specify the minimum length (in stage coordinates) the calibration
        should cover.
    min_n_step: int
        Specify the minimum number of steps to take along X and Y for the
        calibration.
    max_n_step: int
        Specify the maximum number of steps to take along X and Y for the
        calibration. This is used for higher magnifications.
    plot: bool
        Plot the fitting result.
    drc: str
        Path to store the raw data (optional).

    Returns
    -------
    stagematrix: np.ndarray (2x2)
        Stage matrix used to transform the camera coordinates to stage
        coordinates
    """

    if mode and mag:
        ctrl.mode = mode
        ctrl.magnification.value = mag
    else:
        mode = ctrl.mode
        mag = ctrl.magnification.value

    shape = config.camera.dimensions
    pixelsize = config.calibration[mode]['pixelsize'][mag]

    if pixelsize == 1.0 or pixelsize == 0.0:
        raise ValueError(f'Invalid pixelsize for `{mode}` @ {mag}x -> {pixelsize}')

    displacement = np.array(shape) * pixelsize
    x_step, y_step = displacement * (1 - overlap)

    if x_step * min_n_step > stage_length:
        n_x_step = min_n_step
    else:
        n_x_step = min(stage_length // x_step, max_n_step)

    if y_step * min_n_step > stage_length:
        n_y_step = min_n_step
    else:
        n_y_step = min(stage_length // y_step, max_n_step)

    args = (
        (n_x_step, [x_step, 0]),
        (n_y_step, [0, y_step]),
    )

    stagematrix = calibrate_stage_from_stagepos(
        ctrl,
        *args,
        plot=plot,
        drc=drc,
    )

    return stagematrix
