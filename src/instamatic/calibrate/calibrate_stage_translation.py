from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from itertools import cycle
from textwrap import dedent
from time import perf_counter
from typing import ClassVar, Literal, Optional, Self, Sequence

import numpy as np
from tqdm import tqdm

from instamatic._typing import AnyPath
from instamatic.calibrate.calibrate_stage_motion import CalibStageMotion, SpanSpeedTime
from instamatic.calibrate.filenames import CALIB_STAGE_TRANSLATION
from instamatic.microscope.utils import StagePositionTuple
from instamatic.utils.domains import NumericDomain

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


@dataclass
class CalibStageTranslation(CalibStageMotion):
    _program_name: ClassVar[str] = 'instamatic.calibrate_stage_translation'
    _span_typical_limits: ClassVar[tuple[float, float]] = (10_000, 100_000)
    _span_units: ClassVar[str] = 'nm'
    _yaml_filename: ClassVar[str] = CALIB_STAGE_TRANSLATION

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> Self:
        return calibrate_stage_translation_live(ctrl=ctrl, **kwargs)


def calibrate_stage_translation_live(
    ctrl: 'TEMController',
    spans: Optional[Sequence[float]] = None,
    speeds: Optional[Sequence[float]] = None,
    mode: Literal['auto', 'limited', 'listed'] = 'auto',
    outdir: Optional[AnyPath] = None,
    plot: Optional[bool] = None,
) -> CalibStageMotion:
    """Calibrate stage translation speed live on the microscope.

    By default, this function will try testing for rotation speeds of
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
    mode: `Literal['auto', 'limited', 'listed']`
        Determines the way speed settings restrictions are set in calib file.
    outdir: `str` or None
        Directory where the final calibration file will be saved.

    return:
        instance of `CalibStageTranslation` class with conversion methods
    """

    spans = np.array(spans or [1e4, 2e4, 3e4, 4e4, 5e4, 6e4, 7e4, 8e4, 9e4, 1e5])
    alternating_ones = np.ones(len(spans)) * (-1) ** np.arange(len(spans))
    span_direction = cycle(['x', 'y'])
    span_delta = np.repeat(spans * alternating_ones, 2)

    stage0: StagePositionTuple = ctrl.stage.get()
    try:
        ctrl.stage.set_with_speed(*stage0)
    except KeyError:
        log('TEM does not support setting with speed, assuming default = 1.')
        speeds_default = [None, None, None]  # TEM does not support translation w/ speed
        speed_options = None
    else:
        speeds_default = speeds or [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        speed_options = NumericDomain(lower_lim=0.0, upper_lim=1.0)
    finally:
        ctrl.stage.set(*stage0)

    speeds = speeds or speeds_default
    if mode == 'limited':
        speed_options = NumericDomain(lower_lim=min(speeds), upper_lim=max(speeds))
    elif mode == 'listed':
        speed_options = NumericDomain(options=sorted(speeds))

    calib_points: list[SpanSpeedTime] = []
    ctrl.cam.block()
    try:
        n_calib_points = len(speeds) * len(span_delta)
        log(f'Starting translation speed calibration based on {n_calib_points} points.')
        with tqdm(total=n_calib_points) as progress_bar:
            for speed in speeds:
                setter = ctrl.stage.set if speed is None else ctrl.stage.set_with_speed
                speed_keyword = {} if speed is None else {'speed': speed}

                ctrl.stage.set(*stage0)
                for d, s in zip(span_direction, span_delta):
                    stage1 = ctrl.stage.get()
                    t1 = perf_counter()
                    setter(**({d: getattr(stage1, d) + s} | speed_keyword))
                    t2 = perf_counter()
                    calib_points.append(SpanSpeedTime(span=s, speed=speed, time=t2 - t1))
                    progress_bar.update(1)
    finally:
        ctrl.stage.set(*stage0)
        ctrl.cam.unblock()

    c = CalibStageMotion.from_data(calib_points)
    c.speed_options = speed_options
    c.to_file(outdir)
    if plot:
        log('Attempting to plot calibration results.')
        c.plot(calib_points)
    return c


def main_entry() -> None:
    """Calibrate goniometer stage translation speed against speed setting.

    For a quick test or a debug run for the simulated TEM, run
    `instamatic.calibrate_stage_translation -a "10,20,30" -s "8,10,12"`.
    """

    parser = argparse.ArgumentParser(
        description=main_entry.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Comma-delimited list of x/y spans to calibrate (in nanometers). '
    h += 'Default: "10000,20000,30000,40000,50000,60000,70000,80000,90000,100000".'
    parser.add_argument('-a', '--spans', type=str, help=h)

    h = 'Comma-delimited list of speed settings to calibrate for.'
    h += 'Default: "0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0".'
    parser.add_argument('-s', '--speeds', type=str, help=h)

    h = """Calibration mode to be used:
    "auto" - auto-determine upper and lower speed limits based on TEM response;
    "limited" - restrict TEM goniometer speed limits between min and max of --speeds;
    "listed" - restrict TEM goniometer speed settings exactly to --speeds provided."""
    parser.add_argument('-m', '--mode', type=str, default='auto', help=dedent(h.strip()))

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

    h = 'After calibration, attempt to `--plot` / `--no-plot` its results.'
    parser.add_argument('--plot', action=argparse.BooleanOptionalAction, default=True, help=h)

    options = parser.parse_args()

    from instamatic import controller

    kwargs = {'mode': options.mode, 'outdir': options.outdir, 'plot': options.plot}
    if options.spans:
        kwargs['spans'] = [int(a) for a in options.spans.split(',')]
    if options.speeds:
        kwargs['speeds'] = [float(s) for s in options.speeds.split(',')]

    ctrl = controller.initialize()
    calibrate_stage_translation_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
