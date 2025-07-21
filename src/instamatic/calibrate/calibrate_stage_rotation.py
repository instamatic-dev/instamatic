from __future__ import annotations

import abc
import dataclasses
import logging
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Self, Sequence, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy.optimize import curve_fit
from tqdm import tqdm

from instamatic._collections import timer
from instamatic.calibrate.filenames import CALIB_STAGE_ROTATION
from instamatic.config import calibration_drc

logger = logging.getLogger(__name__)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ HELPER OBJECTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def alternating_ones(len_: int) -> np.ndarray:
    """Returning a `len_`-long numpy array of alternating 1 and -1."""
    alt = np.ones(len_)
    alt[1::2] = -1
    return alt


def log(s: str) -> None:
    logger.info(s)
    print(s)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ NEAREST FLOAT OPTION ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class FloatOptions:
    """Store valid float options, help finding the nearest available one."""

    def __new__(cls, *args, **kwargs):
        """Initialize one of subclasses based on the contents of kwargs."""
        if cls is FloatOptions:
            if 'lower_lim' in kwargs and 'upper_lim' in kwargs:
                return FloatOptionsLimited(**kwargs)
            elif 'options' in kwargs:
                return FloatOptionsListed(**kwargs)
            else:
                raise ValueError("Can't determine child class based on kwargs.")
        return super().__new__(cls)

    @abc.abstractmethod
    def __init__(self, **kwargs) -> None:
        """All instance variables must be settable under the same names."""

    @abc.abstractmethod
    def nearest(self, to: float) -> float:
        """Find and return the nearest available float option (L^1 norm)."""

    @classmethod
    def from_dict(cls, dict_: dict) -> Self:
        """Initialize self from a dict to allow easy serialization."""
        return cls(**dict_)

    def to_dict(self) -> dict:
        """Convert self to a dict to allow easy serialization."""
        return vars(self)


class FloatOptionsLimited(FloatOptions):
    def __init__(self, lower_lim: float, upper_lim: float) -> None:
        self.lower_lim = lower_lim
        self.upper_lim = upper_lim

    def nearest(self, to: float) -> float:
        return float(np.clip(to, self.lower_lim, self.upper_lim))


class FloatOptionsListed(FloatOptions):
    def __init__(self, options: List[float]) -> None:
        self.options = list(options)  # must be a list to be serializable

    def nearest(self, to: float) -> float:
        options = np.array(self.options)
        return float(options[(np.abs(options - to)).argmin()])


FEI_ROTATION_SPEED_OPTIONS = FloatOptionsLimited(lower_lim=0.0, upper_lim=1.0)
JEOL_ROTATION_SPEED_OPTIONS = FloatOptionsListed(options=list(range(1, 13)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ROTATION PLAN ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


@dataclasses.dataclass
class RotationPlan:
    """A set of rotation parameters that are the nearest to ones requested."""

    pace: float  # time it takes to cover 1 degree for a moving goniometer
    speed: float  # speed setting that needs to be set to get desired pace
    total_delay: float  # total goniometer delay: delay + alpha_windup / speed


# ~~~~~~~~~~~~~~~~~~~~~~~~ ROTATION CALIBRATION CLASS ~~~~~~~~~~~~~~~~~~~~~~~~ #


class CalibStageRotation:
    """Obtain and apply the results of stage rotation speed calibration.
    The time it takes the stage to move some `alpha_span` with `speed` is
    calculated using the following formula:

    time = (alpha_pace * alpha_span + alpha_windup) / speed + delay

    The two variables and three coefficients used above represent the following:

    - alpha_span: total angular distance for stage to cover in degrees;
    - speed: goniometer speed setting linearly related to real speed, unit-less;
    - alpha_pace: time a stage needs to cover 1 deg at speed=1 in seconds / deg;
    - alpha_windup: constant time for stage speed up or slow down in seconds;
    - delay: small constant time needed for stage communication in seconds;

    The calibration also accepts `FloatOptions`-type `speed_options` to account
    for the fact that different goniometers accept different speed settings.
    If given, `CalibStageRotation.speed_options.nearest(requested)` can be used
    to find the speed setting nearest to the one requested.
    """

    def __init__(
        self,
        alpha_pace: float,
        alpha_windup: float,
        delay: float,
        speed_options: Union[FloatOptions, Dict[str, float], None] = None,
    ) -> None:
        self.alpha_pace: float = alpha_pace
        self.alpha_windup: float = alpha_windup
        self.delay: float = delay
        self.speed_options = (
            FloatOptions(**speed_options) if isinstance(speed_options, dict) else speed_options
        )

    def __repr__(self):
        return (
            f'CalibStageRotation('
            f'alpha_pace={self.alpha_pace}, '
            f'alpha_windup={self.alpha_windup}, '
            f'delay={self.delay}, '
            f'speed_options={self.speed_options.to_dict()})'
        )

    def __eq__(self, o: object) -> bool:
        return isinstance(o, CalibStageRotation) and self.to_dict() == o.to_dict()

    @staticmethod
    def curve_fit_model(
        span_speed: Tuple[float, float],
        alpha_pace: float,
        alpha_windup: float,
        delay: float,
    ) -> float:
        """Model equation for estimating total rotation time for scipy."""
        alpha_span, speed = span_speed
        return (alpha_pace * alpha_span + alpha_windup) / speed + delay

    def _alpha_poly(self, span: float) -> float:
        """Value of `alpha_pace * alpha_span + alpha_windup` polynomial."""
        return self.alpha_pace * span + self.alpha_windup

    def span_speed_to_time(self, span: float, speed: float) -> float:
        """`time` needed to rotate alpha by `span` with `speed`."""
        return self._alpha_poly(span) / speed + self.delay

    def span_time_to_speed(self, span: float, time: float) -> float:
        """`speed` that allows to rotate alpha by `span` with `speed`."""
        return self._alpha_poly(span) / (time - self.delay)

    def speed_time_to_span(self, speed: float, time: float) -> float:
        """Maximum `span` covered with `speed` in `time` (including delay)."""
        return (speed * (time - self.delay) - self.alpha_windup) / self.alpha_pace

    def plan_rotation(self, target_pace: float) -> RotationPlan:
        """Given target pace in sec / deg, find nearest pace, speed, delay."""
        target_speed = self.alpha_pace / target_pace  # exact speed setting needed
        nearest_speed = self.speed_options.nearest(target_speed)  # nearest setting
        nearest_pace = self.alpha_pace / nearest_speed  # nearest in sec/deg
        total_delay = self.alpha_windup / nearest_speed + self.delay
        return RotationPlan(nearest_pace, nearest_speed, total_delay)

    @classmethod
    def from_dict(cls, dict_: dict) -> CalibStageRotation:
        return cls(**dict_)

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> CalibStageRotation:
        if path is None:
            path = Path(calibration_drc) / CALIB_STAGE_ROTATION
        try:
            with open(Path(path), 'r') as yaml_file:
                return cls.from_dict(yaml.safe_load(yaml_file))
        except OSError as e:
            prog = 'instamatic.calibrate_stage_rotation'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> CalibStageRotation:
        return calibrate_stage_rotation_live(ctrl=ctrl, **kwargs)

    def to_dict(self) -> dict:
        return {
            k: float(v) if isinstance(v, float) else v.to_dict() for k, v in vars(self).items()
        }

    def to_file(self, path: Optional[str] = None) -> None:
        if path is None:
            path = Path(calibration_drc) / CALIB_STAGE_ROTATION
        with open(Path(path), 'w') as yaml_file:
            d = self.to_dict()
            for k, v in d.items():
                print(f'{k} {type(k)} {v} {type(v)}')
            yaml.safe_dump(self.to_dict(), yaml_file)
        log(f'{self} saved to {path}.')


class SpanSpeedTime(NamedTuple):
    span: float  # alpha span traveled by the goniometer expressed in degrees
    speed: float  # nearest available speed setting expressed in arbitrary units
    time: float  # time taken to travel span with speed expressed in seconds


def plot_stage_rotation(
    calib: CalibStageRotation,
    sst: Optional[List[SpanSpeedTime]] = None,
) -> None:
    """Plot calib w/measurement results (either simulated or experimental)."""
    if sst is None:
        spans = np.linspace(0.1, 1.0, 10, endpoint=True)
        if isinstance(calib.speed_options, FloatOptionsLimited):
            so: FloatOptionsLimited = calib.speed_options
            speeds = np.linspace(so.lower_lim, so.upper_lim, 10)
        else:  # isinstance(calib.speed_options, FloatOptionsListed):
            speeds = self.speed_options.options  # noqa - has options
        speeds = [s for s in speeds if s != 0]
        sst = []
        for s1 in spans:
            for s2 in speeds:
                sst.append(SpanSpeedTime(s1, s2, calib.span_speed_to_time(s1, s2)))
    else:
        sst = sorted(sst)

    fig, ax = plt.subplots()
    ax.axvline(x=0, color='k')
    ax.axhline(y=0, color='k')
    ax.axhline(y=calib.delay, color='r')

    speeds = list(dict.fromkeys(s.speed for s in sst).keys())
    colors = plt.colormaps['viridis'](np.linspace(0, 1, num=len(speeds)))
    for color, speed in zip(colors, speeds):
        spans = [s.span for s in sst if s.speed == speed]
        times = [s.time for s in sst if s.speed == speed]
        ax.plot(spans, times, color=color, label=f'Speed setting {speed:.2f}')

    ax.set_xlabel('Alpha span [degrees]')
    ax.set_ylabel('Time required [s]')
    ax.set_title('Stage rotation time vs. alpha span at different speeds')
    ax.legend()
    plt.show()


# ~~~~~~~~~~~~~~~~~~~~~~~~ ROTATION CALIBRATION SCRIPT ~~~~~~~~~~~~~~~~~~~~~~~ #


def calibrate_stage_rotation_live(
    ctrl: 'TEMController',
    alpha_spans: Optional[Sequence[float]] = None,
    speed_range: Optional[Sequence[float]] = None,
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
    [0,1. 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] i.e. FEI settings after.
    However, it is worth noting that a microscope might technically support
    every speed setting above while in practice introduce linear changed
    only in its limited range, e.g. up to 0.25, as noted on a FEI Tecnai.
    It is advised to look for irregularities during calibration and limit
    the calibration only to the range of speeds that will be used in practice.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    alpha_spans: `Optional[Sequence[float]]`
        Alpha rotations whose speed will be measured. Default: range(1, 11, 1).
    speed_range: `Optional[Sequence[Union[float, int]]]`
        Spead range to measure. Default: range(1, 13, 1) or range(.1, 1.1, .1).
    outdir: `str` or None
        Directory where the final calibration file will be saved.

    return:
        instance of `CalibStageRotation` class with conversion methods
    """

    alpha_spans = np.array(alpha_spans or np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    alpha_targets = np.cumsum(alpha_spans * alternating_ones(len(alpha_spans)))

    calib_points: List[SpanSpeedTime] = []
    starting_stage_alpha = ctrl.stage.a
    starting_stage_speed = ctrl.stage.get_rotation_speed()
    ctrl.cam.block()
    try:
        try:
            ctrl.stage.set_rotation_speed(12)
            assert ctrl.stage.get_rotation_speed() == 12
        except AssertionError:  # or any other raised if speed can't be set
            speed_range_default = np.linspace(0.01, 0.2, num=20)
            speed_options = FEI_ROTATION_SPEED_OPTIONS
        else:
            speed_range_default = np.arange(1, 13, step=1)
            speed_options = JEOL_ROTATION_SPEED_OPTIONS
        speed_range = speed_range or speed_range_default

        total = len(speed_range) * len(alpha_spans)
        log(f'Starting rotation speed calibration based on {total} points.')

        with tqdm(total=total) as progress_bar:
            for speed in speed_range:
                with ctrl.stage.rotation_speed(speed=float(speed)):
                    ctrl.stage.a = 0.0
                    for at, as_ in zip(alpha_targets, alpha_spans):
                        with timer() as t:
                            ctrl.stage.a = float(at)
                        calib_points.append(SpanSpeedTime(as_, speed, t()))
                        progress_bar.update(1)
    finally:
        ctrl.stage.set(a=starting_stage_alpha)
        ctrl.stage.set_rotation_speed(starting_stage_speed)
        ctrl.cam.unblock()

    calib_points_array = np.array(calib_points).T
    all_spans_speeds = calib_points_array[:2]
    all_times = calib_points_array[2]
    f = CalibStageRotation.curve_fit_model
    p = curve_fit(f, all_spans_speeds, ydata=all_times, p0=[1, 0, 0])
    (alpha_pace, alpha_windup, delay), p_cov = p  # noqa - this unpacking is OK
    alpha_pace_u, alpha_windup_u, delay_u = np.sqrt(np.diag(p_cov))

    log('Stage rotation speed calibration fit complete:')
    log(f'alpha_pace   = {alpha_pace:12.6f} +/- {alpha_pace_u:12.6f} s / deg')
    log(f'alpha_windup = {alpha_windup:12.6f} +/- {alpha_windup_u:12.6f} s')
    log(f'delay        = {delay:12.6f} +/- {delay_u:12.6f} s')
    log('model time   = (alpha_pace * alpha_span + alpha_windup) / speed + delay')

    c = CalibStageRotation(*p[0], speed_options=speed_options)
    c.to_file(None if outdir is None else Path(outdir) / CALIB_STAGE_ROTATION)
    if plot:
        log('Attempting to plot calibration results.')
        plot_stage_rotation(c, calib_points)

    return c


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STANDALONE COMMAND ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def main_entry() -> None:
    import argparse

    description = """Calibrate the rotation speed setting of the stage."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Comma-delimited list of alpha spans to calibrate. '
    h += 'Default: "1,2,3,4,5,6,7,8,9,10".'
    parser.add_argument('-a', '--alphas', type=str, help=h)

    h = 'Comma-delimited list of speed settings to calibrate. '
    h += 'Default: "0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0" or '
    h += '"1,2,3,4,5,6,7,8,9,10,11,12", whichever is accepted by the microscope.'
    parser.add_argument('-s', '--speeds', type=str, help=h)

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

    h = 'After calibration, attempt to `--plot` / `--no-plot` its results'
    parser.add_argument('--plot', action=argparse.BooleanOptionalAction, default=True, help=h)

    options = parser.parse_args()

    from instamatic import controller

    kwargs = {'plot': options.plot}
    if options.alphas:
        kwargs['alpha_spans'] = [float(a) for a in options.alphas.split(',')]
    if options.speeds:
        kwargs['speed_range'] = [float(s) for s in options.speeds.split(',')]
    if options.outdir:
        kwargs['outdir'] = options.outdir

    ctrl = controller.initialize()
    calibrate_stage_rotation_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
