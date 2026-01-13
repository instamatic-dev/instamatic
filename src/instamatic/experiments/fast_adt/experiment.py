from __future__ import annotations

import logging
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from math import ceil
from pathlib import Path
from queue import Queue
from threading import Thread
from tkinter import StringVar
from typing import Any, Iterator, Optional, Sequence, Union, cast

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from PIL.Image import Image
from typing_extensions import Self

from instamatic import config
from instamatic._collections import NullLogger
from instamatic._typing import AnyPath
from instamatic.calibrate import CalibBeamShift, CalibMovieDelays, CalibStageRotation
from instamatic.calibrate.filenames import CALIB_BEAMSHIFT
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.gui.click_dispatcher import MouseButton
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion
from instamatic.utils.iterating import sawtooth


def get_color(i: int) -> tuple[int, int, int]:
    """Return i-th color from matplotlib colormap tab10 as accepted by PIL."""
    return tuple([int(rgb * 255) for rgb in plt.get_cmap('tab10')(i % 10)][:3])  # type: ignore


def safe_range(start: float, stop: float, step: float) -> np.ndarray:
    """Find 2+ floats between `start` and `stop` (inclusive) ~`step` apart."""
    step_count = max(ceil(abs((stop - start) / step)) + 1, 2)
    return np.linspace(start, stop, step_count, endpoint=True, dtype=float)


class FastADTEarlyTermination(RuntimeError):
    """Raised if FastADT experiment terminates early due to known reasons."""


class FastADTMissingCalibError(RuntimeError):
    """Raised if some calibration is strictly required but missing."""


@dataclass
class Step:
    """A dataclass representing a single step in the experimental `Run`."""

    Index: int
    alpha: float
    beampixel_x: Optional[float] = None
    beampixel_y: Optional[float] = None
    beamshift_x: Optional[float] = None
    beamshift_y: Optional[float] = None
    image: Optional[np.ndarray] = None
    meta: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return f'Step(Index={self.Index}, alpha={self.alpha})'


class Run:
    """Collection of details of a generalized single FastADT run.

    Attributes
    ----------
    exposure: float
        Time spent collecting each frame, expressed in seconds
    continuous: bool
        Whether the run involves continuous scan (True) or single frames (False)
    table: pd.DataFrame
        Describes details of individual steps (to be) measured:
            - alpha - average value of the rotation axes for given frame
            - beampixel_x/y - beam x/y position in pixel used for tracking
            - beamshift_x/y - beam deflector x/y value used for tracking
            - image, meta - tracking or diffraction image and its header data
    """

    def __init__(self, exposure=1.0, continuous=False, **columns: Sequence) -> None:
        self.exposure: float = exposure
        self.continuous: bool = continuous
        self.table: pd.DataFrame = pd.DataFrame.from_dict(columns)

    def __str__(self) -> str:
        c = self.__class__.__name__
        a = self.table['alpha'].values
        ar = f'range({a[0]:.3g}, {a[-1]:.3g}, {float(np.mean(np.diff(a))):.3g})'
        return f'{c}(exposure={self.exposure:.3g}, continuous={self.continuous}, alpha={ar})'

    def __len__(self) -> int:
        return len(self.table)

    @property
    def steps(self) -> Iterator[Step]:
        """Iterate over individual run `Step`s holding rows of `self.table`."""
        return (Step(**t._asdict()) for t in self.table.itertuples())  # noqa

    def interpolate(self, key: str, at: np.array) -> np.ndarray:
        """Interpolate values of `table[key]` at some denser grid of points."""
        alpha, values = self.table['alpha'], self.table[key]
        if at[0] > at[-1]:  # decreasing order is not handled by numpy.interp
            return np.interp(at[::-1], alpha[::-1], values[::-1])[::-1]
        return np.interp(at, alpha, values)

    @property
    def buffer(self) -> list[tuple[int, np.ndarray, dict]]:
        """Standardized list of (number, image, meta) used when saving."""
        return [(i, s.image, s.meta) for i, s in enumerate(self.steps)]

    @property
    def has_beamshifts(self) -> bool:
        return {'beamshift_x', 'beamshift_y'}.issubset(self.table.columns)

    @property
    def osc_angle(self) -> float:
        """Difference of alpha angle between two consecutive frames."""
        a = self.table['alpha'].values
        return (a[-1] - a[0]) / (len(a) - 1) if len(a) > 1 else 0

    def collapse_to_alpha_midpoints(self) -> None:
        """Set current alpha midpoints as new alpha, dropping the first row."""
        alpha_midpoints = self.table['alpha'].rolling(2).mean().drop(0)
        self.table = self.table.iloc[1:]
        self.table['alpha'] = alpha_midpoints

    def update_images_metas(self, steps: Queue[Union[Step, None]]) -> None:
        """Consume Steps from queue until None, update self.images & .meta."""
        step_list: list[Step] = []
        while True:
            step = steps.get()
            if step is None:
                break
            step_list.append(step)
        self.table['image'] = [s.image for s in step_list]
        self.table['meta'] = [s.meta for s in step_list]


class TrackingRun(Run):
    """Designed to estimate beampixel_x/y a priori based on manual input."""

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> Self:
        a = safe_range(p['diffraction_start'], p['diffraction_stop'], p['tracking_step'])
        return cls(exposure=p['tracking_time'], continuous=False, alpha=a)


class DiffractionRun(Run):
    """The implementation for the actual diffraction experiment itself."""

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> Self:
        c = p['diffraction_mode'] == 'continuous'
        a = safe_range(p['diffraction_start'], p['diffraction_stop'], p['diffraction_step'])
        return cls(exposure=p['diffraction_time'], continuous=c, alpha=a)

    def add_beamshifts(self, pathing_run: TrackingRun) -> None:
        """Add and interpolate delta x/y info from another run instance."""
        a = self.table['alpha'].values
        self.table['beamshift_x'] = pathing_run.interpolate('beamshift_x', at=a)
        self.table['beamshift_y'] = pathing_run.interpolate('beamshift_y', at=a)


@dataclass
class Runs:
    """Collection of runs for xtal tracking, beam pathing, diff collection."""

    tracking: Optional[Run] = None
    pathing: list[TrackingRun] = field(default_factory=list)
    diffraction: list[DiffractionRun] = field(default_factory=list)


class Experiment(ExperimentBase):
    """Initialize a FastADT-style rotation electron diffraction experiment.

    Parameters
    ----------
    ctrl:
        Instance of instamatic.controller.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Optional instance of `logging.Logger`
    flatfield:
        Optional path to flatfield correction image
    experiment_frame:
        Optional instance of `ExperimentalFastADT` used to display messages
    videostream_frame:
        Optional instance of `VideoStreamFrame` to display tracking and images
    """

    name = 'FastADT'

    def __init__(
        self,
        ctrl,
        path: Optional[AnyPath] = None,
        log: Optional[logging.Logger] = None,
        flatfield: Optional[AnyPath] = None,
        experiment_frame: Optional[Any] = None,
        videostream_frame: Optional[Any] = None,
    ):
        super().__init__()
        self.ctrl = ctrl
        self.path = Path(path)
        self.log = log or NullLogger()
        self.flatfield = flatfield
        self.fast_adt_frame = experiment_frame
        self.beamshift: Optional[CalibBeamShift] = None
        self.binsize: int = 1
        self.camera_length: int = 0

        if videostream_frame is not None:
            d = videostream_frame.click_dispatcher
            n = self.name
            self.click_listener = c if (c := d.listeners.get(n)) else d.add_listener(n)
            self.videostream_processor = videostream_frame.processor
        else:  # needed only for manual tracking
            self.click_listener = None
            self.videostream_processor = None

        self.steps: Queue[Union[Step, None]] = Queue()
        self.runs: Runs = Runs()

    def restore_fast_adt_diff_for_image(self):
        """Restore 'FastADT_diff' config with 'FastADT_track' magnification."""
        self.ctrl.restore('FastADT_track')
        tracking_mode = self.ctrl.mode.get()
        tracking_magnification = self.ctrl.magnification.value
        self.ctrl.restore('FastADT_diff')
        self.ctrl.mode.set(tracking_mode)
        self.ctrl.magnification.value = tracking_magnification

    def get_beamshift(self) -> CalibBeamShift:
        """Must follow `self.restore_fast_adt_diff_for_image()` to see beam."""
        calib_dir = self.path.parent / 'calib'
        try:
            return CalibBeamShift.from_file(calib_dir / CALIB_BEAMSHIFT)
        except OSError:
            self.msg1('Focus and center the beam, and check terminal for instructions.')
            vsp = self.videostream_processor
            return CalibBeamShift.live(self.ctrl, outdir=calib_dir, vsp=vsp)

    def get_dead_time(
        self,
        exposure: float = 0.0,
        header_keys_variable: tuple = (),
        header_keys_common: tuple = (),
    ) -> float:
        """Get time between get_movie frames from any source available or 0."""
        try:
            return self.ctrl.cam.dead_time
        except AttributeError:
            pass
        self.msg2('`cam.dead_time` not found. Looking for calibrated estimate...')
        try:
            c = CalibMovieDelays.from_file(exposure, header_keys_variable, header_keys_common)
        except RuntimeWarning:
            return 0.0
        else:
            return c.dead_time
        finally:
            self.msg2('')

    def get_stage_rotation(self) -> CalibStageRotation:
        """Get rotation calibration if present; otherwise warn & terminate."""
        try:
            return CalibStageRotation.from_file()
        except OSError:
            self.msg1(m1 := 'This script requires stage rotation to be calibrated.')
            self.msg2(m2 := 'Please run `instamatic.calibrate_stage_rotation` first.')
            raise FastADTMissingCalibError(m1 + ' ' + m2)

    def determine_rotation_speed_and_exposure(self, run: Run) -> tuple[float, float]:
        """Closest possible speed setting & exposure considering dead time."""
        detector_dead_time = self.get_dead_time(run.exposure)
        time_for_one_frame = run.exposure + detector_dead_time
        rot_calib = self.get_stage_rotation()
        rot_plan = rot_calib.plan_motion(time_for_one_frame / run.osc_angle)
        exposure = abs(rot_plan.pace * run.osc_angle) - detector_dead_time
        return rot_plan.speed, exposure

    def _message(self, text: str, var: Optional[StringVar]) -> None:
        """Display text in log.info, consoles, FastADT frame msg area 1/2."""
        try:
            var.set(text)
        except AttributeError:
            pass
        if text:
            print(text)
            self.log.info(text)

    def msg1(self, text: str) -> None:
        """Display in message area 1 with persistent status & instructions."""
        var = self.fast_adt_frame.message1 if self.fast_adt_frame else None
        return self._message(text, var=var)

    def msg2(self, text: str) -> None:
        """Display in message area 2 with the most recent tem/cam updates."""
        var = self.fast_adt_frame.message2 if self.fast_adt_frame else None
        return self._message(text, var=var)

    def start_collection(self, **params) -> None:
        """Collect FastADT experiment according to provided **params.

        The FastADT experiment can behave quite differently depending on the
        input parameters provided. For a full list of parameters, see
        `instamatic/gui/fast_adt_frame.py:ExperimentalFastADTVariables`.
        The following code is divided into four sections, each responsible
        for a different part of the experiment.

        At the beginning, FastADT will blank the beam to minimize sample damage.
        The beam will be un-blanked only when strictly needed, e.g. at the start
        when collecting a direct-space preview image of the measured crystal.

        In the second part, if any kind of tracking was requested, a tracking
        `Run`-object will be created and collected.

        After the image and tracking are collected, FastADT will prepare for
        and collect the actual diffraction run. Depending on the experiment mode
        requested, it might consist of several stills or a continuous movie.

        Finally, the collected run will be logged and the stage - reset.
        """
        self.msg1('Collecting crystal image.')
        self.msg2('')
        image_path = self.path / 'image.tiff'
        if not image_path.exists():
            self.ctrl.restore('FastADT_image')
            with self.ctrl.beam.unblanked(delay=0.2):
                self.ctrl.get_image(params['tracking_time'], out=image_path)

        with self.ctrl.beam.blanked(), self.ctrl.cam.blocked():
            if params['tracking_algo'] == 'manual':
                self.binsize = self.ctrl.cam.default_binsize
                self.runs.tracking = TrackingRun.from_params(params)
                self.determine_pathing_manually()
            for pathing_run in self.runs.pathing:
                new_run = DiffractionRun.from_params(params)
                new_run.add_beamshifts(pathing_run)
                self.runs.diffraction.append(new_run)
            if not self.runs.pathing:
                self.runs.diffraction = [DiffractionRun.from_params(params)]

            self.ctrl.restore('FastADT_diff')
            self.camera_length = int(self.ctrl.magnification.get())
            n_runs = len(self.runs.diffraction)
            for ir, run in enumerate(self.runs.diffraction):
                suffix = f' ({ir + 1}/{n_runs})' if n_runs > 1 else ''
                self.msg1(f'Collecting {run!s}.{suffix}')
                self.collect_run(run)
                self.msg1(f'Finalizing {run!s}.{suffix}')
                run.update_images_metas(self.steps)
                self.finalize(run)

            self.ctrl.restore('FastADT_image')
            self.ctrl.stage.a = 0.0

    @contextmanager
    def displayed_pathing(self, step: Step) -> None:
        """Display step image with dots representing existing pathing."""
        draw = self.videostream_processor.draw
        instructions: list[draw.Instruction] = []
        for run_i, p in enumerate(self.runs.pathing):
            x = p.table.at[step.Index, 'beampixel_x'] / self.binsize
            y = p.table.at[step.Index, 'beampixel_y'] / self.binsize
            instructions.append(draw.circle((x, y), fill='white', radius=5))
            instructions.append(draw.circle((x, y), fill=get_color(run_i), radius=3))
        try:
            with self.videostream_processor.temporary(frame=step.image):
                yield
        finally:
            for instruction in instructions:
                draw.instructions.remove(instruction)

    def determine_pathing_manually(self) -> None:
        """Determine the target beam shifts `delta_x` and `delta_y` manually,
        based on the beam center found life (to find clicking offset) and
        `TrackingRun` to be used for crystal tracking in later experiment."""
        run: TrackingRun = cast(TrackingRun, self.runs.tracking)
        self.restore_fast_adt_diff_for_image()
        self.ctrl.stage.a = run.table.loc[len(run) // 2, 'alpha']
        with self.ctrl.beam.unblanked(), self.ctrl.cam.unblocked():
            self.beamshift = self.get_beamshift()
            self.msg1('Locate the beam (move it if needed) and click on its center.')
            with self.click_listener as cl:
                obs_beampixel_xy = np.array(cl.get_click().xy) * self.binsize
        cal_beampixel_yx = self.beamshift.beamshift_to_pixelcoord(self.ctrl.beamshift.get())

        self.ctrl.restore('FastADT_track')
        Thread(target=self.collect_run, args=(run,), daemon=True).start()
        tracking_frames = deque(maxlen=len(run))
        tracking_images: list[Optional[Image]] = [None] * len(run)
        tracking_in_progress = True
        while tracking_in_progress:
            while (step := self.steps.get()) is not None:
                self.msg1(f'Click on tracked point: {step.summary}.')
                with self.displayed_pathing(step=step), self.click_listener:
                    click = self.click_listener.get_click()
                click_xy = np.array(click.xy) * self.binsize
                delta_yx = (click_xy - obs_beampixel_xy)[::-1]
                click_beampixel_yx = cast(Sequence[float], cal_beampixel_yx + delta_yx)
                click_beamshift_xy = self.beamshift.pixelcoord_to_beamshift(click_beampixel_yx)
                cols = ['beampixel_x', 'beampixel_y', 'beamshift_x', 'beamshift_y']
                run.table.loc[step.Index, cols] = *click_xy, *click_beamshift_xy
                tracking_frames.append(step.image)
            if 'image' not in run.table:
                run.table['image'] = tracking_frames
            self.runs.pathing.append(deepcopy(run))

            self.msg1('Displaying tracking. Click LEFT mouse button to start the experiment,')
            self.msg2('MIDDLE to track another point, or RIGHT to cancel the experiment.')
            for step in sawtooth(self.runs.tracking.steps):
                with self.displayed_pathing(step=step):
                    image = self.videostream_processor.image
                    image.info['_annotated_runs'] = len(self.runs.pathing)
                    tracking_images[step.Index] = image
                    with self.click_listener:
                        click = self.click_listener.get_click(timeout=0.5)
                    if click is None:
                        continue
                    self.msg2('')
                    if click.button == MouseButton.RIGHT:
                        self.msg1(msg := 'Experiment abandoned after tracking.')
                        raise FastADTEarlyTermination(msg)
                    if click.button == MouseButton.LEFT:
                        tracking_in_progress = False
                    else:  # any other mouse button was clicked
                        for new_step in [*self.runs.tracking.steps, None]:
                            self.steps.put(new_step)
                    break

        drc = self.path / 'tracking'
        drc.mkdir(parents=True, exist_ok=True)
        with self.ctrl.cam.blocked():
            for step, image in zip(run.steps, tracking_images):
                i = f'image{step.Index:02d}_al{step.alpha:+03.0f}.png'.replace('+', '0')
                if image is None or image.info['_annotated_runs'] < len(self.runs.pathing):
                    with self.displayed_pathing(step=step):
                        image = self.videostream_processor.image
                self.videostream_processor.vsf.save_image(image=image, path=drc / i)

    def collect_run(self, run: Run) -> None:
        """Collect `run.steps` and place them in `self.steps` Queue."""
        with self.ctrl.beam.unblanked(delay=0.2):
            if run.continuous:
                self._collect_scans(run=run)
            else:
                self._collect_stills(run=run)

    def _collect_scans(self, run: Run) -> None:
        """Collect `run.steps` scans and place them in `self.steps` Queue."""
        rot_speed, run.exposure = self.determine_rotation_speed_and_exposure(run)
        self.ctrl.stage.a = float(run.table.at[0, 'alpha'])
        movie = self.ctrl.get_movie(n_frames=len(run) - 1, exposure=run.exposure)
        target_alpha = float(run.table.iloc[-1].loc['alpha'])
        run.collapse_to_alpha_midpoints()
        with self.ctrl.stage.rotation_speed(speed=rot_speed):
            self.ctrl.stage.set(a=target_alpha, wait=False)
            for step, (image, meta) in zip(run.steps, movie):
                self.msg2(f'Collecting {step.summary}.')
                if run.has_beamshifts:
                    self.ctrl.beamshift.set(step.beamshift_x, step.beamshift_y)
                self.steps.put(replace(step, image=image, meta=meta))
        self.steps.put(None)
        self.msg2('')

    def _collect_stills(self, run: Run) -> None:
        """Collect `run.steps` stills and place them in `self.steps` Queue."""
        for step in run.steps:
            self.msg2(f'Collecting {step.summary}.')
            if run.has_beamshifts:
                self.ctrl.beamshift.set(step.beamshift_x, step.beamshift_y)
            self.ctrl.stage.a = step.alpha
            image, meta = self.ctrl.get_image(exposure=run.exposure)
            self.steps.put(replace(step, image=image, meta=meta))
        self.steps.put(None)
        self.msg2('')

    def get_run_output_path(self, run: DiffractionRun) -> Path:
        """Return self.path if only 1 run done, self.path/sub## if multiple."""
        if len(self.runs.pathing) <= 1:
            return self.path
        return self.path / f'sub{self.runs.diffraction.index(run):02d}'

    def finalize(self, run: DiffractionRun) -> None:
        """Create output directories and save provided run there."""
        out_path = self.get_run_output_path(run)
        mrc_path = out_path / 'mrc'
        tiff_path = out_path / 'tiff'
        mrc_path.mkdir(exist_ok=True, parents=True)
        tiff_path.mkdir(exist_ok=True, parents=True)

        self.msg1(f'Saving experiment in "{out_path}"...')
        rotation_axis = config.camera.camera_rotation_vs_stage_xy
        pixel_size = config.calibration['diff']['pixelsize'].get(self.camera_length, -1)
        physical_pixel_size = config.camera.physical_pixelsize  # mm
        wavelength = config.microscope.wavelength  # angstrom
        stretch_azimuth = config.camera.stretch_azimuth
        stretch_amplitude = config.camera.stretch_amplitude
        m = 'Continuous-Rotation 3D ED' if run.continuous else 'Rotation Electron Diffraction'

        img_conv = ImgConversion(
            buffer=run.buffer,
            osc_angle=abs(run.osc_angle),
            start_angle=run.table['alpha'].iloc[0],
            end_angle=run.table['alpha'].iloc[-1],
            rotation_axis=rotation_axis,
            acquisition_time=run.exposure,
            flatfield=self.flatfield,
            pixelsize=pixel_size,
            physical_pixelsize=physical_pixel_size,
            wavelength=wavelength,
            stretch_amplitude=stretch_amplitude,
            stretch_azimuth=stretch_azimuth,
            method=m,
        )

        img_conv.threadpoolwriter(tiff_path=tiff_path, mrc_path=mrc_path, workers=8)
        img_conv.write_ed3d(mrc_path)
        img_conv.write_pets_inp(out_path)
        img_conv.write_beam_centers(out_path)
        self.msg1(f'Experiment saved in "{out_path}".')
