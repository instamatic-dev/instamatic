from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import NamedTuple, Optional, Sequence

import numpy as np
import yaml
from matplotlib import pyplot as plt
from scipy.optimize import curve_fit
from skimage.registration import phase_cross_correlation
from tqdm import tqdm
from typing_extensions import Self

from instamatic._typing import AnyPath, int_nm
from instamatic.calibrate.filenames import CALIB_STAGE_ROTATION, CALIB_STAGE_TRANSLATION
from instamatic.config import calibration_drc
from instamatic.image_utils import autoscale, imgscale
from instamatic.microscope.utils import StagePositionTuple
from instamatic.utils.domains import NumericDomain, NumericDomainConstrained
from instamatic.utils.iterating import sawtooth

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


TRANSLATION_SPEED_OPTIONS = NumericDomain(lower_lim=0.0, upper_lim=1.0)


@dataclass
class TranslationPlan:
    """A set of translation parameters that are the nearest to ones
    requested."""

    pace: float  # time it takes goniometer to cover 1 distance unit (nm/deg)
    speed: float  # speed setting that needs to be set to get desired pace
    total_delay: float  # total goniometer delay: delay + windup / speed


@dataclass
class CalibStageTranslation:
    pace: float
    windup: float
    delay: float
    speed_options: Optional[NumericDomain] = None

    def __post_init__(self) -> None:
        self.pace = float(self.pace)
        self.windup = float(self.windup)
        self.delay = float(self.delay)
        if isinstance(self.speed_options, dict):
            self.speed_options = NumericDomain(**self.speed_options)

    @staticmethod
    def curve_fit_model(
        span_speed: tuple[float, float],
        pace: float,
        windup: float,
        delay: float,
    ) -> float:
        """Model equation for estimating total translation time for scipy."""
        span, speed = span_speed
        return (pace * span + windup) / speed + delay

    def span_speed_to_time(self, span: float, speed: float) -> float:
        """`time` needed to translate stage by `span` with `speed`."""
        return (self.pace * span + self.windup) / speed + self.delay

    def span_time_to_speed(self, span: float, time: float) -> float:
        """`speed` that allows to translate stage by `span` with `speed`."""
        return (self.pace * span + self.windup) / (time - self.delay)

    def speed_time_to_span(self, speed: float, time: float) -> float:
        """Maximum `span` covered with `speed` in `time` (including delay)."""
        return (speed * (time - self.delay) - self.windup) / self.pace

    def plan_translation(self, target_pace: float) -> TranslationPlan:
        """Given target pace in sec / nm, find nearest pace, speed, delay."""
        target_speed = abs(self.pace / target_pace)  # exact speed setting needed
        nearest_speed = self.speed_options.nearest(target_speed)  # nearest setting
        nearest_pace = self.pace / nearest_speed  # nearest in sec/deg
        total_delay = self.windup / nearest_speed + self.delay
        return TranslationPlan(nearest_pace, nearest_speed, total_delay)

    @classmethod
    def from_file(cls, path: Optional[AnyPath] = None) -> Self:
        if path is None:
            path = Path(calibration_drc) / CALIB_STAGE_TRANSLATION
        try:
            with open(Path(path), 'r') as yaml_file:
                return cls(**yaml.safe_load(yaml_file))
        except OSError as e:
            prog = 'instamatic.calibrate_stage_translation'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> Self:
        return calibrate_stage_translation_live(ctrl=ctrl, **kwargs)

    def to_file(self, outdir: Optional[str] = None) -> None:
        if outdir is None:
            outdir = calibration_drc
        yaml_path = Path(outdir) / CALIB_STAGE_TRANSLATION
        with open(yaml_path, 'w') as yaml_file:
            yaml.safe_dump(asdict(self), yaml_file)  # type: ignore[arg-type]
        log(f'{self} saved to {yaml_path}.')

    def plot(self, sst: Optional[list[SpanSpeedTime]] = None) -> None:
        """Plot calib and measurement results (simulated or experimental)."""
        if sst is None:
            spans = np.linspace(1e4, 1e5, 10, endpoint=True)
            if isinstance(self.speed_options, NumericDomainConstrained):
                so: NumericDomainConstrained = self.speed_options
                speeds = np.linspace(so.lower_lim, so.upper_lim, 10)
            else:  # isinstance(calib.speed_options, NumericDomainDiscrete):
                speeds = self.speed_options.options  # noqa - has options
            speeds = [s for s in speeds if s != 0]
            sst = []
            for span in spans:
                for speed in speeds:
                    time = self.span_speed_to_time(span, speed)
                    sst.append(SpanSpeedTime(span, speed, time))
        else:
            sst = sorted(sst)

        fig, ax = plt.subplots()
        ax.axvline(x=0, color='k')
        ax.axhline(y=0, color='k')
        ax.axhline(y=self.delay, color='r')

        speeds = list(dict.fromkeys(s.speed for s in sst).keys())
        colors = plt.colormaps['viridis'](np.linspace(0, 1, num=len(speeds)))
        for color, speed in zip(colors, speeds):
            spans = [s.span for s in sst if s.speed == speed]
            times = [s.time for s in sst if s.speed == speed]
            ax.plot(spans, times, color=color, label=f'Speed setting {speed:.2f}')

        ax.set_xlabel('XY span [degrees]')
        ax.set_ylabel('Time required [s]')
        ax.set_title('Stage translation time vs. motion span at different speeds')
        ax.legend()
        plt.show()


class SpanSpeedTime(NamedTuple):
    """Holds a single measurement point used to calibrate translation speed."""

    span: float  # xy span traveled by the goniometer expressed in nm
    speed: float  # nearest available speed setting expressed in arbitrary units
    time: float  # time taken to travel span with speed expressed in seconds


def calibrate_stage_translation_live(
    ctrl: 'TEMController',
    xy_spans: Optional[Sequence[float]] = None,
    speed_range: Optional[Sequence[float]] = None,
    outdir: Optional[AnyPath] = None,
    plot: Optional[bool] = None,
) -> CalibStageTranslation:
    xy_spans = np.array(xy_spans or [10, 20, 30, 40, 50, 60, 70, 80])  # px
    alternating_ones = np.ones(len(xy_spans)) * (-1) ** np.arange(len(xy_spans))
    delta_dir = sawtooth(['x', 'y', 'x', 'y'])
    delta_span = np.repeat(xy_spans * alternating_ones, 2)

    stage0: StagePositionTuple = ctrl.stage.get()
    try:
        ctrl.stage.set_with_speed(*stage0)
    except KeyError:  # if stage cannot move with speed, investigate shifts only
        speed_range = [0]
    else:
        speed_range = speed_range or [0.1, 0.2, 0.3]
    finally:
        ctrl.stage.set(stage0.x, stage0.y, stage0.z, 0, 0)
    stage0 = ctrl.stage.get()
    image0, h0 = ctrl.get_image(header_keys=None)
    image0s, scale = autoscale(image0)

    calib_points: list[SpanSpeedTime] = []
    ctrl.cam.block()
    try:
        n_calib_points = len(speed_range) * len(delta_span)
        log(f'Starting translation (speed) calibration based on {n_calib_points} points.')
        with tqdm(total=n_calib_points) as progress_bar:
            for speed in speed_range:
                setter = ctrl.stage.set_with_speed if speed > 0 else ctrl.stage.set
                setter_kw = {'speed': speed} if speed > 0 else {}

                ctrl.stage.set(*stage0)
                for d, s in zip(delta_dir, delta_span):
                    stage1 = ctrl.stage.get()
                    t1 = perf_counter()
                    setter(**{**{d: getattr(stage1, d) + s}, **setter_kw})
                    t2 = perf_counter()
                    calib_points.append(SpanSpeedTime(span=s, speed=speed, time=t2 - t1))
                    progress_bar.update(1)
    finally:
        ctrl.stage.set(*stage0)
        ctrl.cam.unblock()

    calib_points_array = np.array(calib_points).T
    all_spans_speeds = calib_points_array[:2]
    all_times = calib_points_array[2]
    f = CalibStageTranslation.curve_fit_model
    p = curve_fit(f, all_spans_speeds, ydata=all_times, p0=[1, 0, 0])
    (pace, windup, delay), p_cov = p  # noqa - this unpacking is OK
    pace_u, windup_u, delay_u = np.sqrt(np.diag(p_cov))

    log('Stage rotation speed calibration fit complete:')
    log(f'pace   = {pace:12.6f} +/- {pace_u:12.6f} s / deg')
    log(f'windup = {windup:12.6f} +/- {windup_u:12.6f} s')
    log(f'delay  = {delay:12.6f} +/- {delay_u:12.6f} s')
    log('model time   = (pace * span + windup) / speed + delay')

    c = CalibStageTranslation(*p[0], speed_options=speed_options)
    c.to_file(outdir)
    if plot:
        log('Attempting to plot calibration results.')
        c.plot(calib_points)

    return c


def main_entry():  # TODO
    from instamatic import controller

    ctrl = controller.initialize()
    calibrate_stage_translation_live(ctrl=ctrl)


if __name__ == '__main__':
    main_entry()
