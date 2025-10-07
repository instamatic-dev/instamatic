from __future__ import annotations

import contextlib
import itertools
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Iterable, Iterator, Optional, Sequence, TypeVar, Union

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from typing_extensions import Self

from instamatic import config
from instamatic._collections import NullLogger
from instamatic._typing import AnyPath
from instamatic.calibrate import CalibBeamShift, CalibMovieDelays, CalibStageRotation
from instamatic.calibrate.filenames import CALIB_BEAMSHIFT
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.gui.click_dispatcher import MouseButton
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion

T = TypeVar('T')


def get_color(i: int) -> tuple[int, int, int]:
    """Return i-th color from matplotlib colormap tab10 as accepted by PIL."""
    return tuple([int(rgb * 255) for rgb in plt.get_cmap('tab10')(i)][:3])  # type: ignore


def safe_range(*, start: float, stop: float, step: float) -> np.ndarray:
    """Find 2+ floats between `start` and `stop` (inclusive) ~`step` apart."""
    step_count = max(round(abs(stop - start) / step) + 1, 2)
    return np.linspace(start, stop, step_count, endpoint=True, dtype=float)


def sawtooth(iterator: Iterable[T]) -> Iterator[T]:
    """Iterate elements of input sequence back and forth, repeating edges."""
    yield from itertools.cycle((seq := list(iterator)) + list(reversed(seq)))


class FastADTEarlyTermination(RuntimeError):
    """Raised if FastADT experiment terminates early due to known reasons."""


class FastADTMissingCalibError(RuntimeError):
    """Raised if some calibration is strictly required but missing."""


@dataclass
class Step:
    """A dataclass representing a single step in the experimental `Run`."""

    Index: int
    alpha: float
    beamshift_x: Optional[float] = None
    beamshift_y: Optional[float] = None
    delta_x: Optional[float] = None
    delta_y: Optional[float] = None
    image: Optional[np.ndarray] = None
    meta: dict = field(default_factory=dict)


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
            - delta_x - x beam shift relative from center needed to track the crystal
            - delta_y - y beam shift relative from center needed to track the crystal
    """

    def __init__(self, exposure=1.0, continuous=False, **columns: Sequence) -> None:
        self.exposure: float = exposure
        self.continuous: bool = continuous
        self.table: pd.DataFrame = pd.DataFrame.from_dict(columns)

    @property
    def scope(self) -> tuple[float, float]:
        """The range of alpha values scanned during the entire run."""
        a = self.table['alpha']
        if not self.continuous:
            return a.iloc[0], a.iloc[-1]
        return a.iloc[0] - self.osc_angle / 2, a.iloc[-1] + self.osc_angle / 2

    @property
    def steps(self) -> Iterator[Step]:
        """Iterate over individual run `Step`s holding rows of `self.table`."""
        return (Step(**t._asdict()) for t in self.table.itertuples())  # noqa

    def interpolate(self, at: np.array, key: str) -> np.ndarray:
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
    def has_beam_delta_information(self) -> bool:
        return {'delta_x', 'delta_y'}.issubset(self.table.columns)

    @property
    def osc_angle(self) -> float:
        """Difference of alpha angle between two consecutive frames."""
        a = list(self.table['alpha'])
        return (a[-1] - a[0]) / (len(a) - 1) if len(a) > 1 else -1

    def make_continuous(self) -> None:
        """Make self a new run from N-1 first rows for the continuous
        method."""
        new_al = self.table['alpha'].rolling(2).mean().drop(0)
        new_kw = self.table.iloc[:-1, :].to_dict(orient='list')
        del new_kw['alpha']
        self.__init__(exposure=self.exposure, continuous=True, alpha=new_al, **new_kw)

    def calculate_beamshifts(self, ctrl, beamshift) -> None:
        """Note CalibBeamShift uses swapped axes: X points down, Y right."""
        beamshift_xy = ctrl.beamshift.get()
        pixelcoord_xy = beamshift.beamshift_to_pixelcoord(beamshift_xy)
        delta_xys = self.table[['delta_x', 'delta_y']].to_numpy()
        crystal_xys = pixelcoord_xy + delta_xys
        crystal_yxs = np.fliplr(crystal_xys)
        beamshifts = beamshift.pixelcoord_to_beamshift(crystal_yxs)
        self.table[['beamshift_x', 'beamshift_y']] = beamshifts


class TrackingRun(Run):
    """Designed to estimate delta_x/y a priori based on manual used input."""

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> Self:
        alpha_range = safe_range(
            start=params['diffraction_start'],
            stop=params['diffraction_stop'],
            step=params['tracking_step'],
        )
        return cls(exposure=params['tracking_time'], alpha=alpha_range)


class DiffractionRun(Run):
    """The implementation for the actual diffraction experiment itself."""

    @classmethod
    def from_params(
        cls,
        params: dict[str, Any],
        pathing_run: Optional['TrackingRun'] = None,
    ) -> Self:
        alpha_range = safe_range(
            start=params['diffraction_start'],
            stop=params['diffraction_stop'],
            step=params['diffraction_step'],
        )
        run = cls(exposure=params['diffraction_time'], alpha=alpha_range)
        if pathing_run is not None:
            run.table['delta_x'] = pathing_run.interpolate(alpha_range, 'delta_x')
            run.table['delta_y'] = pathing_run.interpolate(alpha_range, 'delta_y')
        return run


@dataclass
class Runs:
    """Collection of runs: beam alignment, xtal tracking, beam pathing, diff"""

    alignment: Optional[Run] = None
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
        Optional instance of `VideoStreamFrame` used to display messages
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
        self.camera_length: int = 0
        self.diffraction_mode: str = ''

        if videostream_frame is not None:
            d = videostream_frame.click_dispatcher
            n = self.name
            self.click_listener = c if (c := d.listeners.get(n)) else d.add_listener(n)
            self.videostream_processor = videostream_frame.processor
        else:  # needed only for manual tracking
            self.click_listener = None
            self.videostream_processor = None

        self.beam_center: tuple[float, float] = (float('nan'), float('nan'))
        self.steps_queue: Queue[Union[Step, None]] = Queue()
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
            return CalibBeamShift.live(
                self.ctrl, outdir=calib_dir, vsp=self.videostream_processor
            )

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
        self.msg('`cam.dead_time` not found. Looking for calibrated estimate...')
        try:
            c = CalibMovieDelays.from_file(exposure, header_keys_variable, header_keys_common)
        except RuntimeWarning:
            return 0.0
        else:
            return c.dead_time

    def get_stage_rotation(self) -> CalibStageRotation:
        """Get rotation calibration if present; otherwise warn & terminate."""
        try:
            return CalibStageRotation.from_file()
        except OSError:
            msg = (
                'Collecting cRED with this script requires calibrated stage rotation. '
                'Please run `instamatic.calibrate_stage_rotation` first.'
            )
            self.msg(msg)
            raise FastADTMissingCalibError(msg)

    def msg(self, text: str) -> None:
        """Display a message in log.info, consoles & FastADT frame at once."""
        try:
            self.fast_adt_frame.message.set(text)
        except AttributeError:
            pass
        print(text)
        if text:
            self.log.info(text)

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
        self.msg('FastADT experiment started')

        image_path = self.path / 'image.tiff'
        if not image_path.exists():
            self.ctrl.restore('FastADT_image')
            with self.ctrl.beam.unblanked(delay=0.2):
                self.ctrl.get_image(params['tracking_time'], out=image_path)

        with self.ctrl.beam.blanked(), self.ctrl.cam.blocked():
            if params['tracking_mode'] == 'manual':
                self.runs.tracking = TrackingRun.from_params(params)
                self.determine_pathing_manually()

            for pathing_run in self.runs.pathing:
                new_run = DiffractionRun.from_params(params, pathing_run)
                self.runs.diffraction.append(new_run)
            if not self.runs.pathing:
                self.runs.diffraction = [DiffractionRun.from_params(params)]

            self.ctrl.restore('FastADT_diff')
            self.camera_length = int(self.ctrl.magnification.get())
            self.diffraction_mode = params['diffraction_mode']

            for run in self.runs.diffraction:
                if self.diffraction_mode == 'stills':
                    self.collect_stills(run)
                elif self.diffraction_mode == 'continuous':
                    self.collect_continuous(run)
                self.finalize(run)

            self.ctrl.restore('FastADT_image')
            self.ctrl.stage.a = 0.0

    @contextlib.contextmanager
    def displayed_step(self, step: Step) -> None:
        """Display step image with dots representing existing pathing."""
        draw = self.videostream_processor.draw
        instructions: list[draw.Instruction] = []
        for run_i, p in enumerate(self.runs.pathing):
            x = self.beam_center[0] + p.table.at[step.Index, 'delta_x']
            y = self.beam_center[1] + p.table.at[step.Index, 'delta_y']
            instructions.append(draw.circle((x, y), fill='white', radius=3))
            instructions.append(draw.circle((x, y), fill=get_color(run_i), radius=2))
        with self.videostream_processor.temporary(frame=step.image):
            yield
        for instruction in instructions:
            draw.instructions.remove(instruction)

    def determine_pathing_manually(self) -> None:
        """Determine the target beam shifts `delta_x` and `delta_y` manually,
        based on the beam center found life (to find clicking offset) and
        `TrackingRun` to be used for crystal tracking in later experiment."""

        run: TrackingRun = self.runs.tracking
        self.restore_fast_adt_diff_for_image()
        self.beamshift = self.get_beamshift()
        self.ctrl.stage.a = run.table.loc[len(run.table) // 2, 'alpha']
        with self.ctrl.beam.unblanked(), self.ctrl.cam.unblocked():
            self.msg('Collecting tracking. Click on the center of the beam.')
            with self.click_listener as cl:
                self.beam_center = cl.get_click().xy

        self.ctrl.restore('FastADT_track')
        Thread(target=self.collect_tracking_stills, args=(run,), daemon=True).start()

        tracking_images = []
        tracking_in_progress = True
        while tracking_in_progress:
            print('Starting tracking again?')
            while (step := self.steps_queue.get()) is not None:
                m = f'Click on the crystal (image={step.Index}, alpha={step.alpha} deg).'
                self.msg(m)
                with self.displayed_step(step=step), self.click_listener:
                    click = self.click_listener.get_click()
                run.table.loc[step.Index, 'delta_x'] = click.x - self.beam_center[0]
                run.table.loc[step.Index, 'delta_y'] = click.y - self.beam_center[1]
                tracking_images.append(step.image)
                self.msg('')
            if 'image' not in run.table:
                run.table['image'] = tracking_images
            self.runs.pathing.append(deepcopy(run))

            self.msg('Tracking results: click LMB to accept, MMB to add new, RMB to reject.')
            for step in sawtooth(self.runs.tracking.steps):
                with self.displayed_step(step=step), self.click_listener:
                    click = self.click_listener.get_click(timeout=0.5)
                    if click is None:
                        continue
                    if click.button == MouseButton.RIGHT:
                        msg = 'Experiment abandoned after tracking.'
                        self.msg(msg)
                        raise FastADTEarlyTermination(msg)
                    if click.button == MouseButton.LEFT:
                        tracking_in_progress = False
                    else:  # any other mouse button was clicked
                        for new_step in [*self.runs.tracking.steps, None]:
                            self.steps_queue.put(new_step)
                    break

    def collect_stills(self, run: Run) -> None:
        """Collect a series of stills at angles/exposure specified in `run`"""
        self.msg('Collecting stills from {} to {} degree'.format(*run.scope))
        images, metas = [], []
        if run.has_beam_delta_information:
            run.calculate_beamshifts(self.ctrl, self.beamshift)

        with self.ctrl.beam.unblanked(delay=0.2), self.ctrl.cam.blocked():
            for step in run.steps:
                if run.has_beam_delta_information:
                    self.ctrl.beamshift.set(step.beamshift_x, step.beamshift_y)
                self.ctrl.stage.a = step.alpha
                image, meta = self.ctrl.get_image(exposure=run.exposure)
                images.append(image)
                metas.append(meta)
        run.table['image'] = images
        run.table['meta'] = metas
        self.msg('Collected stills from {} to {} degree'.format(*run.scope))

    def collect_tracking_stills(self, run: Run) -> None:
        """Get & put stills to `self.tracking_queue` to eval asynchronously."""
        with self.ctrl.beam.unblanked(delay=0.2), self.ctrl.cam.blocked():
            for step in run.steps:
                self.ctrl.stage.a = step.alpha
                step.image = self.ctrl.get_image(exposure=run.exposure)[0]
                self.steps_queue.put(step)
        self.steps_queue.put(None)

    def collect_continuous(self, run: Run) -> None:
        """Collect a series of scans at angles/exposure specified in `run`"""
        self.msg('Collecting scans from {} to {} degree'.format(*run.scope))
        images, metas = [], []
        if run.has_beam_delta_information:
            run.calculate_beamshifts(self.ctrl, self.beamshift)
        rot_speed, run.exposure = self.determine_rotation_speed_and_exposure(run)

        self.ctrl.stage.a = float(run.table.loc[0, 'alpha'])
        with self.ctrl.stage.rotation_speed(speed=rot_speed):
            with self.ctrl.beam.unblanked(delay=0.2):
                movie = self.ctrl.get_movie(n_frames=len(run.table) - 1, exposure=run.exposure)
                a = float(run.table.iloc[-1].loc['alpha'])
                self.ctrl.stage.set_with_speed(a=a, speed=rot_speed, wait=False)
                for step, (image, meta) in zip(run.steps, movie):
                    if run.has_beam_delta_information:
                        self.ctrl.beamshift.set(step.beamshift_x, step.beamshift_y)
                    images.append(image)
                    metas.append(meta)
        run.make_continuous()
        run.table['image'] = images
        run.table['meta'] = metas
        self.msg(str(run))

    def determine_rotation_speed_and_exposure(self, run: Run) -> tuple[float, float]:
        """Closest possible speed setting & exposure considering dead time."""
        detector_dead_time = self.get_dead_time(run.exposure)
        time_for_one_frame = run.exposure + detector_dead_time
        rot_calib = self.get_stage_rotation()
        rot_plan = rot_calib.plan_rotation(time_for_one_frame / run.osc_angle)
        exposure = abs(rot_plan.pace * run.osc_angle) - detector_dead_time
        return rot_plan.speed, exposure

    def get_run_output_path(self, run: DiffractionRun) -> Path:
        """Returns self.path if only 1 run done, self.path/sub## if
        multiple."""
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

        self.msg(f'Saving experiment in: {out_path}')
        rotation_axis = config.camera.camera_rotation_vs_stage_xy
        pixel_size = config.calibration['diff']['pixelsize'].get(self.camera_length, -1)
        physical_pixel_size = config.camera.physical_pixelsize  # mm
        wavelength = config.microscope.wavelength  # angstrom
        stretch_azimuth = config.camera.stretch_azimuth
        stretch_amplitude = config.camera.stretch_amplitude

        if self.diffraction_mode == 'continuous':
            method = 'Continuous-Rotation 3D ED'
        else:
            method = 'Rotation Electron Diffraction'

        img_conv = ImgConversion(
            buffer=run.buffer,
            osc_angle=run.osc_angle,
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
            method=method,
        )

        img_conv.threadpoolwriter(tiff_path=tiff_path, mrc_path=mrc_path, workers=8)
        img_conv.write_ed3d(mrc_path)
        img_conv.write_pets_inp(out_path)
        img_conv.write_beam_centers(out_path)
        self.msg('Data collection and conversion done. FastADT experiment finalized.')
