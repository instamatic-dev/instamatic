from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from textwrap import dedent
from time import perf_counter
from typing import ClassVar, Literal, Optional, Sequence

import numpy as np
from tqdm import tqdm
from typing_extensions import Self

from instamatic._typing import float_deg
from instamatic.calibrate.calibrate_stage_motion import CalibStageMotion, SpanSpeedTime, Speed
from instamatic.calibrate.filenames import CALIB_STAGE_ROTATION
from instamatic.utils.domains import NumericDomain

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


FEI_ROTATION_SPEED_OPTIONS = NumericDomain(lower_lim=0.0, upper_lim=1.0)
JEOL_ROTATION_SPEED_OPTIONS = NumericDomain(options=range(1, 13))


@dataclass
class CalibStageRotation(CalibStageMotion):
    _program_name: ClassVar[str] = 'instamatic.calibrate_stage_rotation'
    _span_typical_limits: ClassVar[tuple[float_deg, float_deg]] = (1.0, 10.0)
    _span_units: ClassVar[str] = 'degree'
    _yaml_filename: ClassVar[str] = CALIB_STAGE_ROTATION

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> Self:
        return calibrate_stage_rotation_live(ctrl=ctrl, **kwargs)


def calibrate_stage_rotation_live(
    ctrl: 'TEMController',
    spans: Optional[Sequence[float]] = None,
    speeds: Optional[Sequence[float]] = None,
    mode: Literal['auto', 'limited', 'listed'] = 'auto',
    outdir: Optional[str] = None,
    plot: Optional[bool] = None,
) -> CalibStageRotation:
    """Calibrate stage rotation speed live on the microscope. By default, this
    is run with a large precision and should take between 5 and 15 min. Can be
    made shorter if desired, but this is ill-advised. Even tests done on a
    simulator show that more points offer better accuracy (times in ms):

    -  30 calib. points: pace 1200+/-15, windup -12+/-116, delay 62+/-18
    -  60 calib. points: pace 1202+/-04, windup -22+/-031, delay 51+/-06
    - 120 calib. points: pace 1198+/-03, windup   2+/-020, delay 53+/-04

    By default, this function will try testing for rotation speeds of
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] i.e. JEOL settings first, and
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] i.e. FEI settings after.
    However, it is worth noting that a microscope might technically support
    every speed setting above while in practice introduce linear changed
    only in its limited range, e.g. up to 0.25, as noted on a FEI Tecnai.
    It is advised to look for irregularities during calibration and limit
    the calibration only to the range of speeds that will be used in practice.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    spans: `Optional[Sequence[float]]`
        Alpha rotations whose speed will be measured. Default: range(1, 11, 1).
    speeds: `Optional[Sequence[Union[float, int]]]`
        Spead range to measure. Default: range(1, 13, 1) or range(.1, 1.1, .1).
    mode: `Literal['auto', 'limited', 'listed']`
        Determines the way speed settings restrictions are set in calib file.
    outdir: `str` or None
        Directory where the final calibration file will be saved.

    return:
        instance of `CalibStageRotation` class with conversion methods
    """

    spans_array = np.array(spans or [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    alternating_ones = np.ones(len(spans_array)) * (-1) ** np.arange(len(spans_array))
    alpha_targets = np.cumsum(spans_array * alternating_ones)

    try:
        ctrl.stage.set_rotation_speed(12)
        assert ctrl.stage.get_rotation_speed() == 12
    except AssertionError:  # or any other raised if speed can't be set
        speeds_default = np.linspace(0.01, 0.2, num=20)
        speed_options = FEI_ROTATION_SPEED_OPTIONS
    else:
        speeds_default = np.arange(1, 13, step=1)
        speed_options = JEOL_ROTATION_SPEED_OPTIONS

    speeds_: Sequence[float] = speeds or speeds_default
    if mode == 'limited':
        speed_options = NumericDomain(lower_lim=min(speeds_), upper_lim=max(speeds_))
    elif mode == 'listed':
        speed_options = NumericDomain(options=sorted(speeds_))

    calib_points: list[SpanSpeedTime] = []
    starting_stage_alpha = ctrl.stage.a
    starting_stage_speed = ctrl.stage.get_rotation_speed()
    ctrl.cam.block()
    try:
        n_calib_points = len(speeds_) * len(spans_array)
        log(f'Calibrating a-axis rotation speed based on {n_calib_points} points.')
        with tqdm(total=n_calib_points) as progress_bar:
            for speed in speeds_:
                with ctrl.stage.rotation_speed(speed=float(speed)):
                    ctrl.stage.a = 0.0
                    for target, span in zip(alpha_targets, spans_array):
                        t1 = perf_counter()
                        ctrl.stage.a = float(target)
                        t2 = perf_counter()
                        calib_points.append(SpanSpeedTime(span, speed, t2 - t1))
                        progress_bar.update(1)
    finally:
        ctrl.stage.set(a=starting_stage_alpha)
        ctrl.stage.set_rotation_speed(starting_stage_speed)
        ctrl.cam.unblock()

    c = CalibStageRotation.from_data(calib_points)
    c.speed_options = speed_options
    c.to_file(outdir)
    if plot:
        log('Attempting to plot calibration results.')
        c.plot(calib_points)
    return c


def main_entry() -> None:
    """Calibrate the goniometer stage rotation speed setting of the stage.

    For a quick test or a debug run for the simulated TEM, run
    `instamatic.calibrate_stage_rotation -x 1 2 3 -s 8 10 12`.
    """

    parser = argparse.ArgumentParser(
        description=main_entry.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Comma-delimited list of alpha spans to calibrate (in degrees). '
    h += 'Default: "1 2 3 4 5 6 7 8 9 10".'
    parser.add_argument('-x', '--spans', type=float, default=None, nargs='*', help=h)

    h = """Comma-delimited list of speed settings to calibrate for.
    Default: "0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0" or
    "1 2 3 4 5 6 7 8 9 10 11 12", whichever is accepted by the microscope."""
    h = dedent(h.strip())
    parser.add_argument('-s', '--speeds', type=float, default=None, nargs='*', help=h)

    h = """Calibration mode to be used:
    "auto" - auto-determine upper and lower speed limits based on TEM response;
    "limited" - restrict TEM goniometer speed limits between min and max of --speeds;
    "listed" - restrict TEM goniometer speed settings exactly to --speeds provided."""
    h = dedent(h.strip())
    c = ['auto', 'limited', 'listed']
    parser.add_argument('-m', '--mode', type=str, default=c[0], nargs='?', choices=c, help=h)

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

    h = 'After calibration, attempt to `--plot` / `--no-plot` its results.'
    parser.add_argument('--plot', action=argparse.BooleanOptionalAction, default=True, help=h)

    kwargs = vars(parser.parse_args())
    if kwargs['speeds'] is not None and all(v.is_integer() for v in kwargs['speeds']):
        kwargs['speeds'] = [int(v) for v in kwargs['speeds']]

    from instamatic import controller

    ctrl = controller.initialize()
    calibrate_stage_rotation_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
