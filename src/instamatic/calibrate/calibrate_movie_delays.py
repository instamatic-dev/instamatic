from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence, Tuple, Union

import pandas as pd
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
    """Calibrate the difference between requested and actual movie exposure
    and frame rate. Given `n = n_frames`, the time needed to run the full image
    collection always exceeds the naive product and instead is modeled here as:

    total = init + (exposure + yield + wait) * (n-1) + exposure + yield + return

    Individual variables present above represent the following time spans:

    - total: total time from calling `get_movie` to receiving a return value;
    - exposure: exact constant "exposure" passed to `VideoStream.get_movie`;
    - yield: time between controller receiving a frame and yielding it;
    - wait: time between yielding a (non-final) frame and starting a new one;
    - return: time between yielding the final frame and yielding None.

    When requesting a movie with n frames, the total call time will exceed
    `n * exposure` due to initialization / dead time / finalization delays.
    In particular, to get 1 frame every `exposure` sec, the "declared" exposure
    must be shorter by a `dead_time = yield_time + wait_time`. The measurement
    also starts delayed by `init_time` and ends `return_time` late.
    """

    init_time: float
    yield_time: float
    wait_time: float
    return_time: float

    @property
    def dead_time(self) -> float:
        """Subtract it from your target exposure to get exposure needed."""
        return self.yield_time + self.wait_time

    @classmethod
    def from_dict(cls, dict_: dict) -> CalibMovieDelays:
        return cls(**dict_)

    @classmethod
    def from_file(
        cls,
        ctrl: 'TEMController',
        exposure: float = 1.0,
        header_keys: Tuple[str] = (),
        header_keys_common: Tuple[str] = (),
        path: Optional[str] = None,
    ) -> CalibMovieDelays:
        calib_map = CalibMovieDelaysMapping.from_file(path)
        calib = calib_map.get((exposure, header_keys, header_keys_common))
        if calib is None:
            log(f'{cls.__name__} for specified header keys not found. Calibrating...')
            calib = calibrate_movie_delays_live(ctrl, exposure, header_keys, header_keys_common)
            calib_map[(exposure, header_keys, header_keys_common)] = calib
            calib_map.to_file(path)
        return calib

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> CalibMovieDelays:
        return calibrate_movie_delays_live(ctrl=ctrl, **kwargs)

    def to_dict(self) -> Dict[str, float]:
        return dataclasses.asdict(self)

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


class CalibMovieDelaysMapping(MutableMapping):
    """Calibrated delays depend on the exposure time as well as information
    requested in movie header: requesting a lot of common information might
    elongate the initialization, large per-image headers may take too long to
    collect during `exposure`, artificially inflating yield times.
    This class loads, stores, and saves instances of `CalibMovieDelays`
    calibrated for each combination of exposure and common/variable header.

    Instances of `CalibMovieDelays` are indexed using a composite string key,
    which takes form "exposure;common,header,elements;variable,header,elements".
    However, this class also allows accessing instances using the tuple-form.
    """

    ExposureHeadersHeaders_T = Tuple[float, Tuple[str, ...], Tuple[str, ...]]

    def __init__(self, dict_: Dict[str, CalibMovieDelays] = None) -> None:
        self.dict = dict_ if dict_ else {}

    def __delitem__(self, k: Union[str, ExposureHeadersHeaders_T]) -> None:
        del self.dict[k if isinstance(k, str) else self.ehh_to_str(*k)]

    def __getitem__(self, k: Union[str, ExposureHeadersHeaders_T]) -> CalibMovieDelays:
        return self.dict[k if isinstance(k, str) else self.ehh_to_str(*k)]

    def __len__(self) -> int:
        return len(self.dict)

    def __iter__(self) -> Iterator:
        return self.dict.__iter__()

    def __setitem__(self, k, v) -> None:
        self.dict[k if isinstance(k, str) else self.ehh_to_str(*k)] = v

    @staticmethod
    def str_to_ehh(key: str) -> ExposureHeadersHeaders_T:
        """Convert a "1.0;t11,t12;t21"-form str to float & tuples t1 & t2."""
        exposure, header_keys_common, header_keys_variable = key.split(';', 3)
        header_keys_common = tuple(sorted(header_keys_common.split(',')))
        header_keys_variable = tuple(sorted(header_keys_variable.split(',')))
        return float(exposure), header_keys_common, header_keys_variable

    @staticmethod
    def ehh_to_str(e: float, t1: Sequence[str, ...], t2: Sequence[str, ...]) -> str:
        """Convert float & tuples t1 & t2 to "e;t11,t12;t21,t22"-form str."""
        return f'{round(e, 3):.3f};' + ','.join(sorted(t1)) + ';' + ','.join(sorted(t2))

    @classmethod
    def from_dict(cls, dict_: Dict[str, Dict[str, float]]) -> Self:
        return cls({k: CalibMovieDelays.from_dict(v) for k, v in dict_.items()})

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> Self:
        log(f'Reading {cls.__name__} from {path}')
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        try:
            with open(Path(path), 'r') as json_file:
                return cls.from_dict(json.load(json_file))
        except OSError as e:
            prog = 'instamatic.calibrate_movie_delays'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        return {k: v.to_dict() for k, v in self.dict.items()}

    def to_file(self, path: Optional[str] = None) -> None:
        log(f'Writing {self.__class__.__name__} to {path}')
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        with open(Path(path), 'w') as json_file:
            json.dump(self.to_dict(), fp=json_file, indent=4, sort_keys=True)


# ~~~~~~~~~~~~~~~~~~~~~~~ MOVIE RATE CALIBRATION SCRIPT ~~~~~~~~~~~~~~~~~~~~~~ #


class MovieTimes:
    """A 2D data class that stores the results of movie delay calibrations.

    Individual columns store unique attempts for a given exposure.
    A total of `3 * N + 2` rows, where `N = n_frames`, holds ordered timestamps:

    - "i": 1 time stamp right before `get_movie` initialization call;
    - "s#": N individual time stamps for the frame # collection start;
    - "e#": N individual time stamps for the frame # collection end;
    - "y#": N individual time stamps for the frame # being yielded;
    - "r": 1 time stamp right after `get_movie` return;
    """

    def __init__(self, n_frames: int = 20, exposure: float = 1.0) -> None:
        self.n_frames = n_frames
        self.exposure = exposure
        columns = ['i']
        for i in range(n_frames):
            columns.extend(f's{i} e{i} y{i}'.split())
        columns.append('r')
        self.table = pd.DataFrame(columns=columns)

    @lru_cache(maxsize=2)
    def _get_deltas(self, _cache_flag: Tuple[int, int]) -> pd.DataFrame:
        """Internal cache of the `deltas` using `self.table` shape as flag."""
        return self.table.diff(axis=1).iloc[:, 1:]

    @property
    def deltas(self) -> pd.DataFrame:
        """A `3 * N + 1 x len(exposures)` table of rolling timespan deltas."""
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

    def add_timestamps(self, exposure: float, timestamps: Sequence[float]) -> None:
        """Add `timestamps` or raise `ValueError` if they deviate too much."""
        new = pd.DataFrame([timestamps], columns=self.table.columns)
        self.table = new if self.table.empty else pd.concat([self.table, new], axis=0)


def calibrate_movie_delays_live(
    ctrl: 'TEMController',
    exposure: float,
    header_keys: Tuple[str] = (),
    header_keys_common: Tuple[str] = (),
    outdir: Optional[str] = None,
):
    """Calibrate the `get_movie` function. Intuitively, collecting an N-frame
    movie with X-second exposure should take N*X seconds. However, the hardware
    specification and software implementation for each detector differ, leading
    to deviations. This calibration aims to take this effect into account and
    allow scheduling movies whose frame time better reflects the request.

    ctrl: instance of `TEMController`
        contains tem + cam interface
    exposures: `Optional[Sequence[float]]`
        Alpha rotations whose speed will be measured. Default: range(1, 11, 1).
    outdir: `str` or None
        Directory where the final calibration file will be saved.

    return:
        instance of `CalibStageRotation` class with conversion methods
    """

    n_frames = 20

    m_kwargs = {}
    if header_keys:
        m_kwargs['header_keys'] = header_keys
    if header_keys_common:
        m_kwargs['header_keys_common'] = header_keys_common

    log('Calibration of `get_movie` for the following input started')
    log(f'exposure: {exposure} s')
    log(f'header_keys: {header_keys}')
    log(f'header_keys_common: {header_keys_common}')

    def _get_movie_times(mt: MovieTimes, movie_gen: Iterator) -> None:
        """Generate a `MovieTimes` instance with timings for iterator."""
        timestamps: list[float] = [time.perf_counter()]  # "i"
        for frame, header in movie_gen:
            yield_time = time.perf_counter()
            timestamps.append(header.get('ImageGetTimeStart', yield_time))  # "s#"
            timestamps.append(header.get('ImageGetTimeEnd', yield_time))  # "e#"
            timestamps.append(yield_time)  # "y#"
        timestamps.append(time.perf_counter())  # "r"
        mt.add_timestamps(exposure, timestamps)

    ctrl.cam.block()
    try:
        # first 1-frame movie dummy updates the settings as needed
        _ = next(ctrl.get_movie(1, exposure, **m_kwargs))
        mt = MovieTimes(n_frames=n_frames, exposure=exposure)  # actual movie
        for _ in range(5):
            _get_movie_times(mt, ctrl.get_movie(n_frames, exposure, **m_kwargs))
        _ = next(ctrl.get_movie(1, 1e-6, **m_kwargs))
        mt_ref = MovieTimes(n_frames=n_frames, exposure=1e-6)  # header only
        for _ in range(5):
            _get_movie_times(mt_ref, ctrl.get_movie(n_frames, 1e-6, **m_kwargs))
    finally:
        ctrl.cam.unblock()

    ratio = mt.frame1_times.mean() / mt.exposure
    if ratio > 1.1:
        raise CalibWarning(
            f'Exposure times exceed expected by {(ratio-1)/100}%.'
            f' Consider using longer exposure or smaller header.'
        )

    init_time = float((mt.init_times + mt.frame0_times - mt.frame1_times).mean())
    yield_time = float(mt.yield_times.mean())
    wait_time = float((mt.wait_times + mt.frame1_times - mt.exposure).mean())
    return_time = float(mt.return_times.mean())

    c = CalibMovieDelays(init_time, yield_time, wait_time, return_time)
    log(f'Calibration of `get_movie` complete: {c}')
    c.to_file(outdir, exposure, header_keys, header_keys_common)
    return c


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STANDALONE COMMAND ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def main_entry() -> None:
    import argparse

    description = """Calibrate the delays associated with `get_movie` protocol."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Exposure to test the delay for in seconds. Default: 1'
    parser.add_argument('-e', '--exposure', type=float, default=1.0, help=h)

    h = 'Comma-delimited list of variable header keys to calibrate for. '
    h += 'For default, see `src/instamatic/controller.py:MOVIE_HEADER_KEYS_VARIABLE`.'
    parser.add_argument('-a', '--variable_headers', type=str, default=None, help=h)

    h = 'Comma-delimited list of common header keys to calibrate for. '
    h += 'For default, see `src/instamatic/controller.py:MOVIE_HEADER_KEYS_COMMON`.'
    parser.add_argument('-c', '--common_headers', type=str, default=None, help=h)

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

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
