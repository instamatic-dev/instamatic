from __future__ import annotations

import dataclasses
import logging
import time
import warnings
from collections.abc import MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import pandas as pd
import yaml
from tqdm import tqdm
from typing_extensions import Self

from instamatic.calibrate.filenames import CALIB_MOVIE_DELAYS
from instamatic.config import calibration_drc

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


class CalibWarning(RuntimeWarning):
    """A runtime warning that suggests instability/problems of calibration."""


@dataclasses.dataclass
class CalibMovieDelays:
    """A simple dataclass that stores the differences between expected and
    observed performance of `ctrl.get_movie`. It accepts at initialization
    and stores four averaged time spans between the following events:

    - init_time - between `get_movie` being called and frame 1 being started;
    - yield_time - between frame being reported to end being yielded;
    - wait_time - between frame N being yielded and frame N+1 being started;
    - return_time - between the last frame being yielded and get_movie ending.

    In addition, it reveals the property `dead_time`: an estimated time "gap"
    between individual frames of `get_movie`, crucial if movie is coupled with
    e.g. rotation. I/O operations are handled by `CalibMovieDelaysMapping`.
    """

    init_time: float
    yield_time: float
    wait_time: float
    return_time: float

    @property
    def dead_time(self) -> float:
        """An estimated time "gap" between individual frames of `get_movie`; To
        get a frame every 1 sec, call `get_movie` with exposure=1-dead_time."""
        return self.yield_time + self.wait_time

    @classmethod
    def from_dict(cls, dict_: dict) -> CalibMovieDelays:
        field_names = {f.name for f in dataclasses.fields(cls)}  # noqa type OK
        return cls(**{k: v for k, v in dict_.items() if k in field_names})

    @classmethod
    def from_file(
        cls,
        exposure: float = 1.0,
        header_keys: Tuple[str] = (),
        header_keys_common: Tuple[str] = (),
        path: Optional[str] = None,
    ) -> CalibMovieDelays:
        calib_map = CalibMovieDelaysMapping.from_file(path)
        calib_conditions = (exposure, header_keys, header_keys_common)
        calib = calib_map.get(calib_conditions, None)
        if calib is None:
            header_keys_str = ','.join(header_keys)
            header_keys_common_str = ','.join(header_keys_common)
            raise KeyError(
                f'Calibration for conditions {calib_conditions} not found. '
                f"Please run 'instamatic.calibrate_movie_delays -e {exposure:.6f} "
                f'-a "{header_keys_str}" -c "{header_keys_common_str}" first.'
            )
        return calib

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> CalibMovieDelays:
        return calibrate_movie_delays_live(ctrl=ctrl, **kwargs)

    def to_dict(self) -> Dict[str, float]:
        return dataclasses.asdict(self)  # noqa

    def to_file(
        self,
        path: Optional[str] = None,
        exposure: float = 1.0,
        header_keys: Tuple[str] = (),
        header_keys_common: Tuple[str] = (),
    ) -> None:
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        if Path(path).is_file():
            calib_map = CalibMovieDelaysMapping.from_file(path)
        else:
            calib_map = CalibMovieDelaysMapping()
        calib_map[(exposure, header_keys, header_keys_common)] = self
        calib_map.to_file(path)


@dataclasses.dataclass(frozen=True)
class CalibConditions:
    """A key-type with calibration conditions for `CalibMovieDelaysMapping`"""

    exposure: float
    header_keys_variable: Tuple[str, ...]
    header_keys_common: Tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'exposure', round(self.exposure, 3))
        object.__setattr__(self, 'header_keys_variable', tuple(self.header_keys_variable))
        object.__setattr__(self, 'header_keys_common', tuple(self.header_keys_common))

    @classmethod
    def from_any(cls, a: CalibConditionsAny_T) -> Self:
        if isinstance(a, dict):
            a = [a[k.name] for k in dataclasses.fields(cls)]  # noqa
        return cls(*a)


CalibConditionsDict_T = Dict[str, Union[float, Tuple[str, ...]]]
CalibConditionsTuple_T = Tuple[float, Tuple[str, ...], Tuple[str, ...]]
CalibConditionsAny_T = Union[CalibConditionsDict_T, CalibConditionsTuple_T]
ListedCalibMovieDelays_T = List[Dict[str, Dict[str, Union[List[str], float]]]]


class CalibMovieDelaysMapping(MutableMapping):
    """Calibrated delays depend on the exposure time as well information
    requested for movie header. This information can be split into two kinds:
    common information is collected once at the beginning of the movie,
    potentially leading to long initialization times. Variable information is
    collect for each image individually while it is gathered, potentially
    artificially inflating the "dead" time. This class manages instances of
    `CalibMovieDelays` calibrated for each combination of exposure and headers.

    From the code perspective, the easiest way to express calibration conditions
    i.e. exposure, variable headers, and common headers, is via a tuple.
    Unfortunately, tuples can't be used as a key for serialization.
    This mapping internally uses `CalibConditions` as a key, but allows indexing
    via `CalibConditionsDict_T` or `CalibConditionsTuple_T` for convenience.
    It can also serialize/deserialize self to/from a `ListedCalibMovieDelays_T`.
    """

    def __init__(self, dict_: Optional[Dict[CalibConditions, CalibMovieDelays]] = None) -> None:
        self.dict: Dict[CalibConditions, CalibMovieDelays] = dict_ or {}

    def __delitem__(self, key: CalibConditionsAny_T) -> None:
        del self.dict[CalibConditions.from_any(key)]

    def __getitem__(self, key: CalibConditionsAny_T) -> CalibMovieDelays:
        return self.dict[CalibConditions.from_any(key)]

    def __setitem__(self, key: CalibConditionsAny_T, value: CalibMovieDelays) -> None:
        self.dict[CalibConditions.from_any(key)] = value

    def __iter__(self) -> Iterator:
        return iter(self.dict)

    def __len__(self) -> int:
        return len(self.dict)

    def to_list(self) -> ListedCalibMovieDelays_T:
        list_ = []
        for conditions, results in self.dict.items():
            c = dataclasses.asdict(conditions)  # noqa
            r = results.to_dict()
            list_.append({'calibration_conditions': c, 'calibration_results': r})
        return list_

    @classmethod
    def from_list(cls, listed: list[Dict[str, Any]]) -> Self:
        mapping = {}
        for entry in listed:
            cond = CalibConditions.from_any(entry['calibration_conditions'])
            results = CalibMovieDelays.from_dict(entry['calibration_results'])
            mapping[cond] = results
        return cls(mapping)

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> Self:
        log(f'Reading {cls.__name__} from {path}')
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        try:
            with open(Path(path), 'r') as yaml_file:
                return cls.from_list(yaml.safe_load(yaml_file))
        except OSError as e:
            prog = 'instamatic.calibrate_movie_delays'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    def to_file(self, path: Optional[str] = None) -> None:
        log(f'Writing {self.__class__.__name__} to {path}')
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        with open(Path(path), 'w') as json_file:
            yaml.safe_dump(self.to_list(), json_file)
        log(f'{self} saved to {path}.')


class MovieTimes:
    """A 2D data class that stores the results of movie delay calibrations.

    Stores exposure, n_frames, as well as a table with timings, whose
    individual rows store timestamp series for all movies/cycles collected.
    A total of `3*N+2` cols, where `N = n_frames`, hold in chronological order:

    - "i": 1 time stamp right before `get_movie` initialization call;
    - "s#": N individual time stamps for the frame # collection start;
    - "e#": N individual time stamps for the frame # collection end;
    - "y#": N individual time stamps for the frame # being yielded;
    - "r": 1 time stamp right after `get_movie` return;
    """

    def __init__(self, n_frames: int = 20, exposure: float = 1.0) -> None:
        self.n_frames = n_frames
        self.exposure = exposure
        columns = ['i']  # make col names: [i, s1, e1, y1, s2, e2, y2, ..., r]
        for i in range(n_frames):
            columns.extend(f's{i} e{i} y{i}'.split())
        columns.append('r')
        self.table = pd.DataFrame(columns=columns)

    @lru_cache(maxsize=2)
    def _get_deltas(self, _cache_flag: Tuple[int, int]) -> pd.DataFrame:
        """Internal cache of the `deltas` using `self.table.shape` as flag."""
        return self.table.diff(axis=1).iloc[:, 1:]

    @property
    def deltas(self) -> pd.DataFrame:
        """A `n_cycles x 3 * N + 1` table of rolling timespan differences."""
        return self._get_deltas(self.table.shape)

    @property
    def init_times(self) -> pd.Series:
        """Timespan between calling `get_movie` & requesting first frame."""
        return self.deltas.iloc[:, 0]

    @property
    def frame0_times(self) -> pd.Series:
        """Timespan between requesting & receiving the first frame only."""
        return self.deltas.iloc[:, 1]

    @property
    def frame1_times(self) -> pd.Series:
        """Mean timespan between requesting & receiving 2nd+ frames."""
        frame1_i_loc = [4 + 3 * n for n in range(self.n_frames - 1)]
        return self.deltas.iloc[:, frame1_i_loc].mean(axis=1)

    @property
    def yield_times(self) -> pd.Series:
        """Mean timespan between receiving and yielding each movie frame."""
        yield_i_loc = [2 + 3 * n for n in range(self.n_frames)]
        return self.deltas.iloc[:, yield_i_loc].mean(axis=1)

    @property
    def wait_times(self) -> pd.Series:
        """Mean timespan between yielding frame M and requesting frame M+1."""
        repeat_loc = [3 + 3 * n for n in range(self.n_frames - 1)]
        return self.deltas.iloc[:, repeat_loc].mean(axis=1)

    @property
    def return_times(self) -> pd.Series:
        """Timespan between yielding the last frame and returning the func."""
        return self.deltas.iloc[:, -1]

    @property
    def total_times(self) -> pd.Series:
        """Total timespan of entire `ctrl.get_movie`, from call to return."""
        return self.table.iloc[:, -1] - self.table.iloc[:, 0]

    def add_timestamps(self, timestamps: Sequence[float]) -> None:
        """Add `timestamps` sequence as a new row to `self.table`."""
        new = pd.DataFrame([timestamps], columns=self.table.columns)
        self.table = new if self.table.empty else pd.concat([self.table, new], axis=0)


def calibrate_movie_delays_live(
    ctrl: 'TEMController',
    exposure: float,
    header_keys: Optional[Tuple[str]] = None,
    header_keys_common: Optional[Tuple[str]] = None,
    outdir: Optional[str] = None,
):
    """Calibrate and save the delays of the `TEMController.get_movie` method`.

    Intuitively, collecting an N-frame movie with X-second exposure should take
    exactly N*X seconds. However, hardware specification and software
    implementation for each detector may differ, leading to different delays.
    This calibration aims to quickly estimate the delays for `ctrl.get_movie`
    call given provided exposure, header_keys, and header_keys_common.

    The delays calculations performed here assumes that the total time
    taken by the `ctrl.get_movie` call follows the following formula:

    total = init + (exposure + yield + wait) * (N-1) + exposure + yield + return

    where N is the number of frames collected in a movie (20 in calibration).
    Individual variables present above represent the following time spans:

    - total: total time from iterating `get_movie` to receiving a return value;
    - exposure: exact value of "exposure" passed to `VideoStream.get_movie`;
    - yield: time between controller receiving a frame and yielding it;
    - wait: time between yielding a (non-final) frame and starting a new one;
    - return: time between yielding the final frame and yielding None.

    The calibration is performed by timing execution of `ctrl.get_movie` with
    given parameters 5 times, deriving mean init / yield / wait / return times,
    and saving / returning them as an instance of `CalibMovieDelays`. The
    calibration might raise warnings in case the times are suspicious. Produced
    `CalibMovieDelays` instance can be then used to improve accuracy of
    other methods, e.g. by taking the `CalibMovieDelays.dead_time` into account
    when coupling `ctrl.get_movie` with timed methods e.g. scanning or rotation.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    exposures: `float`
        Exposure time for which `get_movie` delays will be estimated.
    header_keys: `Optional[Tuple[str]]`
        (Variable) header keys i.e. collected individually for/during each frame
        for which `get_movie` delays will be estimated.
    common_header_keys: `Optional[Tuple[str]]`
        Common header keys i.e. collected once before the movie starts only
        for which `get_movie` delays will be estimated.
    outdir: `str` or None
        Directory where the final calibration file will be saved.
    return:
        instance of `CalibStageRotation` class with `get_movie` delay details
    """

    n_frames = 20
    n_rounds = 5

    movie_kwargs = {}
    if header_keys is not None:
        movie_kwargs['header_keys'] = header_keys
    if header_keys_common is not None:
        movie_kwargs['header_keys_common'] = header_keys_common

    log('Calibration of `get_movie` for the following input started')
    log(f'exposure: {exposure} s')
    log(f'header_keys: {header_keys}')
    log(f'header_keys_common: {header_keys_common}')

    def _get_movie_times(exposure_=1e-6) -> MovieTimes:
        """Benchmark `get_movie` and put the results into a `MovieTimes`."""
        # first single-frame movie dummy only updates the settings if needed
        _ = next(ctrl.get_movie(1, exposure_, **movie_kwargs))
        mt_ = MovieTimes(n_frames=n_frames, exposure=exposure)
        for _ in tqdm(range(n_rounds), desc='Collecting movie', unit='round'):
            movie_gen = ctrl.get_movie(n_frames, exposure_, **movie_kwargs)
            timestamps: list[float] = [time.perf_counter()]  # "i"
            for frame, header in movie_gen:
                timestamps.append(header['ImageGetTimeStart'])  # "s#"
                timestamps.append(header['ImageGetTimeEnd'])  # "e#"
                timestamps.append(time.perf_counter())  # "y#"
            timestamps.append(time.perf_counter())  # "r"
            mt_.add_timestamps(timestamps)
        return mt_

    ctrl.cam.block()
    try:
        mte = _get_movie_times(exposure)  # actual movie timestamps
        mtr = _get_movie_times(1e-6)  # reference movie with ~0 exposure
    finally:
        ctrl.cam.unblock()

    ratio = mte.frame1_times.mean() / mte.exposure
    if ratio > 1.1:
        msg = (
            f'Exposure times exceed expected by {(ratio - 1) * 100}%. '
            f'Consider using longer exposure or smaller header.'
        )
        warnings.warn(msg, CalibWarning)

    ratio = mtr.total_times.mean() / mte.total_times.mean()
    if ratio > 0.5:
        msg = (
            f'Total time is dominated ({ratio * 100}%) by header collection. '
            f'Consider using longer exposure or smaller header.'
        )
        warnings.warn(msg, CalibWarning)

    init_time = float((mte.init_times + mte.frame0_times - mte.frame1_times).mean())
    yield_time = float(mte.yield_times.mean())
    wait_time = float((mte.wait_times + mte.frame1_times - mte.exposure).mean())
    return_time = float(mte.return_times.mean())

    c = CalibMovieDelays(init_time, yield_time, wait_time, return_time)
    log(f'Calibration of `get_movie` complete: {c}')
    c.to_file(outdir, exposure, header_keys, header_keys_common)
    return c


def main_entry() -> None:
    import argparse

    description = """Calibrate the delays associated with `get_movie` protocol."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-e',
        '--exposure',
        type=float,
        default=1.0,
        help='Exposure to test the delay for in seconds. Default: 1',
    )

    parser.add_argument(
        '-a',
        '--variable_headers',
        type=str,
        default=None,
        help=(
            'Comma-delimited list of variable header keys to calibrate for. '
            'For default, see `src/instamatic/controller.py:MOVIE_HEADER_KEYS_VARIABLE`.'
        ),
    )

    parser.add_argument(
        '-c',
        '--common_headers',
        type=str,
        default=None,
        help=(
            'Comma-delimited list of common header keys to calibrate for. '
            'For default, see `src/instamatic/controller.py:MOVIE_HEADER_KEYS_COMMON`.'
        ),
    )

    parser.add_argument(
        '-o',
        '--outdir',
        type=str,
        help=(
            'Path to the directory where calibration file should be output. '
            'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
        ),
    )

    options = parser.parse_args()

    from instamatic.controller import TEMController, initialize

    kwargs = {'exposure': options.exposure}

    if options.variable_headers is None:
        kwargs['header_keys'] = TEMController.MOVIE_HEADER_KEYS_VARIABLE
    elif options.variable_headers == '':
        kwargs['header_keys'] = ()
    else:
        kwargs['header_keys'] = tuple(options.variable_headers.split(','))

    if options.common_headers is None:
        kwargs['header_keys_common'] = TEMController.MOVIE_HEADER_KEYS_COMMON
    elif options.common_headers == '':
        kwargs['header_keys_common'] = ()
    else:
        kwargs['header_keys_common'] = tuple(options.common_headers.split(','))

    if options.outdir:
        kwargs['outdir'] = options.outdir

    ctrl = initialize()
    calibrate_movie_delays_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
