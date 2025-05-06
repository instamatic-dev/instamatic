from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from typing_extensions import Self

from instamatic import config
from instamatic.calibrate import CalibBeamShift, CalibMovieDelays, CalibStageRotation
from instamatic.calibrate.filenames import CALIB_BEAMSHIFT
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


def safe_range(start: float, stop: float, step: float) -> np.ndarray:  # noqa
    step_count = round(abs(stop - start) / step) + 1
    return np.linspace(start, stop, step_count, endpoint=True, dtype=float)


class MissingCalibError(RuntimeError):
    pass


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ RUN CLASSES ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class Run:
    """Collection of details of a single RATS run. Includes a `.table`

    describing individual frames (to be) measured. Possible col. names include:
      - alpha - average value of the rotation axes for given frame
      - delta_x - x beam shift relative from center needed to track the crystal
      - delta_y - y beam shift relative from center needed to track the crystal

    Other class attributes include:
      - exposure - time spent collecting each frame, expressed in seconds
    """

    def __init__(self, exposure=1.0, continuous=False, **columns: Sequence) -> None:
        self.exposure: float = exposure
        self.table = pd.DataFrame.from_dict(columns)
        self.continuous = continuous

    @classmethod
    def concat(cls, runs: Sequence[Run]) -> Self:
        exposure = runs[0].exposure
        continuous = runs[0].continuous
        table = pd.concat(r.table.set_index('alpha') for r in runs)
        table = table[~table.index.duplicated(keep='last')]
        cols = table.reset_index().sort_values(by='alpha').to_dict(orient='list')
        return cls(exposure=exposure, continuous=continuous, **cols)

    @property
    def scope(self):
        print(self.table)
        a = self.table['alpha']
        if not self.continuous:
            return a.iloc[0], a.iloc[-1]
        return a.iloc[0] - self.osc_angle / 2, a.iloc[-1] + self.osc_angle / 2

    @property
    def experiments(self) -> NamedTuple:
        return self.table.itertuples(name='Experiment')  # noqa, rtype is correct

    def interpolate(self, alpha_range: Sequence[float], key: str) -> Sequence[float]:
        return np.interp(alpha_range, self.table['alpha'], self.table[key])

    @property
    def buffer(self) -> List[Tuple[int, np.ndarray, dict]]:
        return [(i, e.image, e.meta) for i, e in enumerate(self.experiments)]

    @property
    def osc_angle(self):
        a = list(self.table['alpha'])
        return (a[-1] - a[0]) / (len(a) - 1) if len(a) > 1 else -1

    def to_continuous(self) -> Self:
        """Construct a new run from N-1 first rows for continuous method."""
        new_alphas = self.table['alpha'].rolling(2).mean().drop(0)
        new_cols = self.table.iloc[:-1, :].to_dict(orient='list')
        del new_cols['alpha']
        c = self.__class__(
            exposure=self.exposure, continuous=True, alpha=new_alphas, **new_cols
        )
        return c


class BeamCenterRun(Run):
    """A 1-image run designed to correct for clicking offset on beam center."""

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> Self:
        return cls(exposure=params['tracking_time'], alpha=[0.0])


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
            delta_xs = tracking_run.interpolate(alpha_range, 'delta_x')
            delta_ys = tracking_run.interpolate(alpha_range, 'delta_y')
            run.table['delta_x'] = delta_xs
            run.table['delta_y'] = delta_ys
        return run


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ EXPERIMENT ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class RatsExperiment(ExperimentBase):
    """Initialize RATS-style rotation electron diffraction experiment.

    ctrl:
        Instance of instamatic.controller.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Instance of `logging.Logger`
    flatfield:
        Path to flatfield correction image
    """

    def __init__(
        self,
        ctrl,
        path: str = None,
        log=None,
        flatfield=None,
        rats_frame=None,
        videostream_frame=None,
    ):
        super().__init__()
        self.ctrl = ctrl
        self.path = Path(path)

        self.mrc_path = self.path / 'mrc'
        self.tiff_path = self.path / 'tiff'
        self.tiff_image_path = self.path / 'tiff_image'

        self.tiff_path.mkdir(exist_ok=True, parents=True)
        self.tiff_image_path.mkdir(exist_ok=True, parents=True)
        self.mrc_path.mkdir(exist_ok=True, parents=True)

        self.offset = 1
        self.log = log
        self.flatfield = flatfield

        self.rats_frame = rats_frame

        self.beamshift = self.get_beamshift()

        self.videostream_frame = videostream_frame
        self.vss = self.videostream_frame.stream_service
        # self.overlay = self.vss.add_overlay('rats', ImageDrawOverlay())

        self.vcd = self.videostream_frame.click_dispatcher
        try:
            self.click_listener = self.vcd.add_listener('rats')  # TODO
        except KeyError:  # already exists
            self.click_listener = self.vcd.listeners['rats']

        self.start_time: Optional[datetime.datetime] = None
        self.run: Optional[Run] = None
        self.run_list: List[Run] = []

    @property
    def alpha_scope(self) -> Tuple[float, float]:
        return (
            min(min(r.scope) for r in self.run_list),
            max(max(r.scope) for r in self.run_list),
        )

    def get_beamshift(self) -> CalibBeamShift:
        calib_dir = self.path.parent / 'calib'
        try:
            return CalibBeamShift.from_file(calib_dir / CALIB_BEAMSHIFT)
        except OSError:
            self.ctrl.mode.set('mag1')
            # self.ctrl.store('image') # super important, check out later!
            cbs = CalibBeamShift.live(self.ctrl, outdir=calib_dir)
            return cbs

    def get_dead_time(
        self,
        exposure: float = 0.0,
        header_keys_variable: tuple = (),
        header_keys_common: tuple = (),
    ) -> float:
        """Get time between get_movie frames from any source available or 0."""
        cam_dead_time = getattr(self.ctrl.cam, 'dead_time', None)
        if cam_dead_time is not None:
            return cam_dead_time
        self.display_message('`cam.dead_time` not found. Looking in calibrate file...')
        try:
            calib_movie_delays = CalibMovieDelays.from_file(
                exposure, header_keys_variable, header_keys_common
            )
        except RuntimeWarning:
            return 0.0
        else:
            return calib_movie_delays.dead_time

    def get_stage_rotation(self) -> CalibStageRotation:
        """Get rotation calib.

        if present; otherwise warn user & terminate.
        """
        try:
            return CalibStageRotation.from_file()
        except OSError:
            msg = (
                'Collecting cRED with this script requires calibrated stage rotation.'
                ' Please run `instamatic.calibrate_stage_rotation` first.'
            )
            self.display_message(msg)
            raise MissingCalibError(msg)

    def display_message(self, text: str):
        try:
            self.rats_frame.message.set(text)
        except AttributeError:
            pass
        print(text)

    def start_collection(self, **params) -> None:
        self.log.info('RATS Data recording started')
        self.collect(**params)

    def extend_collection(self, **params):
        new_scope = (params['diffraction_start'], params['diffraction_stop'])
        old_scope = self.alpha_scope
        if len(np.unique(np.array(old_scope + new_scope).round(6))) != 3:
            msg = (
                f'New alpha scope {new_scope} must extend existing'
                f'alpha scope {old_scope}. Terminating.'
            )
            self.display_message(msg)
            return
        self.collect(**params)

    def collect(self, **params) -> None:
        if params['tracking_mode'] == 'manual':
            alignment_run = BeamCenterRun.from_params(params)
            self.collect_stills(alignment_run)
            tracking_run = TrackingRun.from_params(params)
            self.collect_stills(tracking_run)
            self.resolve_tracking_delta_xy(alignment_run, tracking_run)
        else:
            tracking_run = None

        run = DiffractionRun.from_params(params, tracking_run)
        self.ctrl.mode.set('diff')

        if params['diffraction_mode'] == 'stills':
            self.run = self.collect_stills(run)
        elif params['diffraction_mode'] == 'continuous':
            self.run = self.collect_continuous(run)

        self.camera_length = int(self.ctrl.magnification.get())

        self.log.info('Collected the following run:')
        self.log.info(str(self.run))
        self.run_list.append(self.run)

    def collect_stills(self, run) -> Run:
        images, metas = [], []
        has_beamshifts = ('delta_x' in run.table) and ('delta_y' in run.table)

        self.ctrl.beam.blank()
        self.beamshift.center(self.ctrl)  # passes numpy classes
        if has_beamshifts:
            px_center = [xy / 2.0 for xy in self.ctrl.cam.get_image_dimensions()]
            delta_xys = run.table[['delta_x', 'delta_y']].to_numpy()
            crystal_xys = px_center + delta_xys
            beamshifts = self.beamshift.pixelcoord_to_beamshift(crystal_xys)
            run.table[['beamshift_x', 'beamshift_y']] = beamshifts

        for expt in run.experiments:
            if has_beamshifts:
                self.ctrl.beamshift.set(expt.beamshift_x, expt.beamshift_y)
            self.ctrl.stage.a = expt.alpha
            self.ctrl.beam.unblank()
            image, meta = self.ctrl.get_image(exposure=run.exposure)
            self.ctrl.beam.blank()
            images.append(image)
            metas.append(meta)
        run.table['image'] = images
        run.table['meta'] = metas

        pd.set_option('display.max_rows', 500)
        pd.set_option('display.max_columns', 500)
        pd.set_option('display.width', 150)
        print(run.table)
        self.ctrl.beam.unblank()
        return run

    def collect_continuous(self, run) -> Run:
        images, metas = [], []
        has_beamshifts = ('delta_x' in run.table) and ('delta_y' in run.table)

        self.ctrl.beam.blank()  # TODO: scatter correctly
        self.beamshift.center(self.ctrl)
        if has_beamshifts:
            px_center = [xy / 2.0 for xy in self.ctrl.cam.get_image_dimensions()]
            delta_xys = run.table[['delta_x', 'delta_y']].to_numpy()
            crystal_xys = px_center + delta_xys
            beamshifts = self.beamshift.pixelcoord_to_beamshift(crystal_xys)
            run.table[['beamshift_x', 'beamshift_y']] = beamshifts

        # this part correctly finds the closest possible speed settings for expt
        frame_sep = run.exposure + self.get_dead_time(run.exposure)
        rot_calib = self.get_stage_rotation()
        rot_plan = rot_calib.plan_rotation(frame_sep / run.osc_angle)
        run.exposure = rot_plan.pace * run.osc_angle - self.get_dead_time(run.exposure)
        with self.ctrl.stage.rotation_speed(speed=rot_plan.speed):
            self.ctrl.beam.unblank()
            self.ctrl.stage.a = float(run.table.loc[0, 'alpha'])
            movie = self.ctrl.get_movie(n_frames=len(run.table) - 1, exposure=run.exposure)
            self.ctrl.stage.set(a=float(run.table.iloc[-1].loc['alpha']), wait=False)
            for expt, (image, header) in zip(run.experiments, movie):
                if has_beamshifts:
                    self.ctrl.beamshift.set(expt.beamshift_x, expt.beamshift_y)
                images.append(image)
                metas.append(header)
            self.ctrl.beam.blank()
            run = run.to_continuous()
            run.table['image'] = images
            run.table['meta'] = metas

        pd.set_option('display.max_rows', 500)
        pd.set_option('display.max_columns', 500)
        pd.set_option('display.width', 150)
        print(run.table)
        self.ctrl.beam.unblank()
        return run

    def resolve_tracking_delta_xy(
        self,
        beam_center_run: BeamCenterRun,
        tracking_run: TrackingRun,
    ) -> None:
        """Determine the target beam shifts `delta_x` and `delta_y` manually,
        based on the `BeamCenterRun` (to find clicking offset) and
        `TrackingRun` to be used later for crystal tracking in actual
        experiment."""

        # collecting beam center information
        beam_image = beam_center_run.table['image'].iloc[0]
        with self.vss.temporary_provider(lambda: beam_image):
            self.display_message('Please click on the center of the beam')
            with self.click_listener as cl:
                click = cl.get_click()
                beam_center_x, beam_center_y = click.x, click.y

        # collecting tracking information
        delta_xs, delta_ys = [], []
        for expt in tracking_run.experiments:
            with self.vss.temporary_provider(lambda: expt.image):
                self.display_message(
                    f'Please click on the crystal ' f'(image={expt.Index}, alpha={expt.alpha}°)'
                )
                with self.click_listener as cl:
                    click = cl.get_click()
                    delta_xs.append(click.x - beam_center_x)
                    delta_ys.append(click.y - beam_center_y)
            self.display_message('')
        tracking_run.table['delta_x'] = delta_xs
        tracking_run.table['delta_y'] = delta_ys

        # plot tracking results
        # fig, ax1 = plt.subplots()
        # ax2 = ax1.twinx()
        # ax1.set_xlabel('alpha [degrees]')
        # ax1.set_ylabel('ΔX [pixels]')
        # ax2.set_ylabel('ΔY [pixels]')
        # ax1.yaxis.label.set_color('red')
        # ax2.yaxis.label.set_color('blue')
        # ax2.spines['left'].set_color('red')
        # ax2.spines['right'].set_color('blue')
        # ax1.tick_params(axis='y', colors='red')
        # ax2.tick_params(axis='y', colors='blue')
        # ax1.plot('alpha', 'delta_x', data=tracking_run.table, color='red', label='X')
        # ax2.plot('alpha', 'delta_y', data=tracking_run.table, color='blue', label='Y')
        # fig.tight_layout()
        # plt.show()

    def finalize(self):
        self.log.info(f'Saving experiment in: {self.path}')
        rotation_axis = config.camera.camera_rotation_vs_stage_xy
        pixel_size = config.calibration['diff']['pixelsize'][self.camera_length]
        physical_pixelsize = config.camera.physical_pixelsize  # mm
        wavelength = config.microscope.wavelength  # angstrom
        stretch_azimuth = config.camera.stretch_azimuth
        stretch_amplitude = config.camera.stretch_amplitude

        run = Run.concat(self.run_list) if len(self.run_list) > 1 else self.run

        img_conv = ImgConversion(
            buffer=run.buffer,
            osc_angle=run.osc_angle,
            start_angle=run.table['alpha'].iloc[0],
            end_angle=run.table['alpha'].iloc[-1],
            rotation_axis=rotation_axis,
            acquisition_time=run.exposure,
            flatfield=self.flatfield,
            pixelsize=pixel_size,
            physical_pixelsize=physical_pixelsize,
            wavelength=wavelength,
            stretch_amplitude=stretch_amplitude,
            stretch_azimuth=stretch_azimuth,
        )
        print('Writing data files...')
        img_conv.threadpoolwriter(tiff_path=self.tiff_path, mrc_path=self.mrc_path, workers=8)

        print('Writing input files...')
        img_conv.write_ed3d(self.mrc_path)
        img_conv.write_pets_inp(self.path)
        img_conv.write_beam_centers(self.path)

        print('Data Collection and Conversion Done.')
        print()

        return True

    def teardown(self):
        self.finalize()
