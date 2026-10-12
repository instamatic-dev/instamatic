#!/usr/bin/env python3
"""benchmark_movie_rates.py.

Benchmark achievable frame rates using TEMController.get_movie.

Key behaviour:
- Uses `with ctrl.cam.blocked():` to avoid interference during timed acquisition.
- Optional warm-up cycle (single tiny-frame) before timed measurement.
- For each exposure requested, runs N rounds. Each round collects frames
  until at least `--min-duration` seconds elapse (or until a safe max frames limit).
- Does not save image data; only timestamps and basic header-derived times are recorded.
- Optional light processing per frame (`--process`) to emulate CPU work (np.mean).
- Prints summary after measurements and optionally writes raw CSV.

Use:
    python benchmark_movie_rates.py --exposures 0.01,0.02 --variable-headers BeamShift --rounds 3
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import math
import time
from pathlib import Path
from statistics import mean, stdev
from typing import Generator, Optional

import matplotlib.pyplot as plt

from instamatic.controller import TEMController, _ctrl, initialize
from instamatic.utils.iterating import pairwise

if not _ctrl:
    _ctrl: TEMController = initialize()


@dataclasses.dataclass
class FrameStamp:
    """Timestamps and minimal metadata for a single yielded frame."""

    frame_index: int
    t0: float  # perf_counter right before calling next(gen)
    t1: float  # perf_counter right after next(gen) returned
    h0: Optional[float] = None  # header-reported 'ImageGetTimeStart' if present
    h1: Optional[float] = None  # header-reported 'ImageGetTimeEnd' if present


@dataclasses.dataclass
class RoundResult:
    """Results for a single timed round at one exposure and header
    configuration."""

    index: int
    exposure: float
    header_keys: tuple
    header_keys_common: tuple
    frames: list[FrameStamp]
    t_start: float
    t_end: float

    @property
    def n_frames(self) -> int:
        return len(self.frames)

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    @property
    def fps(self) -> float:
        return self.n_frames / self.duration if self.duration > 0 else float('nan')

    def inter_frame_intervals(self) -> list[float]:
        """Return list of intervals between successive t1 frame yield times."""
        return [g.t1 - f.t1 for f, g in pairwise(self.frames)]

    def mean_inter_frame_interval(self) -> Optional[float]:
        ints = self.inter_frame_intervals()
        return mean(ints) if ints else None

    def mean_header_duration(self) -> Optional[float]:
        durations = [f.h1 - f.h0 for f in self.frames if f.h0 and f.h1]
        return mean(durations) if durations else None


class MovieBench:
    """Benchmark runner using a TEMController instance."""

    def __init__(
        self,
        n_rounds: int = 3,
        n_frames: int = 1000,
    ) -> None:
        self.rounds = int(n_rounds)
        self.n_frames = int(n_frames)

        if _ctrl is None:
            raise RuntimeError('No TEMController instance available.')

        if not getattr(_ctrl, 'cam', None):
            raise RuntimeError("Controller has no 'cam' attribute.")
        if not hasattr(_ctrl.cam, 'blocked'):
            raise RuntimeError("Camera does not provide 'blocked()' context manager.")

    def _warm_up(self, exposure: float, header_keys: tuple, header_keys_common: tuple) -> None:
        """Optional tiny dummy call warming camera / generator start-up."""

        try:
            hk, hkc = header_keys, header_keys_common
            gen = _ctrl.get_movie(1, exposure, header_keys=hk, header_keys_common=hkc)
            next(gen)
            gen.close()
        except (StopIteration, RuntimeError):
            pass

    def run_round(
        self,
        exposure: float,
        header_keys: tuple,
        header_keys_common: tuple,
    ) -> RoundResult:
        frames: list[FrameStamp] = []
        hk, hkc = header_keys, header_keys_common
        gen = _ctrl.get_movie(self.n_frames, exposure, header_keys=hk, header_keys_common=hkc)
        t_start = time.perf_counter()
        try:
            for i in range(self.n_frames):
                t0 = time.perf_counter()
                try:
                    img, header = next(gen)
                except StopIteration:
                    break
                t1 = time.perf_counter()
                h0 = header.get('ImageGetTimeStart')
                h1 = header.get('ImageGetTimeEnd')
                frames.append(FrameStamp(frame_index=i + 1, t0=t0, t1=t1, h0=h0, h1=h1))
                # _ = float(np.mean(img))  # if benchmarking later?
        finally:
            try:
                gen.close()
            except Exception:
                pass
        t_end = time.perf_counter()
        return RoundResult(
            exposure=exposure,
            header_keys=header_keys,
            header_keys_common=header_keys_common,
            index=0,
            frames=frames,
            t_start=t_start,
            t_end=t_end,
        )

    def run(
        self,
        exposures: list[float],
        header_keys: tuple = (),
        header_keys_common: tuple = (),
        warmup: bool = True,
    ) -> Generator[RoundResult]:
        """Run benchmark across provided exposure times and header
        configurations."""
        hk, hkc = header_keys, header_keys_common
        for e in exposures:
            for r in range(self.rounds):
                if warmup and r == 0:
                    self._warm_up(exposure=e, header_keys=hk, header_keys_common=hkc)
                with _ctrl.cam.blocked():
                    res = self.run_round(exposure=e, header_keys=hk, header_keys_common=hkc)
                res.index = r + 1
                yield res


# -------------------------
# Reporting utilities
# -------------------------
def summarize_result(result: RoundResult) -> dict:
    """Return a dict with human-friendly summarized numbers for a run."""
    inter_intervals = result.inter_frame_intervals()
    mean_interval = mean(inter_intervals) if inter_intervals else None
    std_interval = stdev(inter_intervals) if len(inter_intervals) >= 2 else None
    header_mean = result.mean_header_duration()
    header_time_ratio = None
    if header_mean is not None and mean_interval is not None:
        header_time_ratio = header_mean / mean_interval if mean_interval > 0 else None

    dead_time_est = (
        (mean_interval - result.exposure) if (mean_interval and result.exposure) else None
    )

    return {
        'exposure_seconds': result.exposure,
        'round_index': result.index,
        'n_frames': result.n_frames,
        'duration_s': result.duration,
        'fps_measured': result.fps,
        'init_time_est_s': (result.frames[0].t1 - result.t_start) if result.frames else None,
        'mean_interframe_s': mean_interval,
        'std_interframe_s': std_interval,
        'min_interframe_s': min(inter_intervals) if inter_intervals else None,
        'max_interframe_s': max(inter_intervals) if inter_intervals else None,
        'dead_time_est_s': dead_time_est,
        'header_mean_s': header_mean,
        'header_time_ratio': header_time_ratio,
    }


def print_run_summary(summ: dict) -> None:
    print(
        f'Exposure {summ["exposure_seconds"]:.6f}s | Round {summ["round_index"]} | frames={summ["n_frames"]} | duration={summ["duration_s"]:.4f}s'
    )
    print(f'  fps={summ["fps_measured"]:.3f} | init_time≈{summ["init_time_est_s"]:.6f}s')
    print(
        f'  interframe mean={summ["mean_interframe_s"]:.6f}s ±{summ["std_interframe_s"] or 0:.6f}s | min={summ["min_interframe_s"]:.6f}s max={summ["max_interframe_s"]:.6f}s'
    )
    if summ['dead_time_est_s'] is not None:
        print(f'  dead_time_est = mean_interframe - exposure = {summ["dead_time_est_s"]:.6f}s')
    if summ['header_mean_s'] is not None:
        print(
            f'  header_mean = {summ["header_mean_s"]:.6f}s | header_time_ratio = {summ["header_time_ratio"]:.3f}'
        )


def print_aggregated_table(results: list[RoundResult]) -> None:
    """Print a CSV-like aggregated summary grouped by exposure."""
    grouped: dict[float, list[RoundResult]] = {}
    for r in results:
        grouped.setdefault(r.exposure, []).append(r)

    header = [
        'exposure_s',
        'rounds',
        'frames_avg',
        'fps_mean',
        'fps_std',
        'dead_time_mean_s',
        'header_mean_s',
        'header_time_ratio',
    ]
    print('\nAggregated summary (CSV):')
    print(','.join(header))

    for exposure in sorted(grouped.keys()):
        runs = grouped[exposure]
        fps_vals = [rr.fps for rr in runs if not math.isnan(rr.fps)]
        frames_avg = mean([rr.n_frames for rr in runs]) if runs else 0
        fps_mean = mean(fps_vals) if fps_vals else float('nan')
        fps_std = stdev(fps_vals) if len(fps_vals) >= 2 else 0.0

        dead_times = []
        header_means = []
        for rr in runs:
            mi = rr.mean_inter_frame_interval()
            if mi is not None:
                dead_times.append(mi - rr.exposure)
            hm = rr.mean_header_duration()
            if hm is not None:
                header_means.append(hm)

        dead_mean = mean(dead_times) if dead_times else float('nan')
        header_mean = mean(header_means) if header_means else float('nan')
        header_ratio = (
            (header_mean / (dead_mean + exposure))
            if (not math.isnan(header_mean) and not math.isnan(dead_mean))
            else float('nan')
        )

        row = [
            exposure,
            len(runs),
            frames_avg,
            fps_mean,
            fps_std,
            dead_mean,
            header_mean,
            header_ratio,
        ]
        print(','.join([f'{v:.6g}' if isinstance(v, float) else str(v) for v in row]))


def save_raw_csv(results: list[RoundResult]) -> None:
    filename = Path.cwd() / f'benchmark_movie_raw_{int(time.time())}.csv'
    with filename.open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['exposure_s', 'round', 'frame_index', 't0', 't1', 'h0', 'h1'])
        for r in results:
            for f in r.frames:
                writer.writerow([r.exposure, r.index, f.frame_index, f.t0, f.t1, f.h0, f.h1])
    print(f'Raw timestamps saved to: {filename}')


# -------------------------
# CLI helpers
# -------------------------
def parse_exposures(arg: Optional[str]) -> list[float]:
    """Parse comma-separated exposures or default to 1/10..1/100 s."""
    if not arg:
        defaults_fps = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        return [1.0 / f for f in defaults_fps]
    parts = [p.strip() for p in arg.split(',') if p.strip()]
    exposures: list[float] = []
    for p in parts:
        try:
            exposures.append(float(p))
        except Exception:
            raise argparse.ArgumentTypeError(f'Invalid exposure value: {p}')
    return exposures


def parse_header_keys(arg: Optional[str]) -> tuple:
    if (arg is None) or (arg == ''):
        return ()
    return tuple(x.strip() for x in arg.split(',') if x.strip())


def generate_plots(results: list[RoundResult]) -> None:
    """Generate basic plots: exposure vs fps, exposure vs dead-time."""

    # Aggregate by exposure
    grouped: dict[float, list[RoundResult]] = {}
    for r in results:
        grouped.setdefault(r.exposure, []).append(r)

    exposures = sorted(grouped.keys())
    fps_means = []
    dead_time_means = []

    for exp in exposures:
        runs = grouped[exp]
        # fps mean
        fps_vals = [rr.fps for rr in runs if not math.isnan(rr.fps)]
        fps_means.append(mean(fps_vals) if fps_vals else float('nan'))
        dead_times = []
        for rr in runs:
            mi = rr.mean_inter_frame_interval()
            if mi is not None:
                dead_times.append(mi - rr.exposure)
        dead_time_means.append(mean(dead_times) if dead_times else float('nan'))

    # ---- PLOT 1: Exposure vs FPS ----
    plt.figure()
    plt.plot(exposures, fps_means, marker='o')
    plt.xlabel('Exposure (s)')
    plt.ylabel('FPS (measured)')
    plt.title('Exposure vs Measured FPS')
    plt.grid(True)
    plt.show()

    # ---- PLOT 2: Exposure vs Dead Time ----
    plt.figure()
    plt.plot(exposures, dead_time_means, marker='o')
    plt.xlabel('Exposure (s)')
    plt.ylabel('Dead time (s)')
    plt.title('Exposure vs Dead Time')
    plt.grid(True)
    plt.show()


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description='Benchmark TEMController.get_movie to measure achievable frame rates.'
    )
    parser.add_argument(
        '--exposures',
        type=str,
        default=None,
        help="Comma-separated exposures in seconds, e.g. '0.01,0.02'. Default: 1/10..1/100.",
    )
    parser.add_argument(
        '--variable-headers',
        type=str,
        default=None,
        help='Comma-separated variable header keys to collect per frame. Use empty string to disable.',
    )
    parser.add_argument(
        '--common-headers',
        type=str,
        default=None,
        help='Comma-separated common header keys to collect once before movie. Use empty string to disable.',
    )
    parser.add_argument(
        '--n_rounds', type=int, default=3, help='Rounds per exposure. Default: 3'
    )
    parser.add_argument(
        '--n_frames', type=int, default=10, help='Number of frames to be collected. Default: 10'
    )
    parser.add_argument('--no-warmup', action='store_true', help='Disable warmup dummy frame.')
    parser.add_argument(
        '--plot',
        action='store_true',
        help='Generate simple matplotlib plots after the benchmark.',
    )
    args = parser.parse_args(argv)

    exposures = parse_exposures(args.exposures)
    variable_headers = parse_header_keys(args.variable_headers)
    common_headers = parse_header_keys(args.common_headers)

    bench = MovieBench(
        n_rounds=args.n_rounds,
        n_frames=args.n_frames,
    )

    print('=== benchmark_movie_rates: starting benchmark ===')
    print(f'Exposures (s): {exposures}')
    print(f'Variable header keys: {variable_headers or "(none)"}')
    print(f'Common header keys: {common_headers or "(none)"}')
    print(f'Rounds per exposure: {args.n_rounds}')

    results: list[RoundResult] = []
    results_generator = bench.run(
        exposures=exposures,
        header_keys=variable_headers,
        header_keys_common=common_headers,
        warmup=(not args.no_warmup),
    )

    # Print per-run summaries
    for res in results_generator:
        summ = summarize_result(res)
        print()
        print_run_summary(summ)
        results.append(res)
    print_aggregated_table(results)
    try:
        save_raw_csv(results)
    except PermissionError:
        pass
    generate_plots(results)

    print('\n=== benchmark_movie_rates: finished ===')


if __name__ == '__main__':
    main()
