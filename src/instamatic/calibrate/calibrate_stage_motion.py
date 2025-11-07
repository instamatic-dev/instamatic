from __future__ import annotations

import logging
from abc import ABC
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar, Generic, NamedTuple, Optional, Sequence, TypeVar, Union

import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.lines import Line2D
from scipy.optimize import curve_fit
from typing_extensions import Self

from instamatic._typing import AnyPath, float_deg, int_nm
from instamatic.config import calibration_drc
from instamatic.utils.domains import NumericDomain, NumericDomainConstrained

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


Span = TypeVar('Span', float_deg, int_nm)
SpeedN = TypeVar('SpeedN', float, int)
Speed = Optional[SpeedN]


@dataclass
class MotionPlan(Generic[SpeedN]):
    """A set of motion parameters/outcomes nearest to the ones requested."""

    pace: float  # time it takes goniometer to cover 1 span unit (nm or degree)
    speed: Optional[SpeedN]  # speed setting to get pace, None = not supported
    total_delay: float  # total goniometer delay: delay + windup / speed


class SpanSpeedTime(Generic[Span, SpeedN], NamedTuple):
    """A single measurement point used to calibrate stage motion speed.

    - span: the motion span expressed in degrees (rotation) or nm (translation);
    - speed: the speed setting used expressed in arbitrary TEM units;
    - time: time taken to travel span with speed expressed in seconds.
    """

    span: Span
    speed: Optional[SpeedN]
    time: float


@dataclass
class CalibStageMotion(ABC):
    """Abstract base class for stage-motion calibration.

    Stores three parameters (pace, windup, delay) and optional speed_options.
    The `time` it takes the stage to move some `span` with `speed`
    is calculated using the following formula:

    time = (alpha_pace * alpha_span + alpha_windup) / speed + delay

    The two variables and three coefficients used above represent the following:

    - span: total translation/rotation distance for stage to cover in degrees;
    - speed: goniometer speed setting linearly related to real speed, unit-less;
    - pace: time needed to cover 1 distance unit at speed=1 in dist unit / deg;
    - windup: variable time delay for stage speed up or slow down in seconds;
    - delay: constant time needed for stage communication in seconds;

    The calibration also accepts `NumericDomain`-type `speed_options` to account
    for the fact that different goniometers accept different speed settings.
    `CalibStageRotation.speed_options.nearest(requested)` is used to find the
    speed setting nearest to the one requested. Any mention of `speed=None`
    signals that the microscope does not allow control over this motion speed.

    Concrete subclasses should provide:
      - units and axis labels for plotting
      - a `live` class method that runs live calibration and returns an instance
    """

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

    _program_name: ClassVar[str] = NotImplemented
    _span_typical_limits: ClassVar[tuple[float, float]] = NotImplemented
    _span_units: ClassVar[str] = NotImplemented
    _yaml_filename: ClassVar[str] = NotImplemented

    @staticmethod
    def model1(
        span_speed: tuple[Span, SpeedN],
        pace: float,
        windup: float,
        delay: float,
    ) -> float:
        """Model 1 for estimating the total motion time for scipy curve_fit."""
        span, speed = span_speed
        return (pace * span + windup) / speed + delay

    @staticmethod
    def model2(span: Span, pace: float, delay: float):
        """Simplified model used when speed is not supported i.e. = None."""
        return pace * span + delay

    def span_speed_to_time(self, span: Span, speed: Speed = None) -> float:
        """`time` needed to move stage by `span` with `speed`."""
        return (self.pace * span + self.windup) / (speed or 1.0) + self.delay

    def span_time_to_speed(self, span: Span, time: float) -> float:
        """`speed` that allows to move stage by `span` with `speed`."""
        return (self.pace * span + self.windup) / (time - self.delay)

    def time_speed_to_span(self, time: float, speed: Speed = None) -> float:
        """Maximum `span` covered with `speed` in `time` (including delay)."""
        return ((speed or 1.0) * (time - self.delay) - self.windup) / self.pace

    def plan_motion(self, target_pace: float) -> MotionPlan:
        """Given target pace, find nearest pace, needed speed, and delay."""
        if self.speed_options is None:
            return MotionPlan(self.pace, None, self.windup + self.delay)
        target_speed: float = abs(self.pace / target_pace)
        nearest_speed: Union[float, int] = self.speed_options.nearest(target_speed)
        nearest_pace: float = self.pace / nearest_speed
        total_delay: float = self.windup / nearest_speed + self.delay
        return MotionPlan(nearest_pace, nearest_speed, total_delay)

    def plot(self, sst: Optional[Sequence[SpanSpeedTime]] = None) -> None:
        """Generic plot of experimental (if given) & fit motion speed data."""

        # determine speeds to plot; use experimental if given, fabricate otherwise
        speeds: list[Speed]  # sorted
        if sst is not None:
            speeds = sorted(dict.fromkeys(s.speed for s in sst).keys())
        elif self.speed_options is None:
            speeds = [None]
        elif isinstance(self.speed_options, NumericDomainConstrained):
            so: NumericDomainConstrained = self.speed_options
            speeds = list(np.linspace(so.lower_lim, so.upper_lim, 10))
        else:  # isinstance(calib.speed_options, NumericDomainDiscrete):
            speeds = sorted(getattr(self.speed_options, 'options', [1.0]))
        speeds = [s for s in speeds if s != 0]

        # determine spans to plot; use experimental if given, fabricate otherwise
        spans: list[float]  # sorted
        if sst is not None:
            spans = list(dict.fromkeys(s.span for s in sst).keys())
        else:
            spans = list(np.linspace(*self._span_typical_limits, 10))

        # generate simulated span/speed/times data to be drawn later as lines
        simulated_sst = []
        for span in spans:
            for speed in speeds:
                t = self.span_speed_to_time(span, speed)
                simulated_sst.append(SpanSpeedTime(span, speed, t))
        plotted: list[tuple[Sequence[SpanSpeedTime], str]] = [(simulated_sst, '-')]

        # generate experimental span/speed/times to be drawn later as points
        if sst is not None:
            plotted.append((sst, 'o'))

        fig, ax = plt.subplots()
        ax.axvline(x=0, color='k')
        ax.axhline(y=0, color='k')
        ax.axhline(y=self.delay, color='r')

        colors = plt.colormaps['coolwarm'](np.linspace(0, 1, num=len(speeds)))
        handles: list[Line2D] = []
        for color, speed in zip(colors, speeds):
            for sst, fmt in plotted:
                spans = [s.span for s in sst if s.speed == speed]
                times = [s.time for s in sst if s.speed == speed]
                ax.plot(spans, times, fmt, color=color)
            label = f'Speed setting {speed:.2f}'
            handles.append(Line2D([], [], color=color, marker='o', label=label))

        ax.set_xlabel(f'Motion span [{self._span_units}]')
        ax.set_ylabel('Time required [s]')
        ax.set_title('Stage motion time vs span at different speeds')
        ax.legend(handles=handles, loc='best')
        plt.show()

    @classmethod
    def from_data(cls, sst: Sequence[SpanSpeedTime]) -> Self:
        """Fit cls.model to span-speed-time points and init based on result."""
        sst_array = np.array(sst).T
        spans = np.array(sst_array[0], dtype=float)
        speeds = np.array(sst_array[1], dtype=float)
        times = np.array(sst_array[2], dtype=float)

        if np.all(np.isnan(speeds)):  # TEM does not support setting with speed
            p = curve_fit(CalibStageMotion.model2, spans, ydata=times, p0=[1, 0])
            (pace_n, delay_n), p_cov = p  # noqa - this unpacking is OK
            pace_u, delay_u = np.sqrt(np.diag(p_cov))
            windup_n, windup_u = 0.0, 0.0
        else:
            ss = sst_array[:2]
            p = curve_fit(CalibStageMotion.model1, ss, ydata=times, p0=[1, 0, 0])
            (pace_n, windup_n, delay_n), p_cov = p  # noqa - this unpacking is OK
            pace_u, windup_u, delay_u = np.sqrt(np.diag(p_cov))

        log(f'{cls.__name__} fit of motion model complete:')
        log(f'pace       = {pace_n:12.6g} +/- {pace_u:12.6g} s / {cls._span_units}')
        log(f'windup     = {windup_n:12.6f} +/- {windup_u:12.6f} s')
        log(f'delay      = {delay_n:12.6f} +/- {delay_u:12.6f} s')
        log('model time = (pace * span + windup) / speed + delay')

        return cls(pace_n, windup_n, delay_n)

    @classmethod
    def from_file(cls, path: Optional[AnyPath] = None) -> Self:
        if path is None:
            path = Path(calibration_drc) / cls._yaml_filename
        try:
            with open(Path(path), 'r') as yaml_file:
                return cls(**yaml.safe_load(yaml_file))
        except OSError as e:
            raise OSError(f'{e.strerror}: {path}. Please run {cls._program_name} first.')

    def to_file(self, outdir: Optional[AnyPath] = None) -> None:
        if outdir is None:
            outdir = calibration_drc
        yaml_path = Path(outdir) / self._yaml_filename
        with open(yaml_path, 'w') as yaml_file:
            yaml.safe_dump(asdict(self), yaml_file)  # type: ignore[arg-type]
        log(f'{self.__class__.__name__} saved to {yaml_path}.')
