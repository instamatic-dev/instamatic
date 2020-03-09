import matplotlib.pyplot as plt
import numpy as np
from skimage.feature import register_translation

from .fit import fit_affine_transformation
from instamatic import config


def calibrate_stage_from_stagepos(ctrl,
                                  *ranges,
                                  plot: bool = False,
                                  ) -> np.array:
    """Run the calibration algorithm on the given X/Y ranges. An image will be
    taken at each position for cross correlation with the previous. An affine
    transformation matrix defines the relation between the pixel shift and the
    difference in stage position.

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
    stage_x, stage_y = ctrl.stage.xy

    stage_shifts = []  # um
    translations = []  # pixels

    for rng in ranges:
        last_image = None

        for i, (dx, dy) in enumerate(rng):
            new_x_pos = stage_x + dx
            new_y_pos = stage_y + dy
            ctrl.stage.set_xy_with_backlash_correction(x=new_x_pos, y=new_y_pos)

            print(i, ctrl.stage)

            img, h = ctrl.getImage()

            if i > 0:
                translation, error, phasediff = register_translation(last_image, img)
                print(f'shift {translation} error {error:.4f} phasediff {phasediff:.4f}')

                translations.append(translation)
                stage_shifts.append((dx, dy))

            last_image = img
        print()

    # return to original position
    ctrl.stage.xy = (stage_x, stage_y)

    stage_shifts = np.array(stage_shifts)
    translations = np.array(translations)

    r, t = fit_affine_transformation(stage_shifts, translations, verbose=True)

    if plot:
        r_i = np.linalg.inv(r)
        translations_ = np.dot(stage_shifts, r_i)

        plt.scatter(*translations.T, label='Pixel translations (CC)')
        plt.scatter(*translations_.T, label='Calculated pixel coordinates')
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
                    ) -> np.array:
    """Calibrate the stage movement (nm) and the position of the camera
    (pixels) at a specific magnification.

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
        x_pos = np.arange(min_n_step) * x_step
    else:
        x_pos = np.arange(0, stage_length, x_step)[:max_n_step]

    x_pos = np.stack((x_pos, np.zeros_like(x_pos))).T

    if y_step * min_n_step > stage_length:
        y_pos = np.arange(min_n_step) * y_step
    else:
        y_pos = np.arange(0, stage_length, y_step)[:max_n_step]

    y_pos = np.stack((y_pos, np.zeros_like(y_pos))).T

    r, t = calibrate_stage_from_stagepos(ctrl, x_pos, y_pos, plot=plot)
    return r
