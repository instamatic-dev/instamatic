from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple, Union

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
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


def safe_range(start: float, stop: float, step: float) -> np.ndarray:  # noqa
    step_count = max(round(abs(stop - start) / step) + 1, 2)
    return np.linspace(start, stop, step_count, endpoint=True, dtype=float)


class FastADTEarlyTermination(RuntimeError):
    pass


class FastADTMissingCalibError(RuntimeError):
    pass


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
    """Collection of details of a single FastADT run.

    Includes a `.table` describing details of individual steps (to be) measured:
      - alpha - average value of the rotation axes for given frame
      - delta_x - x beam shift relative from center needed to track the crystal
      - delta_y - y beam shift relative from center needed to track the crystal

    Other class attributes include:
      - continuous - whether the run involves continuous scan or single frames
      - exposure - time spent collecting each frame, expressed in seconds
    """

    def __init__(self, exposure=1.0, continuous=False, **columns: Sequence) -> None:
        self.exposure: float = exposure
        self.continuous: bool = continuous
        self.table = pd.DataFrame.from_dict(columns)

    @property
    def scope(self) -> Tuple[float, float]:
        """The range of alpha values scanned during the entire run."""
        a = self.table['alpha']
        if not self.continuous:
            return a.iloc[0], a.iloc[-1]
        return a.iloc[0] - self.osc_angle / 2, a.iloc[-1] + self.osc_angle / 2

    @property
    def steps(self) -> Generator[Step]:
        """Used to iterate over individual run steps – rows of `self.table`"""
        return (Step(**t._asdict()) for t in self.table.itertuples())  # noqa

    def interpolate(self, at: Sequence[float], key: str) -> Sequence[float]:
        """Interpolate values of `table[key]` at a denser grid of points."""
        if at[0] > at[-1]:  # decreasing order: not handled by numpy.interp
            return np.interp(at[::-1], self.table['alpha'][::-1], self.table[key][::-1])[::-1]
        return np.interp(at, self.table['alpha'], self.table[key])

    @property
    def buffer(self) -> List[Tuple[int, np.ndarray, dict]]:
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

    def to_continuous(self) -> Self:
        """Construct a new run from N-1 first rows for continuous method."""
        new_alphas = self.table['alpha'].rolling(2).mean().drop(0)
        new_cols = self.table.iloc[:-1, :].to_dict(orient='list')
        del new_cols['alpha']
        c = self.__class__
        return c(exposure=self.exposure, continuous=True, alpha=new_alphas, **new_cols)

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
    def from_params(cls, params: Dict[str, Any]) -> Self:
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
        params: Dict[str, Any],
        tracking_run: Optional['TrackingRun'] = None,
    ) -> Self:
        alpha_range = safe_range(
            start=params['diffraction_start'],
            stop=params['diffraction_stop'],
            step=params['diffraction_step'],
        )
        run = cls(exposure=params['diffraction_time'], alpha=alpha_range)
        if tracking_run is not None:
            run.table['delta_x'] = tracking_run.interpolate(alpha_range, 'delta_x')
            run.table['delta_y'] = tracking_run.interpolate(alpha_range, 'delta_y')
        return run


class Experiment(ExperimentBase):
    """Initialize a FastADT-style rotation electron diffraction experiment.

    ctrl:
        Instance of instamatic.controller.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Optional instance of `logging.Logger`
    flatfield:
        Optional path to flatfield correction image
    fast_adt_frame:
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

        self.mrc_path = self.path / 'mrc'
        self.tiff_path = self.path / 'tiff'
        self.tiff_image_path = self.path / 'tiff_image'
        self.mrc_path.mkdir(exist_ok=True, parents=True)
        self.tiff_path.mkdir(exist_ok=True, parents=True)
        self.tiff_image_path.mkdir(exist_ok=True, parents=True)

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

        self.steps_queue: Queue[Union[Step, None]] = Queue()
        self.run: Optional[Run] = None

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
            return CalibBeamShift.live(self.ctrl, outdir=calib_dir)

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
        self.msg('FastADT experiment started')
        with self.ctrl.beam.blanked():
            image_path = self.tiff_image_path / 'image.tiff'
            if not image_path.exists():
                self.ctrl.restore('FastADT_image')
                with self.ctrl.beam.unblanked(delay=0.2):
                    self.ctrl.get_image(params['tracking_time'], out=image_path)

            if params['tracking_mode'] == 'manual':
                tracking_run = TrackingRun.from_params(params)
                self.collect_manual_tracking(tracking_run)
            else:
                tracking_run = None

            self.run = DiffractionRun.from_params(params, tracking_run)
            self.ctrl.restore('FastADT_diff')
            self.camera_length = int(self.ctrl.magnification.get())
            self.diffraction_mode = params['diffraction_mode']
            if self.diffraction_mode == 'stills':
                self.collect_stills(self.run)
            elif self.diffraction_mode == 'continuous':
                self.collect_continuous(self.run)
            print(self.run.table)
            self.ctrl.restore('FastADT_image')

            self.log.info('Collected the following run:')
            self.log.info(str(self.run))
            self.ctrl.stage.a = 0.0

    def collect_manual_tracking(self, run: TrackingRun) -> None:
        """Determine the target beam shifts `delta_x` and `delta_y` manually,
        based on the beam center found life (to find clicking offset) and
        `TrackingRun` to be used for crystal tracking in later experiment."""

        self.restore_fast_adt_diff_for_image()
        self.beamshift = self.get_beamshift()
        self.ctrl.stage.a = run.table.loc[len(run.table) // 2, 'alpha']
        with self.ctrl.beam.unblanked():
            self.msg('Collecting tracking. Click on the center of the beam.')
            with self.click_listener as cl:
                click = cl.get_click()
                beam_center_x, beam_center_y = click.x, click.y

        self.ctrl.restore('FastADT_track')
        delta_xs, delta_ys = [], []
        Thread(target=self.enqueue_still_steps, args=(run,), daemon=True).start()
        while (step := self.steps_queue.get()) is not None:
            with self.videostream_processor.temporary(frame=step.image):
                m = f'Click on the crystal (image={step.Index}, alpha={step.alpha} deg).'
                self.msg(m)
                with self.click_listener as cl:
                    click = cl.get_click()
                    delta_xs.append(click.x - beam_center_x)
                    delta_ys.append(click.y - beam_center_y)
            self.msg('')
        run.table['delta_x'] = delta_xs
        run.table['delta_y'] = delta_ys
        self.plot_tracking(tracking_run=run)

    def collect_stills(self, run: Run) -> None:
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

    def enqueue_still_steps(self, run: Run) -> None:
        """Get & put stills to `self.tracking_queue` to eval asynchronously."""
        with self.ctrl.beam.unblanked(delay=0.2), self.ctrl.cam.blocked():
            for step in run.steps:
                self.ctrl.stage.a = step.alpha
                step.image = self.ctrl.get_image(exposure=run.exposure)[0]
                self.steps_queue.put(step)
        self.steps_queue.put(None)

    def collect_continuous(self, run) -> None:
        self.msg('Collecting scans from {} to {} degree'.format(*run.scope))
        images, metas = [], []
        if run.has_beam_delta_information:
            run.calculate_beamshifts(self.ctrl, self.beamshift)

        # this part correctly finds the closest possible speed settings for expt
        frame_sep = run.exposure + self.get_dead_time(run.exposure)
        rot_calib = self.get_stage_rotation()
        rot_plan = rot_calib.plan_rotation(frame_sep / run.osc_angle)
        run.exposure = abs(rot_plan.pace * run.osc_angle) - self.get_dead_time(run.exposure)

        self.ctrl.stage.a = float(run.table.loc[0, 'alpha'])
        with self.ctrl.stage.rotation_speed(speed=rot_plan.speed):
            with self.ctrl.beam.unblanked(delay=0.2):
                movie = self.ctrl.get_movie(n_frames=len(run.table) - 1, exposure=run.exposure)
                a = float(run.table.iloc[-1].loc['alpha'])
                self.ctrl.stage.set_with_speed(a=a, speed=rot_plan.speed, wait=False)
                for step, (image, header) in zip(run.steps, movie):
                    if run.has_beam_delta_information:
                        self.ctrl.beamshift.set(step.beamshift_x, step.beamshift_y)
                    images.append(image)
                    metas.append(header)
            self.run = run.to_continuous()
            self.run.table['image'] = images
            self.run.table['meta'] = metas
        self.msg('Collected scans from {} to {} degree'.format(*run.scope))

    def finalize(self) -> None:
        self.msg(f'Saving experiment in: {self.path}')
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
            buffer=self.run.buffer,
            osc_angle=self.run.osc_angle,
            start_angle=self.run.table['alpha'].iloc[0],
            end_angle=self.run.table['alpha'].iloc[-1],
            rotation_axis=rotation_axis,
            acquisition_time=self.run.exposure,
            flatfield=self.flatfield,
            pixelsize=pixel_size,
            physical_pixelsize=physical_pixel_size,
            wavelength=wavelength,
            stretch_amplitude=stretch_amplitude,
            stretch_azimuth=stretch_azimuth,
            method=method,
        )
        img_conv.threadpoolwriter(tiff_path=self.tiff_path, mrc_path=self.mrc_path, workers=8)
        img_conv.write_ed3d(self.mrc_path)
        img_conv.write_pets_inp(self.path)
        img_conv.write_beam_centers(self.path)
        self.msg('Data collection and conversion done. FastADT experiment finalized.')

    def plot_tracking(self, tracking_run: Run) -> None:
        """Plot tracking results in `VideoStreamFrame` and let user reject."""
        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        ax1.set_xlabel('alpha [degrees]')
        ax1.set_ylabel('ΔX [pixels]')
        ax2.set_ylabel('ΔY [pixels]')
        ax1.yaxis.label.set_color('red')
        ax2.yaxis.label.set_color('blue')
        ax2.spines['left'].set_color('red')
        ax2.spines['right'].set_color('blue')
        ax1.tick_params(axis='y', colors='red')
        ax2.tick_params(axis='y', colors='blue')
        ax1.plot('alpha', 'delta_x', data=tracking_run.table, color='red', label='X')
        ax2.plot('alpha', 'delta_y', data=tracking_run.table, color='blue', label='Y')
        fig.tight_layout()
        self.msg('Tracking results: left-click to accept, right-click to reject.')
        with self.videostream_processor.temporary(figure=fig):
            with self.click_listener as cl:
                if cl.get_click().button != 1:
                    self.msg('Experiment abandoned after tracking.')
                    raise FastADTEarlyTermination('Experiment abandoned after tracking.')

    def teardown(self) -> None:
        self.finalize()
