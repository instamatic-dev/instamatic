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


def _normalize_speed(speed: Union[float, int]) -> Union[int, float]:
    """Return integer-valued speeds as int, so dict keys survive a YAML round
    trip."""
    speed = float(speed)
    return int(speed) if speed.is_integer() else speed


@dataclass
class SpeedModel:
    """Independent linear model of one speed setting: time = pace * span + delay.

    Here `delay` already includes any windup contribution at this setting.
    """

    pace: float  # seconds per span unit at this setting
    delay: float  # total constant delay at this setting, in seconds

    def __post_init__(self) -> None:
        self.pace = float(self.pace)
        self.delay = float(self.delay)


@dataclass
class MotionPlan(Generic[SpeedN]):
    """A set of motion parameters/outcomes nearest to the ones requested."""

    pace: float  # time it takes goniometer to cover 1 span unit (nm or degree)
    speed: Optional[SpeedN]  # speed setting to get pace, None = not supported
    total_delay: float  # total goniometer delay: delay + windup / speed


class SpanSpeedTime(NamedTuple):
    """A single measurement point used to calibrate stage motion speed.

    - span: the motion span expressed in degrees (rotation) or nm (translation);
    - speed: the speed setting used expressed in arbitrary TEM units;
    - time: time taken to travel span with speed expressed in seconds.
    """

    span: Span
    speed: Speed
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

    If the speed settings are not linearly related to the speed values (e.g.
    JEOL OverRateTxNum), `speed_models` holds one `SpeedModel` per setting,
    each fitted independently as time = pace * span + delay. In that case
    `pace`, `windup` and `delay` are `nan` and only `speed_models` is used.

    Concrete subclasses should provide:
      - units and axis labels for plotting
      - a `live` class method that runs live calibration and returns an instance
    """

    pace: float
    windup: float
    delay: float
    speed_options: Optional[NumericDomain] = None
    speed_models: Optional[dict[Union[int, float], SpeedModel]] = None

    def __post_init__(self) -> None:
        self.pace = float(self.pace)
        self.windup = float(self.windup)
        self.delay = float(self.delay)
        if isinstance(self.speed_options, dict):
            self.speed_options = NumericDomain(**self.speed_options)

        if self.speed_models is not None:
            self.speed_models = {
                _normalize_speed(k): SpeedModel(**v) if isinstance(v, dict) else v
                for k, v in self.speed_models.items()
            }

    @property
    def independent(self) -> bool:
        """True if each speed setting has its own independent model."""
        return self.speed_models is not None

    def _speed_model(self, speed: Speed) -> SpeedModel:
        """Model calibrated for exactly this speed setting."""
        assert self.speed_models is not None
        if speed is None or speed not in self.speed_models:
            raise ValueError(
                f'No independent calibration for speed setting {speed}. '
                f'Calibrated settings: {sorted(self.speed_models)}.'
            )
        return self.speed_models[speed]

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
        if self.speed_models is not None:
            m = self._speed_model(speed)
            return m.pace * span + m.delay
        return (self.pace * span + self.windup) / (speed or 1.0) + self.delay

    def span_time_to_speed(self, span: Span, time: float) -> float:
        """`speed` that best allows to move the stage by `span` in `time`."""
        if self.speed_models is not None:
            return min(
                self.speed_models,
                key=lambda s: abs(self.span_speed_to_time(span, s) - time),
            )
        return (self.pace * span + self.windup) / (time - self.delay)

    def time_speed_to_span(self, time: float, speed: Speed = None) -> float:
        """Maximum `span` covered with `speed` in `time` (including delay)."""
        if self.speed_models is not None:
            m = self._speed_model(speed)
            return (time - m.delay) / m.pace
        return ((speed or 1.0) * (time - self.delay) - self.windup) / self.pace

    def plan_motion(self, target_pace: float) -> MotionPlan:
        """Given target pace, find nearest pace, needed speed, and delay."""
        if self.speed_models is not None:
            nearest_speed = min(
                self.speed_models,
                key=lambda s: abs(self.speed_models[s].pace - abs(target_pace)),
            )
            m = self.speed_models[nearest_speed]
            return MotionPlan(m.pace, nearest_speed, m.delay)
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
        elif self.speed_models is not None:
            speeds = sorted(self.speed_models)
        elif self.speed_options is None:
            speeds = [None]
        elif isinstance(self.speed_options, NumericDomainConstrained):
            so: NumericDomainConstrained = self.speed_options
            speeds = list(np.linspace(so.lower_lim, so.upper_lim, 10))
        else:  # isinstance(calib.speed_options, NumericDomainDiscrete):
            speeds = sorted(getattr(self.speed_options, 'options', [1.0]))
        speeds = [s for s in speeds if s != 0 or self.independent]

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
        if not self.independent:
            ax.axhline(y=self.delay, color='r')

        colors = plt.colormaps['coolwarm'](np.linspace(0, 1, num=len(speeds)))
        handles: list[Line2D] = []
        for color, speed in zip(colors, speeds):
            for sst, fmt in plotted:
                spans = [s.span for s in sst if s.speed == speed]
                times = [s.time for s in sst if s.speed == speed]
                ax.plot(spans, times, fmt, color=color)
            label = f'Speed setting {speed:.2f}' if speed is not None else 'Default speed'
            handles.append(Line2D([], [], color=color, marker='o', label=label))

        ax.set_xlabel(f'Motion span [{self._span_units}]')
        ax.set_ylabel('Time required [s]')
        ax.set_title('Stage motion time vs span at different speeds')
        ax.legend(handles=handles, loc='best')
        plt.show()

    @classmethod
    def from_data(cls, sst: Sequence[SpanSpeedTime], independent: bool = False) -> Self:
        """Fit cls.model to span-speed-time points and init based on result.

        If `independent`, fit each speed setting with its own linear
        model instead.
        """
        sst_array = np.array(sst).T
        spans = np.array(sst_array[0], dtype=float)
        speeds = np.array(sst_array[1], dtype=float)
        times = np.array(sst_array[2], dtype=float)

        if independent:
            return cls._from_data_independent(spans, speeds, times)

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
    def _from_data_independent(
        cls,
        spans: np.ndarray,
        speeds: np.ndarray,
        times: np.ndarray,
    ) -> Self:
        """Fit time = pace * span + delay separately for every speed setting."""
        if np.any(np.isnan(speeds)):
            raise ValueError('Independent calibration needs explicit speed settings.')

        log(f'{cls.__name__} independent fit of motion model per speed setting:')
        models: dict[Union[int, float], SpeedModel] = {}
        for speed in np.unique(speeds):
            mask = speeds == speed
            if len(np.unique(spans[mask])) < 2:
                raise ValueError(f'Need at least 2 distinct spans for speed {speed}.')
            p, p_cov = curve_fit(
                CalibStageMotion.model2, spans[mask], ydata=times[mask], p0=[1, 0]
            )
            pace_n, delay_n = p
            pace_u, delay_u = np.sqrt(np.diag(p_cov))
            models[_normalize_speed(speed)] = SpeedModel(pace_n, delay_n)
            log(
                f'speed {speed:g}: pace = {pace_n:12.6g} +/- {pace_u:12.6g} s / {cls._span_units}'
            )
            log(f'speed {speed:g}: delay = {delay_n:11.6f} +/- {delay_u:12.6f} s')
        log('model time = pace * span + delay (separately for each speed setting)')

        nan = float('nan')
        return cls(nan, nan, nan, speed_models=models)

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
