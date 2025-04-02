from __future__ import annotations

import json
import logging
import time
from collections import UserDict
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from tqdm import tqdm

from instamatic.calibrate.filenames import CALIB_MOVIE_RATE
from instamatic.config import calibration_drc

logger = logging.getLogger(__name__)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ HELPER OBJECTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def log(s: str) -> None:
    logger.info(s)
    print(s)


# ~~~~~~~~~~~~~~~~~~~~~~~ MOVIE RATE CALIBRATION CLASS ~~~~~~~~~~~~~~~~~~~~~~~ #


class CalibMovieRate:
    """Calibrate the difference between requested and actual movie exposure
    and frame rate. Given `N = n_frames`, the time needed to run the full image
    collection always exceeds the simple sum and is modeled here as:

    total = init + (frame + yield + dead) * (N-1) + frame + yield + return

    Individual variables present above represent the following time spans:

    - total: total time from calling `get_movie` to receiving a return value;
    - frame: time since `VideoStream.get_movie` to return, should be ~exposure;
    - yield: time between controller receiving a frame and yielding it;
    - dead: time between yielding a (non-final) frame and starting a new one;
    - return: time between yielding the final frame and yielding None.

    The goal if this calibration is to, given expected "total exposure" per
    frame, find a numerical value of "get-movie-exposure" that satisfies it.
    """

    def __init__(
        self,
        init_time: float,
        frame_times: Union[pd.Series[float], Dict[float, float]],
        yield_time: float,
        dead_time: float,
        return_time: float,
    ) -> None:
        self.init_time = init_time
        self.frame_times = pd.Series(frame_times).sort_values(inplace=False)
        self.yield_time = yield_time
        self.dead_time = dead_time
        self.return_time = return_time

    def __repr__(self) -> str:
        return (
            f'CalibMovieRate('
            f'init_time={self.init_time}, '
            f'frame_times={self.frame_times.to_dict()}, '
            f'yield_time={self.yield_time}, '
            f'dead_time={self.dead_time}, '
            f'return_time={self.return_time})'
        )

    def exposure_requested_to_actual(self, exposure: float) -> float:
        idx = self.frame_times.index
        if exposure < idx.min() or exposure > idx.max():
            msg = (
                f'Requested exposure of {exposure} is beyond the calibration '
                f'range of {idx.min()} to {idx.max()} and can be unreliable!'
            )
            raise RuntimeWarning(msg)
        interpolator = interp1d(
            x=idx,
            y=self.frame_times.values,
            fill_value='extrapolate',
        )
        return interpolator(exposure)

    def exposure_actual_to_requested(self, exposure: float) -> float:
        idx = self.frame_times.index
        if exposure < idx.min() or exposure > idx.max():
            msg = (
                f'Requested exposure of {exposure} is beyond the calibration '
                f'range of {idx.min()} to {idx.max()} and can be unreliable!'
            )
            raise RuntimeWarning(msg)
        interpolator = interp1d(
            x=self.frame_times.values,
            y=idx,
            fill_value='extrapolate',
        )
        return interpolator(exposure)

    def plan_movie_exposure(self, target_exposure: float) -> float:
        """Exposure value such that (frame + dead) time ~= target_exposure."""
        target_exp_actual = target_exposure - self.yield_time - self.dead_time
        return self.exposure_actual_to_requested(target_exp_actual)

    @classmethod
    def from_dict(cls, dict_: dict) -> CalibMovieRate:
        return cls(**dict_)

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> CalibMovieRate:
        if path is None:
            path = Path(calibration_drc) / CALIB_MOVIE_RATE
        try:
            with open(Path(path), 'r') as json_file:
                return cls.from_dict(json.load(json_file))
        except OSError as e:
            prog = 'instamatic.calibrate_movie_rate'
            raise OSError(f'{e.strerror}: {path}. Please run {prog} first.')

    @classmethod
    def live(cls, ctrl: 'TEMController', **kwargs) -> CalibMovieRate:
        return calibrate_movie_rate_live(ctrl=ctrl, **kwargs)


class CalibMovieRateDict(UserDict):
    """A manager class for reading, writing `CalibMovieRate`s to one file."""

    # TODO


# ~~~~~~~~~~~~~~~~~~~~~~~ MOVIE RATE CALIBRATION SCRIPT ~~~~~~~~~~~~~~~~~~~~~~ #


class MovieTimes:
    """A 2D data class that stores the results of movie rate calibrations.

    Individual columns represent different preset conditions (i.e. exposures).
    A total of `3 * N + 2` rows, where `N = n_frames`, hold time-ordered:

    - "i": 1 time stamp right before `get_movie` initialization call;
    - "s#": N individual time stamps for the frame # collection start;
    - "e#": N individual time stamps for the frame # collection end;
    - "y#": N individual time stamps for the frame # being yielded;
    - "r": 1 time stamp right after `get_movie` return;
    """

    def __init__(self, n_frames: int = 5) -> None:
        self.n_frames = n_frames
        index = ['i']
        for i in range(n_frames):
            index.extend(f's{i} e{i} y{i}'.split())
        index.append('r')
        self.table = pd.DataFrame(index=index)
        self.deltas: Optional[pd.DataFrame] = None

    def recalculate_stats(self) -> None:
        """Return copy of self with time-deltas in seconds in 3N-1 rows."""
        self.deltas = self.table.diff().shift(-1)[:-1]
        # deltas['means'] = self.table.mean(axis=1)
        # deltas['stds'] = self.table.std(axis=1)

    @property
    def init_mean_time(self) -> float:
        return float(self.deltas.iloc[0].mean())

    @property
    def frame_mean_times(self) -> pd.Series:
        frame_loc = [1 + 3 * n for n in range(self.n_frames)]
        return self.deltas.iloc[frame_loc].mean()

    @property
    def yield_mean_time(self) -> float:
        yield_loc = [2 + 3 * n for n in range(self.n_frames)]
        return float(self.deltas.iloc[yield_loc].mean(axis=None))

    @property
    def dead_mean_time(self) -> float:
        repeat_loc = [3 + 3 * n for n in range(self.n_frames - 1)]
        return float(self.deltas.iloc[repeat_loc].mean(axis=None))

    @property
    def return_mean_time(self) -> float:
        return float(self.deltas.iloc[-1].mean())


def calibrate_movie_rate_live(
    ctrl: 'TEMController',
    exposures: Optional[Sequence[float]] = None,
    header_keys: Tuple[str] = None,
    header_keys_common: Tuple[str] = None,
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

    exposures = np.array(exposures or [10, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01])
    n_frames = 5

    get_movie_kwargs = {}
    if header_keys:
        get_movie_kwargs['header_keys'] = header_keys
    if header_keys_common:
        get_movie_kwargs['header_keys_common'] = header_keys_common

    movie_times = MovieTimes(n_frames=n_frames)
    ctrl.cam.block()
    try:
        total = n_frames * len(exposures)
        log(f'Starting movie rate calibration based on {total} points.')
        with tqdm(total=total) as progress_bar:
            for exposure in exposures:
                # first 1-frame movie dummy updates the settings as needed
                _ = next(ctrl.get_movie(1, exposure, **get_movie_kwargs))
                # creating actial movie generator here
                movie = ctrl.get_movie(n_frames, exposure, **get_movie_kwargs)
                timestamps: list[float] = [time.perf_counter()]  # "i"
                for frame, header in movie:
                    yield_time = time.perf_counter()
                    timestamps.append(header['ImageGetTimeStart'])  # "s#"
                    timestamps.append(header['ImageGetTimeEnd'])  # "e#"
                    timestamps.append(yield_time)  # "y#"
                    progress_bar.update(1)
                timestamps.append(time.perf_counter())  # "r"

                if timestamps[-1] - timestamps[0] <= 1.5 * (exposure * n_frames):
                    movie_times.table[exposure] = timestamps
                else:  # above some deviation it becomes unreliable
                    break
    finally:
        ctrl.cam.unblock()

    movie_times.recalculate_stats()
    print('deltas')
    print(movie_times.deltas)
    print('int_mean_std_time')
    print(movie_times.init_mean_time)
    print('mean times: frame, dead, return')
    print(movie_times.frame_mean_times)
    print(movie_times.return_mean_time)

    init_time = movie_times.init_mean_time
    exposure_times = movie_times.frame_mean_times
    yield_time = movie_times.yield_mean_time
    dead_time = movie_times.dead_mean_time
    return_time = movie_times.return_mean_time

    return CalibMovieRate(init_time, exposure_times, yield_time, dead_time, return_time)
    # TODO: for each header combination, a new calibration should be saved to the same file


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STANDALONE COMMAND ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def main_entry() -> None:
    import argparse

    description = """Calibrate the rotation speed setting of the stage."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    h = 'Comma-delimited list of exposure settings to calibrate. '
    h += 'Default: "10,5.,2.,1.,0.5,0.2,0.1,0.05,0.02,0.01".'
    parser.add_argument('-e', '--exposures', type=str, help=h)

    h = 'Path to the directory where calibration file should be output. '
    h += 'Default: "%%appdata%%/calib" (Windows) or "$AppData/calib" (Unix).'
    parser.add_argument('-o', '--outdir', type=str, help=h)

    options = parser.parse_args()

    from instamatic import controller

    kwargs = {}
    if options.exposures:
        kwargs['exposures'] = [float(a) for a in options.exposures.split(',')]

    ctrl = controller.initialize()
    calibrate_movie_rate_live(ctrl=ctrl, **kwargs)


if __name__ == '__main__':
    main_entry()
