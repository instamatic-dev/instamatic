from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy import stats
from skimage.registration import phase_cross_correlation

from instamatic import config
from instamatic.calibrate.fit import fit_affine_transformation
from instamatic.formats import read_tiff
from instamatic.formats import write_tiff
from instamatic.image_utils import rotate_image
from instamatic.io import get_new_work_subdirectory

np.set_printoptions(suppress=True)

data_drc = config.locations['data']


def stagematrix_to_pixelsize(stagematrix: np.array) -> float:
    """Calculate approximate pixelsize from the stagematrix."""
    return np.mean(np.linalg.norm(stagematrix, axis=1))


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


def cross_correlate_image_pairs(pairs: tuple) -> list:
    """Cross correlate image pairs."""
    translations = []
    for img0, img1 in pairs:
        translation, error, phasediff = phase_cross_correlation(img0, img1, upsample_factor=10)
        print(f'shift {translation} error {error:.4f} phasediff {phasediff:.4f}')
        translations.append(translation)
    return translations


def calibrate_stage_from_file(drc: str, plot: bool = False):
    """Calibrate the stage from the saved log/tiff files. This is essentially
    the same function as below, with the exception that it reads the `log.yaml`
    to recalculate the stage matrix.

    Parameters
    ----------
    drc : str
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
    fn = drc / 'log.yaml'

    d = yaml.full_load(open(fn, 'r'))

    binning = d['binning']
    args = d['args']

    stage_shifts = []  # um
    pairs = []

    for i, (n_steps, step) in enumerate(args):
        dx, dy = step

        for j in range(0, n_steps):
            img, _ = read_tiff(drc / f'{i}_{j}.tiff')

            if j > 0:
                pairs.append((last_img, img))
                stage_shifts.append((dx, dy))

            last_img = img

    translations = cross_correlate_image_pairs(pairs)

    # Filter outliers
    sel = get_outlier_filter(translations)
    stage_shifts = np.array(stage_shifts)[sel]
    translations = np.array(translations)[sel]

    # Fit stagematrix
    fit_result = fit_affine_transformation(translations, stage_shifts, verbose=True)
    r = fit_result.r
    t = fit_result.t

    if plot:
        r_i = np.linalg.inv(r)
        translations_ = np.dot(stage_shifts, r_i)

        plt.scatter(*translations.T, marker='<', label='Pixel translations (CC)')
        plt.scatter(*translations_.T, marker='>', label='Calculated pixel coordinates')
        plt.legend()
        plt.show()

    stagematrix = r / binning

    return stagematrix


def calibrate_stage_from_stageshifts(ctrl,
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
        Each range is a List of tuples with X/Y stage shifts (i.e.
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
    >>> x_shifts = [3, (10000, 0)]
    >>> y_shifts = [3, (0, 10000)]
    >>> stagematrix = calibrate_stage_from_stageshifts(ctrl, x_shifts, y_shifts)
    """
    if drc:
        drc = Path(drc)

    stage_x, stage_y = ctrl.stage.xy

    stage_shifts = []  # um

    mag = ctrl.magnification.value
    mode = ctrl.mode.get()
    binning = ctrl.cam.getBinning()

    pairs = []

    for i, (n_steps, step) in enumerate(args):
        j = 0

        current_stage_pos = ctrl.stage
        dx, dy = step

        last_img, _ = ctrl.get_image()

        if drc:
            write_tiff(drc / f'{i}_{j}.tiff', last_img)

        for j in range(1, n_steps):
            new_x_pos = current_stage_pos.x + dx
            new_y_pos = current_stage_pos.y + dy
            ctrl.stage.set_xy_with_backlash_correction(x=new_x_pos, y=new_y_pos)

            img, _ = ctrl.get_image()

            if drc:
                write_tiff(drc / f'{i}_{j}.tiff', img)

            pairs.append((last_img, img))
            stage_shifts.append((dx, dy))

            current_stage_pos = ctrl.stage

            print(f'{i:02d}-{j:02d}: {current_stage_pos}')

            last_img = img

        # return to original position
        ctrl.stage.xy = (stage_x, stage_y)

    translations = cross_correlate_image_pairs(pairs)

    # Filter outliers
    sel = get_outlier_filter(translations)
    stage_shifts = np.array(stage_shifts)[sel]
    translations = np.array(translations)[sel]

    # Fit stagematrix
    fit_result = fit_affine_transformation(translations, stage_shifts, verbose=True)
    r = fit_result.r
    t = fit_result.t

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
            'binning': binning,
        }
        yaml.dump(d, open(drc / 'log.yaml', 'w'))

    if plot:
        r_i = np.linalg.inv(r)
        translations_ = np.dot(stage_shifts, r_i)

        plt.scatter(*translations.T, marker='<', label='Pixel translations (CC)')
        plt.scatter(*translations_.T, marker='>', label='Calculated pixel coordinates')
        plt.legend()
        plt.show()

    stagematrix = r / binning

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
        ctrl.mode.set(mode)
        ctrl.magnification.value = mag
    else:
        mode = ctrl.mode.get()
        mag = ctrl.magnification.value

    print(f'\nCalibrating stagematrix mode=`{mode}` mag={mag}\n')

    camera_shape = ctrl.cam.getCameraDimensions()
    pixelsize = config.calibration[mode]['pixelsize'][mag]

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

    args = (
        (n_x_step, [x_step, 0.0]),
        (n_y_step, [0.0, y_step]),
    )

    stagematrix = calibrate_stage_from_stageshifts(
        ctrl,
        *args,
        plot=plot,
        drc=drc,
    )

    return stagematrix


def calibrate_stage_all(ctrl,
                        modes=('mag1', 'lowmag'),
                        mag_ranges: dict = None,
                        overlap: float = 0.8,
                        stage_length: int = 40_000,
                        min_n_step: int = 5,
                        max_n_step: int = 9,
                        save: bool = False,
                        ) -> dict:
    """Run the stagematrix calibration routine for all magnifications
    specified. Return the updates values for the configuration file.

    Parameters
    ----------
    mag_ranges : dict
        Dictionary with the mag ranges to calibrate. Format example:
        `mag_ranges = {'lowmag': (100, 200, 300), 'mag1': (1000, 2000, 3000)}`
        If not defined, all mag ranges (`lowmag`, `mag1`) as defined above are taken.
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
                stagematrix = calibrate_stage(ctrl,
                                              mode=mode,
                                              mag=mag,
                                              overlap=overlap,
                                              min_n_step=min_n_step,
                                              max_n_step=max_n_step,
                                              drc=drc,
                                              )
            except ValueError as e:  # raises if pixelsize is 0 or 1.0
                print(e)
                continue

            cfg[mode]['pixelsize'][mag] = float(stagematrix_to_pixelsize(stagematrix))
            cfg[mode]['stagematrix'][mag] = stagematrix.round(4).flatten().tolist()

    print('\nUpdate this config file:\n  ', config.locations['calibration'])

    print(yaml.dump(cfg))

    return cfg


def main_entry():
    import argparse

    description = """Run the stagematrix calibration routine for all magnifications
specified. Return the updates values for the configuration file.

Calibrate the stage movement (nm) and the position of the camera
(pixels) at a specific magnification.

The stagematrix takes the image binning into account."""

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-m', '--mode', dest='mode', type=str,
                        help=('Select the imaging mode (mag1/mag2/lowmag/samag). '
                              'If `all` is specified, all imaging modes+mags are calibrated.'
                              'If the imaging mode and magnification are not given, the current'
                              'values are used.'))

    parser.add_argument('-k', '--mag', dest='mags', type=int, nargs='+', metavar='K',
                        help='Select the imaging magnification(s).')

    parser.add_argument('-A', '--all_mags', action='store_true', dest='all_mags',
                        help='Run calibration routine for all mags over selected mode.')

    parser.add_argument('-v', '--overlap', dest='overlap', type=float, metavar='X',
                        help=('Specify the approximate overlap between images for cross '
                              'correlation.'))

    parser.add_argument('-l', '--stage_length', dest='stage_length', type=int,
                        help=('Specify the minimum length (in stage coordinates) the calibration '
                              'should cover.'))

    parser.add_argument('-a', '--min_n_steps', dest='min_n_step', type=int, metavar='N',
                        help=('Specify the minimum number of steps to take along X and Y for the '
                              'calibration.'))

    parser.add_argument('-b', '--max_n_steps', dest='max_n_step', type=int, metavar='N',
                        help=('Specify the maximum number of steps to take along X and Y for the '
                              'calibration. This is used for higher magnifications.'))

    parser.add_argument('-s', '--save', action='store_true', dest='save',
                        help=f'Save the data to the data directory [{data_drc}].')

    parser.set_defaults(mode=(),
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

    mode = options.mode
    mags = options.mags

    from instamatic import TEMController
    ctrl = TEMController.initialize()

    if not mode:
        mode = ctrl.mode.get()
    if not mags:
        mags = (ctrl.magnification.get(), )

    kwargs = {
        'overlap': options.overlap,
        'stage_length': options.stage_length,
        'min_n_step': options.min_n_step,
        'max_n_step': options.max_n_step,
    }

    if mode == 'all':
        calibrate_stage_all(
            ctrl,
            save=options.save,
            **kwargs,
        )
    elif options.all_mags:
        calibrate_stage_all(
            ctrl,
            mode=mode,
            save=options.save,
            **kwargs,
        )
    else:
        calibrate_stage_all(
            ctrl,
            mag_ranges={mode: mags},
            save=options.save,
            **kwargs,
        )


if __name__ == '__main__':
    main_entry()
