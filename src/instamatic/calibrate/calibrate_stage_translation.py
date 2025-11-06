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

from instamatic._typing import AnyPath, int_nm
from instamatic.calibrate.calibrate_stage_motion import CalibStageMotion, SpanSpeedTime, Speed
from instamatic.calibrate.filenames import (
    CALIB_STAGE_TRANSLATION_X,
    CALIB_STAGE_TRANSLATION_Y,
    CALIB_STAGE_TRANSLATION_Z,
)
from instamatic.microscope.utils import StagePositionTuple
from instamatic.utils.domains import NumericDomain

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


@dataclass
class CalibStageTranslation(CalibStageMotion):
    _calib_axis: ClassVar[Literal['x', 'y', 'z']] = NotImplemented
    _program_name: ClassVar[str] = 'instamatic.calibrate_stage_translation'
    _span_typical_limits: ClassVar[tuple[int_nm, int_nm]] = (10_000, 100_000)
    _span_units: ClassVar[str] = 'nm'

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> Self:
        return calibrate_stage_translation_live(ctrl=ctrl, axis=cls._calib_axis, **kwargs)


@dataclass
class CalibStageTranslationX(CalibStageTranslation):
    _calib_axis: ClassVar[Literal['x', 'y', 'z']] = 'x'
    _yaml_filename: ClassVar[str] = CALIB_STAGE_TRANSLATION_X


@dataclass
class CalibStageTranslationY(CalibStageTranslation):
    _calib_axis: ClassVar[Literal['x', 'y', 'z']] = 'y'
    _yaml_filename: ClassVar[str] = CALIB_STAGE_TRANSLATION_Y


@dataclass
class CalibStageTranslationZ(CalibStageTranslation):
    _calib_axis: ClassVar[Literal['x', 'y', 'z']] = 'z'
    _yaml_filename: ClassVar[str] = CALIB_STAGE_TRANSLATION_Z


axis_to_calib_class_dict: dict[Literal['x', 'y', 'z'], type[CalibStageTranslation]] = {
    'x': CalibStageTranslationX,
    'y': CalibStageTranslationY,
    'z': CalibStageTranslationZ,
}


def calibrate_stage_translation_live(
    ctrl: 'TEMController',
    spans: Optional[Sequence[float]] = None,
    speeds: Optional[Sequence[float]] = None,
    axis: Literal['x', 'y', 'z'] = 'x',
    mode: Literal['auto', 'limited', 'listed'] = 'auto',
    outdir: Optional[AnyPath] = None,
    plot: Optional[bool] = None,
) -> CalibStageTranslation:
    """Calibrate stage translation speed along axis live on the microscope. By
    default, this is run for a large number of stage span and speed settings
    and should take up to 30 minutes per axis. Calibration can be made shorter
    if desired but this is ill-advised. Tests run on a Tecnai T20 machine show
    how more calibration points offer better accuracy (delay may be unreliable;
    pace given in seconds / meter, windup and delay in milliseconds):

    -  5 x  6 cal pts: pace 9667+/-118, windup -67+/-9, delay 2235+/-58 (4 min)
    - 10 x  6 cal pts: pace 9682+/- 78, windup -68+/-6, delay 2227+/-39 (7 min)
    - 10 x 15 cal pts: pace 9715+/- 47, windup -32+/-3, delay 1924+/-30 (20 min)

    By default, this function will try testing for translation speeds of
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] i.e. FEI settings.
    However, it is worth noting that a microscope might technically support
    every speed setting above while in practice introduce linear changed
    only in its limited range, e.g. up to 0.25, as noted on a FEI Tecnai.
    It is advised to look for irregularities during calibration and limit
    the calibration only to the range of speeds that will be used in practice.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    spans: `Optional[Sequence[float]]`
        Translations that will be timed. Default: 10_000 to 100_000 every 10_000
    speeds: `Optional[Sequence[Union[float, int]]]`
        All speed settings used for calibration. Default: 0.1 to 1.0 every 0.1.
    axis: `Literal['x', 'y', 'z']`
        Axis the speed of which is to be calibrated. Default: 'x'.
    mode: `Literal['auto', 'limited', 'listed']`
        Determines the way speed settings restrictions are set in calib file.
    outdir: `str` or None
        Directory where the final calibration file will be saved.

    return:
        instance of `CalibStageTranslation` class with conversion methods
    """

    spans_array = np.array(spans or [1e4, 2e4, 3e4, 4e4, 5e4, 6e4, 7e4, 8e4, 9e4, 1e5])
    alternating_ones = np.ones(len(spans_array)) * (-1) ** np.arange(len(spans_array))
    span_deltas = spans_array * alternating_ones

    stage0: StagePositionTuple = ctrl.stage.get()
    try:
        ctrl.stage.set_with_speed(*stage0)
    except KeyError:
        log('TEM does not support setting with speed, assuming default = 1.')
        speeds_default: Sequence[Speed] = [None, None, None]  # no translation w/ speed
        speed_options = None
    else:
        speeds_default = speeds or [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        speed_options = NumericDomain(lower_lim=0.0, upper_lim=1.0)
    finally:
        ctrl.stage.set(*stage0)

    speeds_: Sequence[Speed] = speeds or speeds_default
    if mode == 'limited':
        speed_options = NumericDomain(lower_lim=min(speeds_), upper_lim=max(speeds_))
    elif mode == 'listed':
        speed_options = NumericDomain(options=sorted(speeds_))

    calib_points: list[SpanSpeedTime] = []
    ctrl.cam.block()
    try:
        n_calib_points = len(speeds_) * len(span_deltas)
        log(f'Calibrating {axis}-axis translation speed based on {n_calib_points} points.')
        with tqdm(total=n_calib_points) as progress_bar:
            for speed in speeds_:
                setter = ctrl.stage.set if speed is None else ctrl.stage.set_with_speed
                speed_kwarg = {} if speed is None else {'speed': speed}

                ctrl.stage.set(*stage0)
                for s in span_deltas:
                    stage1 = ctrl.stage.get()
                    t1 = perf_counter()
                    setter(**({axis: getattr(stage1, axis) + s} | speed_kwarg))
                    t2 = perf_counter()
                    calib_points.append(SpanSpeedTime(span=abs(s), speed=speed, time=t2 - t1))
                    progress_bar.update(1)
    finally:
        ctrl.stage.set(*stage0)
        ctrl.cam.unblock()

    c = axis_to_calib_class_dict[axis].from_data(calib_points)
    c.speed_options = speed_options
    c.to_file(outdir)
    if plot:
        log('Attempting to plot calibration results.')
        c.plot(calib_points)
    return c


def main_entry() -> None:
    """Calibrate goniometer stage translation speed against speed setting.

    For a quick test or a debug run for the simulated TEM, run
    `instamatic.calibrate_stage_translation -x 10 20 30 -s 8 10 12`.
    """

    parser = argparse.ArgumentParser(
        description=main_entry.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Space-delimited list of x/y spans to calibrate (in nanometers). '
    h += 'Default: "10000 20000 30000 40000 50000 60000 70000 80000 90000 100000".'
    parser.add_argument('-x', '--spans', type=int, default=None, nargs='*', help=h)

    h = 'Comma-delimited list of speed settings to calibrate for.'
    h += 'Default: "0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0".'
    parser.add_argument('-s', '--speeds', type=float, default=None, nargs='*', help=h)

    h = 'Axis whose translation speed should be calibrated, x, y, or z. Default: x'
    c = ['x', 'y', 'z']
    parser.add_argument('-a', '--axis', type=str, default=c[0], nargs='?', choices=c, help=h)

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
    calibrate_stage_translation_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
