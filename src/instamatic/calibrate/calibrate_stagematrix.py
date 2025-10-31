from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal, Optional

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy import stats
from skimage.registration import phase_cross_correlation

from instamatic import config
from instamatic._typing import AnyPath, int_nm
from instamatic.calibrate.fit import fit_affine_transformation
from instamatic.formats import read_tiff
from instamatic.io import get_new_work_subdirectory
from instamatic.microscope.utils import StagePositionTuple
from instamatic.utils.iterating import pairwise

np.set_printoptions(suppress=True)

Mode = Literal['mag1', 'mag2', 'lowmag', 'samag']

data_drc = config.locations['data']


def get_or_roughly_estimate_pixelsize(mode: Mode, magnification: int) -> float:
    """Get or estimate pixelsize, assuming constant mag * pixelsize in mode."""
    pixel_sizes = config.calibration[mode]['pixelsize']
    pixel_size = pixel_sizes.get(magnification)
    if pixel_size is None:
        products = [mag * pxs for mag, pxs in pixel_sizes.items()]
        if (sum_ := sum(products)) <= 0:
            raise KeyError(f'No legal reference pixel sizes defined for mag={magnification}')
        pixel_size = sum_ / (len(products) * magnification)
    return pixel_size


def stagematrix_to_pixelsize(stagematrix: np.ndarray) -> float:
    """Calculate approximate pixelsize from the stagematrix."""
    return float(np.mean(np.linalg.norm(stagematrix, axis=1)))


def is_outlier(data: list[np.ndarray], threshold: float = 2.0) -> np.ndarray:
    """Simple outlier filter based on zscore.

    `threshold` defines the cut-off value for which zscores are still
    accepted as an inlier. Returns a numpy array of dtype bool.
    """
    zscore = stats.zscore(np.linalg.norm(data, axis=1))
    sel: np.ndarray = abs(zscore) < threshold
    if not np.all(sel):
        print(f'Filtered {len(sel) - np.sum(sel)} outliers.')
    return sel


def cross_correlate_image_pair(img0: np.ndarray, img1: np.ndarray) -> np.ndarray:
    """Cross correlate a pair of images and return translation between them."""
    s, e, p = phase_cross_correlation(img0, img1, upsample_factor=10)
    if np.isclose(e, 1.0, atol=1e-3) and np.allclose(s, 0, atol=1e-3):
        s, e, p = phase_cross_correlation(img0, img1, upsample_factor=10, normalization=None)
    print(f'shift [{s[0]:+6.1f}, {s[1]:+6.1f}] error {e:5.3f} phasediff {p:+6.3f}')
    return s


def calibrate_stage_from_file(drc: AnyPath, plot: bool = False) -> np.ndarray:
    """Calibrate the stage from the saved log/tiff files. This is essentially
    the same function as below, with the exception that it reads the `log.yaml`
    to recalculate the stage matrix.

    Parameters
    ----------
    drc : AnyPath
        Directory containing the `log.yaml` and tiff files.
    plot : bool
        Plot the results of the fitting.

    Returns
    -------
    stagematrix: np.ndarray (2x2)
        Stage matrix used to transform the camera coordinates to stage
        coordinates
    """
    drc = Path(drc)
    with open(drc / 'log.yaml', 'r') as yaml_file:
        d = yaml.full_load(yaml_file)

    binning = d['binning']
    stage_shift_plans = d['args']

    stage_shifts: list[tuple[int_nm, int_nm]] = []
    translations: list[np.ndarray] = []

    for i, (n_shifts, (shift_x, shift_y)) in enumerate(stage_shift_plans):
        images = [read_tiff(drc / f'{i}_{j}.tiff') for j in range(n_shifts)]
        for img0, img1 in pairwise(images):
            translations.append(cross_correlate_image_pair(img0, img1))
            stage_shifts.append((shift_x, shift_y))

    # Filter outliers
    sel: np.ndarray = is_outlier(translations)
    stage_shifts: np.ndarray = np.array(stage_shifts)[sel]
    translations: np.ndarray = np.array(translations)[sel]

    # Fit stagematrix
    fit_result = fit_affine_transformation(translations, stage_shifts, verbose=True)
    r = fit_result.r

    if plot:
        plot_results(r, translations, stage_shifts)

    stagematrix = r / binning
    return stagematrix


def calibrate_stage_from_stageshifts(
    ctrl,
    *stage_shift_plans: tuple[int, tuple[int_nm, int_nm]],
    plot: bool = False,
    drc: Optional[AnyPath] = None,
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
    stage_shift_plans: tuple[int, tuple[int, int]]
        A list of unique shift series to apply to the stage one after another.
        Each stage shift plan consist of a number of steps to apply (int) and
        the stage translation to be applied with each individual step.
    plot: bool
        Plot the fitting result.
    drc: Optional[AnyPath]
        If present, directory where resulting `log.yaml` and tiff will be saved.

    Returns
    -------
    stagematrix: np.ndarray (2x2)
        Stage matrix used to transform the camera coordinates to stage
        coordinates

    Usage
    -----
    >>> x_shifts = (3, (10000, 0))
    >>> y_shifts = (3, (0, 10000))
    >>> stagematrix = calibrate_stage_from_stageshifts(ctrl, x_shifts, y_shifts)
    """
    if drc:
        drc = Path(drc)

    stage_starting_position: StagePositionTuple = ctrl.stage.get()
    stage_shifts: list[tuple[int_nm, int_nm]] = []
    translations: list[np.ndarray] = []

    mag = ctrl.magnification.value
    mode = ctrl.mode.get()
    binning = ctrl.cam.get_binning()

    for i, (n_shifts, (shift_x, shift_y)) in enumerate(stage_shift_plans):
        last_img, _ = ctrl.get_image(out=drc / f'{i}_0.tiff' if drc else None)

        for j in range(1, n_shifts):
            new_x_pos = stage_starting_position.x + j * shift_x
            new_y_pos = stage_starting_position.y + j * shift_y
            ctrl.stage.set_xy_with_backlash_correction(x=new_x_pos, y=new_y_pos)

            img, _ = ctrl.get_image(out=drc / f'{i}_{j}.tiff' if drc else None)

            translations.append(cross_correlate_image_pair(last_img, img))
            stage_shifts.append((shift_x, shift_y))

            print(f'{i:02d}-{j:02d}: {ctrl.stage}')

            last_img = img

        ctrl.stage.set(*stage_starting_position)

    # Filter outliers
    sel: np.ndarray = is_outlier(translations)
    stage_shifts: np.ndarray = np.array(stage_shifts)[sel]
    translations: np.ndarray = np.array(translations)[sel]

    # Fit stagematrix
    fit_result = fit_affine_transformation(translations, stage_shifts, verbose=True)
    r = fit_result.r
    t = fit_result.t

    if drc:
        d = {
            'n_ranges': len(stage_shift_plans),
            'stage_x': stage_starting_position.x,
            'stage_y': stage_starting_position.y,
            'mode': mode,
            'magnification': mag,
            'args': stage_shift_plans,
            'translations': translations,
            'stage_shifts': stage_shifts,
            'r': r,
            't': t,
            'binning': binning,
        }
        yaml.dump(d, open(drc / 'log.yaml', 'w'))

    if plot:
        plot_results(r, translations, stage_shifts)

    stagematrix = r / binning
    return stagematrix


def plot_results(r: np.ndarray, translations: np.ndarray, stage_shifts: np.ndarray) -> None:
    """Show the list of pixel translation from CC (<) vs calculated (>)"""
    calculated = np.dot(stage_shifts, np.linalg.inv(r))
    plt.scatter(*translations.T, marker='<', label='Pixel translations (CC)')
    plt.scatter(*calculated.T, marker='>', label='Calculated pixel coordinates')
    plt.legend()
    plt.show()


def calibrate_stage(
    ctrl,
    mode: Optional[Mode] = None,
    mag: Optional[int] = None,
    overlap: float = 0.5,
    stage_length: int_nm = 40_000,
    min_n_step: int = 3,
    max_n_step: int = 15,
    plot: bool = False,
    drc: Optional[AnyPath] = None,
) -> np.ndarray:
    """Calibrate the stage movement (nm) and the position of the camera
    (pixels) at a specific magnification.

    The stagematrix takes the image binning into account.

    Parameters
    ----------
    mode: Optional[Literal['mag1', 'mag2', 'lowmag', 'samag']]
        Select the imaging mode (mag1/mag2/lowmag/samag).
        If the imaging mode and magnification are not given, the current
        values are used.
    mag: Optional[int]
        Select the imaging magnification.
    overlap: float
        Specify the approximate overlap between images for cross
        correlation.
    stage_length: int_nm
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
    drc: Optional[AnyPath]
        Path to store the raw data (optional).

    Returns
    -------
    stagematrix: np.ndarray (2x2)
        Stage matrix used to transform the camera coordinates to stage
        coordinates
    """

    if mode and mag:
        ctrl.mode.set(mode)
        ctrl.magnification.value = mag
    else:
        mode = ctrl.mode.get()
        mag = ctrl.magnification.value

    print(f'\nCalibrating stagematrix mode=`{mode}` mag={mag}\n')

    camera_shape = ctrl.cam.get_camera_dimensions()
    pixelsize = get_or_roughly_estimate_pixelsize(mode=mode, magnification=mag)

    if pixelsize == 1.0 or pixelsize == 0.0:
        raise ValueError(f'Invalid pixelsize for `{mode}` @ {mag}x -> {pixelsize}')

    displacement = np.array(camera_shape) * pixelsize
    x_step, y_step = displacement * (1 - overlap)

    if x_step * min_n_step > stage_length:
        n_x_step = min_n_step
    else:
        n_x_step = min(int(stage_length // x_step), max_n_step)

    if y_step * min_n_step > stage_length:
        n_y_step = min_n_step
    else:
        n_y_step = min(int(stage_length // y_step), max_n_step)

    stage_shift_plans = (
        (n_x_step, [x_step, 0.0]),
        (n_y_step, [0.0, y_step]),
    )

    stagematrix = calibrate_stage_from_stageshifts(
        ctrl,
        *stage_shift_plans,
        plot=plot,
        drc=drc,
    )

    return stagematrix


def calibrate_stage_all(
    ctrl,
    modes: tuple[Mode] = ('mag1', 'mag2', 'lowmag', 'samag'),
    mag_ranges: dict[Mode, Iterable[int]] = None,
    overlap: float = 0.8,
    stage_length: int_nm = 40_000,
    min_n_step: int = 5,
    max_n_step: int = 9,
    save: bool = False,
) -> dict:
    """Run the stagematrix calibration routine for all magnifications
    specified. Return the updates values for the configuration file.

    Parameters
    ----------
    modes: tuple[Literal['mag1', 'mag2', 'lowmag', 'samag']]
        A tuple of modes to calibrate.
    mag_ranges : dict[Literal['mag1', 'mag2', 'lowmag', 'samag'], Iterable[int]]
        Dictionary with the magnification ranges to calibrate. Format example:
        `mag_ranges = {'lowmag': (100, 200, 300), 'mag1': (1000, 2000, 3000)}`
        If not defined, all mag ranges (`lowmag`, `mag1`) from modes are taken.
    overlap: float
        Specify the approximate overlap between images for cross
        correlation.
    stage_length: int_nm
        Specify the minimum length (in stage coordinates) the calibration
        should cover.
    min_n_step: int
        Specify the minimum number of steps to take along X and Y for the
        calibration.
    max_n_step: int
        Specify the maximum number of steps to take along X and Y for the
        calibration. This is used for higher magnifications.
    save: bool
        Save the data to the data directory.

    Returns
    -------
    config : dict
        Dictionary in the same structure as `instamatic.config` with the
        calibrated values.
    """

    if not mag_ranges:
        mag_ranges = config.microscope.ranges

    cfg = {mode: {} for mode in modes if mode in mag_ranges}

    for mode in modes:
        if mode not in mag_ranges:
            continue

        cfg[mode] = {'stagematrix': {}, 'pixelsize': {}}

        for mag in mag_ranges[mode]:
            msg = f'Calibrating `{mode}` @ {mag}x'
            if save:
                drc = get_new_work_subdirectory(f'stagematrix_{mode}')
                msg += f' -> {drc}'
            else:
                drc = None

            try:
                stagematrix = calibrate_stage(
                    ctrl,
                    mode=mode,
                    mag=mag,
                    overlap=overlap,
                    stage_length=stage_length,
                    min_n_step=min_n_step,
                    max_n_step=max_n_step,
                    drc=drc,
                )
            except ValueError as e:  # raises if pixelsize is 0 or 1.0
                print(e)
                continue

            cfg[mode]['pixelsize'][mag] = stagematrix_to_pixelsize(stagematrix)
            cfg[mode]['stagematrix'][mag] = stagematrix.round(4).flatten().tolist()

    print('\nUpdate this config file:\n  ', config.locations['calibration'])

    print(yaml.dump(cfg))

    return cfg


def main_entry() -> None:
    import argparse

    description = """Run the stagematrix calibration routine for all magnifications
specified. Return the updates values for the configuration file.

Calibrate the stage movement (nm) and the position of the camera
(pixels) at a specific magnification.

The stagematrix takes the image binning into account."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-m',
        '--mode',
        dest='mode',
        type=str,
        help=(
            'Select the imaging mode (mag1/mag2/lowmag/samag). '
            'If `all` is specified, all imaging modes+mags are calibrated.'
            'If the imaging mode and magnification are not given, the current'
            'values are used.'
        ),
    )

    parser.add_argument(
        '-k',
        '--mag',
        dest='mags',
        type=int,
        nargs='+',
        metavar='K',
        help='Select the imaging magnification(s).',
    )

    parser.add_argument(
        '-A',
        '--all_mags',
        action='store_true',
        dest='all_mags',
        help='Run calibration routine for all mags over selected mode.',
    )

    parser.add_argument(
        '-v',
        '--overlap',
        dest='overlap',
        type=float,
        metavar='X',
        help='Specify the approximate overlap between images for cross correlation.',
    )

    parser.add_argument(
        '-l',
        '--stage_length',
        dest='stage_length',
        type=int,
        help=(
            'Specify the minimum length (in stage coordinates) the calibration should cover.'
        ),
    )

    parser.add_argument(
        '-a',
        '--min_n_steps',
        dest='min_n_step',
        type=int,
        metavar='N',
        help='Specify the minimum number of steps to take along X and Y for the calibration.',
    )

    parser.add_argument(
        '-b',
        '--max_n_steps',
        dest='max_n_step',
        type=int,
        metavar='N',
        help=(
            'Specify the maximum number of steps to take along X and Y for the '
            'calibration. This is used for higher magnifications.'
        ),
    )

    parser.add_argument(
        '-s',
        '--save',
        action='store_true',
        dest='save',
        help=f'Save the data to the data directory [{data_drc}].',
    )

    parser.set_defaults(
        mode=(),
        mags=(),
        overlap=0.8,
        stage_length=40_000,
        min_n_step=5,
        max_n_step=9,
        plot=False,
        drc=None,
        save=False,
    )

    options = parser.parse_args()

    mode: Optional[Mode] = options.mode
    mags: Optional[list[int]] = options.mags

    from instamatic import controller

    ctrl = controller.initialize()

    if not mode:
        mode: Mode = ctrl.mode.get()
    if not mags:
        mags: list[int] = [
            ctrl.magnification.get(),
        ]

    kwargs = {
        'overlap': options.overlap,
        'stage_length': options.stage_length,
        'min_n_step': options.min_n_step,
        'max_n_step': options.max_n_step,
        'save': options.save,
    }

    if mode != 'all':
        if options.all_mags:
            kwargs['modes'] = (mode,)
        else:
            kwargs['mag_ranges'] = {mode: mags}
    calibrate_stage_all(ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
