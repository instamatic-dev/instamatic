from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections import UserDict
from collections.abc import MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from tqdm import tqdm
from typing_extensions import Self

from instamatic.calibrate.filenames import CALIB_MOVIE_DELAYS
from instamatic.config import calibration_drc

logger = logging.getLogger(__name__)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ HELPER OBJECTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def log(s: str) -> None:
    logger.info(s)
    print(s)


# ~~~~~~~~~~~~~~~~~~~~~~~ MOVIE RATE CALIBRATION CLASS ~~~~~~~~~~~~~~~~~~~~~~~ #


@dataclasses.dataclass
class CalibMovieDelays:
    """Calibrate the difference between requested and actual movie exposure
    and frame rate. Given `n = n_frames`, the time needed to run the full image
    collection always exceeds the simple sum and is modeled here as:

    total = init + (exposure + yield + wait) * (n-1) + exposure + yield + return

    Individual variables present above represent the following time spans:

    - total: total time from calling `get_movie` to receiving a return value;
    - exposure: declared exposure time passed to `VideoStream.get_movie`;
    - yield: time between controller receiving a frame and yielding it;
    - wait: time between yielding a (non-final) frame and starting a new one;
    - return: time between yielding the final frame and yielding None.

    When requesting a movie with n frames, the total call time will exceed
    `n * exposure` due to initialization / dead time / finalization delays.
    In particular, to get 1 frame every `exposure` seconds, the "declared"
    exposure must be shorter by a `dead_time` defined here. The measurement
    also starts delayed by `init_time` and ends `return_time` late.

    The last parameter, `min_exposure`, declares the lowest value of exposure
    for which the calibration has been performed and follows the same trends.
    """

    init_time: float
    yield_time: float
    wait_time: float
    return_time: float
    min_exposure: float = 0.0

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
        header_keys: Tuple[str] = (),
        header_keys_common: Tuple[str] = (),
        path: Optional[str] = None,
    ) -> CalibMovieDelays:
        calib_map = CalibMovieDelaysMapping.from_file(path)
        calib = calib_map.get((header_keys, header_keys_common))
        if calib is None:
            log('CalibMovieDelays for specified header keys not found. Calibrating...')
            calib = calibrate_movie_delays_live(header_keys, header_keys_common)
            calib_map[(header_keys, header_keys_common)] = calib
            calib_map.to_file(path)
        return calib

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> CalibMovieDelays:
        return calibrate_movie_delays_live(ctrl=ctrl, **kwargs)


class CalibMovieDelaysMapping(MutableMapping):
    """Calibrated delays depend on the information requested in movie header:
    requesting a lot of common information might elongate the initialization,
    whereas large per-image headers will raise the feasible `min_exposure`.
    This class loads, stores, and saves instances of `CalibMovieDelays`
    calibrated for each combination of the header.
    """

    TwoTuples_T = Tuple[Tuple[str, ...], Tuple[str, ...]]

    def __init__(self, dict_: Dict[str, CalibMovieDelays]) -> None:
        self.dict = dict_

    def __delitem__(self, k: Union[str, TwoTuples_T]) -> None:
        del self.dict[k if isinstance(k, str) else self.sequences_to_str(*k)]

    def __getitem__(self, k: Union[str, TwoTuples_T]) -> CalibMovieDelays:
        return self.dict[k if isinstance(k, str) else self.sequences_to_str(*k)]

    def __len__(self) -> int:
        return len(self.dict)

    def __iter__(self) -> Iterator:
        return self.dict.__iter__()

    def __setitem__(self, k, v) -> None:
        self.dict[k if isinstance(k, str) else self.sequences_to_str(*k)] = v

    @staticmethod
    def str_to_tuples(key: str) -> TwoTuples_T:
        """Convert a "t11,t12;t21,t22"-form string into 2 tuples t1 & t2."""
        header_keys_common, header_keys_variable = key.split(';', 2)
        header_keys_common = tuple(sorted(header_keys_common.split(',')))
        header_keys_variable = tuple(sorted(header_keys_variable.split(',')))
        return header_keys_common, header_keys_variable

    @staticmethod
    def sequences_to_str(t1: Sequence[str, ...], t2: Sequence[str, ...]) -> str:
        """Convert 2 sequences t1 & t2 into a "t11,t12;t21,t22"-form str."""
        return ','.join(sorted(t1)) + ';' + ','.join(sorted(t2))

    @classmethod
    def from_dict(cls, dict_: Dict[str, Dict[str, float]]) -> Self:
        return cls({k: CalibMovieDelays.from_dict(v) for k, v in dict_.items()})

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> Self:
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        try:
            with open(Path(path), 'r') as json_file:
                return cls.from_dict(json.load(json_file))
        except OSError as e:
            prog = 'instamatic.calibrate_movie_delays'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        return {k: v.to_dict() for k, v in self.dict}

    def to_file(self, path: Optional[str] = None) -> None:
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_DELAYS
        with open(Path(path), 'w') as json_file:
            json.dump(self.to_dict(), json_file)
        log(f'{self} saved to {path}.')


# ~~~~~~~~~~~~~~~~~~~~~~~ MOVIE RATE CALIBRATION SCRIPT ~~~~~~~~~~~~~~~~~~~~~~ #


class MovieTimes:
    """A 2D data class that stores the results of movie delay calibrations.

    Individual columns represent different preset conditions (i.e. exposures).
    A total of `3 * N + 2` rows, where `N = n_frames`, hold time-ordered:

    - "i": 1 time stamp right before `get_movie` initialization call;
    - "s#": N individual time stamps for the frame # collection start;
    - "e#": N individual time stamps for the frame # collection end;
    - "y#": N individual time stamps for the frame # being yielded;
    - "r": 1 time stamp right after `get_movie` return;
    """

    def __init__(self, n_frames: int = 10) -> None:
        self.n_frames = n_frames
        index = ['i']
        for i in range(n_frames):
            index.extend(f's{i} e{i} y{i}'.split())
        index.append('r')
        self.table = pd.DataFrame(index=index)

    @lru_cache(maxsize=2)
    def _get_deltas(self, _cache_flag: Tuple[int, int]) -> pd.DataFrame:
        return self.table.diff().shift(-1)[:-1]

    @property
    def deltas(self) -> pd.DataFrame:
        return self._get_deltas(self.table.shape)

    @property
    def init_times(self) -> pd.Series:
        return self.deltas.iloc[0]

    @property
    def frame0_times(self) -> pd.Series:
        return self.deltas.iloc[1]

    @property
    def frame1_times(self) -> pd.Series:
        frame1_i_loc = [4 + 3 * n for n in range(self.n_frames - 1)]
        return self.deltas.iloc[frame1_i_loc].mean(axis=0)

    @property
    def yield_times(self) -> pd.Series:
        yield_i_loc = [2 + 3 * n for n in range(self.n_frames)]
        return self.deltas.iloc[yield_i_loc].mean(axis=0)

    @property
    def wait_times(self) -> pd.Series:
        repeat_loc = [3 + 3 * n for n in range(self.n_frames - 1)]
        return self.deltas.iloc[repeat_loc].mean(axis=0)

    @property
    def return_times(self) -> pd.Series:
        return self.deltas.iloc[-1]

    @property
    def total_times(self) -> pd.Series:
        return (
            self.init_times
            + self.return_times
            + self.frame0_times
            - self.frame1_times
            + self.n_frames * (self.frame1_times + self.yield_times + self.wait_times)
        )

    def add_column(self, exposure: float, timestamps: Sequence[float]) -> None:
        """Add `timestamps` or raise `ValueError` if they deviate too much."""
        n = self.n_frames
        ts = np.array(timestamps)
        if self.table.shape[1] < 3:  # too small sample
            pass
        else:
            total_delays = self.total_times - n * self.table.keys()
            timestamps_delays = ts[-1] - ts[0] - n * exposure
            if timestamps_delays > total_delays.mean() + 3 * total_delays.std():
                raise ValueError('Total delays exceed predicted mean + 3 sigma')
            elif (ts[2 : 2 + 3 * n : 3] - ts[2 : 2 + 3 * n : 3]).mean() > 1.5 * exposure:
                raise ValueError('Logged exposure time exceeds declared by >50%')
        self.table[exposure] = timestamps


def calibrate_movie_delays_live(
    ctrl: 'TEMController',
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

    exposures = np.array([1 / 2 ** (n**1 / 10) for n in range(1, 101)])
    n_frames = 10

    get_movie_kwargs = {}
    if header_keys:
        get_movie_kwargs['header_keys'] = header_keys
    if header_keys_common:
        get_movie_kwargs['header_keys_common'] = header_keys_common

    log('Calibration of `get_movie` for the following keys started')
    log(f'header_keys: {header_keys}')
    log(f'header_keys_common: {header_keys_common}')

    mt = MovieTimes(n_frames=n_frames)
    ctrl.cam.block()
    try:
        for exposure in tqdm(exposures):
            # first 1-frame movie dummy updates the settings as needed
            _ = next(ctrl.get_movie(1, exposure, **get_movie_kwargs))
            for attempt in range(10):
                # creating actual movie generator here
                movie = ctrl.get_movie(n_frames, exposure, **get_movie_kwargs)
                timestamps: list[float] = [time.perf_counter()]  # "i"
                for frame, header in movie:
                    yield_time = time.perf_counter()
                    timestamps.append(header['ImageGetTimeStart'])  # "s#"
                    timestamps.append(header['ImageGetTimeEnd'])  # "e#"
                    timestamps.append(yield_time)  # "y#"
                timestamps.append(time.perf_counter())  # "r"
                try:
                    mt.add_column(exposure, timestamps)
                except ValueError as e:
                    msg = 'Exposure {}, attempt {}: Calibration failed: {}'
                    log(msg.format(exposure, attempt, e))
                else:
                    break  # Do not test again if a column was added successfully
            else:
                break  # Do not continue if 10 consecutive attempts just failed
    finally:
        ctrl.cam.unblock()

    init_time = float((mt.init_times + mt.frame0_times - mt.frame1_times).mean())
    yield_time = float(mt.yield_times.mean())
    wait_time = float((mt.wait_times + mt.frame1_times - mt.table.keys()).mean())
    return_time = float(mt.return_times.mean())
    min_exposure = float(min(mt.table.keys()))

    c = CalibMovieDelays(init_time, yield_time, wait_time, return_time, min_exposure)
    log(f'Calibration of `get_movie` complete: {c}')
    return c


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STANDALONE COMMAND ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def main_entry() -> None:
    import argparse

    description = """Calibrate the rotation speed setting of the stage."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Comma-delimited list of exposure settings to calibrate. '
    h += 'Default: "10,5.,2.,1.,0.5,0.2,0.1,0.05,0.02,0.01".'
    parser.add_argument('-h', '--headers', type=str, help=h)

    h = 'Comma-delimited list of exposure settings to calibrate. '
    h += 'Default: "10,5.,2.,1.,0.5,0.2,0.1,0.05,0.02,0.01".'
    parser.add_argument('-c', '--common', type=str, help=h)

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

    options = parser.parse_args()

    from instamatic import controller

    kwargs = {}
    if options.exposures:
        kwargs['exposures'] = [float(a) for a in options.exposures.split(',')]

    ctrl = controller.initialize()
    calibrate_movie_delays_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
