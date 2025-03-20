from __future__ import annotations

import contextlib
import datetime
import time
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from instamatic import config
from instamatic.calibrate import CalibBeamShift
from instamatic.calibrate.filenames import CALIB_BEAMSHIFT
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.gui.videostream_service import ImageDrawOverlay
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


def safe_range(start: float, stop: float, step: float) -> np.ndarray:  # noqa
    step_count = round(abs(stop - start) / step) + 1
    return np.linspace(start, stop, step_count, endpoint=True, dtype=float)


class RatsRun:
    """Collection of details of a single RATS run."""

    def __init__(self, **columns: Sequence) -> None:
        self.table = pd.DataFrame.from_dict(columns)

    @classmethod
    def alignment_from_params(cls, params: dict[str, Any]) -> 'RatsRun':
        return cls(alpha=[0.0], exposure=[params['tracking_time']])

    @classmethod
    def tracking_from_params(cls, params: dict[str, Any]) -> 'RatsRun':
        alpha_range = safe_range(
            start=params['diffraction_start'],
            stop=params['diffraction_stop'],
            step=params['tracking_step'],
        )
        tracking_run = RatsRun(alpha=alpha_range)
        tracking_run.table['exposure'] = params['tracking_time']
        return tracking_run

    @classmethod
    def diffraction_from_params(
        cls,
        params: dict[str, Any],
        tracking_run: Optional['RatsRun'] = None,
    ) -> 'RatsRun':
        alpha_range = safe_range(
            start=params['diffraction_start'],
            stop=params['diffraction_stop'],
            step=params['diffraction_step'],
        )
        diffraction_run = RatsRun(alpha=alpha_range)
        diffraction_run.table['exposure'] = params['diffraction_time']
        if tracking_run is not None:
            delta_xs = tracking_run.interpolate(alpha_range, 'delta_x')
            delta_ys = tracking_run.interpolate(alpha_range, 'delta_y')
            diffraction_run.table['delta_x'] = delta_xs
            diffraction_run.table['delta_y'] = delta_ys
        return diffraction_run

    def experiments(self) -> NamedTuple:
        return self.table.itertuples(name='Experiment')  # noqa, rtype is correct

    def interpolate(self, alpha_range: Sequence[float], key: str) -> Sequence[float]:
        return np.interp(alpha_range, self.table['alpha'], self.table[key])

    @property
    def buffer(self) -> List[Tuple[int, np.ndarray, dict]]:
        return [(i, e.image, e.meta) for i, e in enumerate(self.experiments())]

    @property
    def osc_angle(self):
        a = list(self.table['alpha'])
        return (a[-1] - a[0]) / (len(a) - 1) if len(a) > 1 else -1


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

        self.beamshift = self.calibrate_beamshift()

        self.videostream_frame = videostream_frame
        self.vss = self.videostream_frame.stream_service
        # self.overlay = self.vss.add_overlay('rats', ImageDrawOverlay())

        self.vcd = self.videostream_frame.click_dispatcher
        try:
            self.click_listener = self.vcd.add_listener('rats')  # TODO
        except KeyError:  # already exists
            self.click_listener = self.vcd.listeners['rats']

        self.start_time: Optional[datetime.datetime] = None
        self.diffraction_run = ...  # TODO

    def calibrate_beamshift(self) -> CalibBeamShift:
        calib_dir = self.path.parent / 'calib'
        try:
            return CalibBeamShift.from_file(calib_dir / CALIB_BEAMSHIFT)
        except OSError:
            self.ctrl.mode.set('mag1')
            # self.ctrl.store('image') # super important, check out later!
            cbs = CalibBeamShift.live(self.ctrl, outdir=calib_dir)
            return cbs

    def display_message(self, text: str):
        try:
            self.rats_frame.message.set(text)
        except AttributeError:
            pass
        print(text)

    def start_collection(self, **params):
        self.log.info('RATS Data recording started')

        if params['tracking_mode'] == 'manual':
            alignment_run = RatsRun.alignment_from_params(params)
            self.collect(alignment_run)
            tracking_run = RatsRun.tracking_from_params(params)
            self.collect(tracking_run)
            self.resolve_tracking_delta_xy(alignment_run, tracking_run)
        else:
            tracking_run = None

        diffraction_run = RatsRun.diffraction_from_params(params, tracking_run)

        # TODO: correctly determine "imageshift1" from tracking data
        # x_image_shift0_xy = self.ctrl.imageshift1.get()
        # x_image_shifts = [0 * click.x for click in tracking_clicks]
        # y_image_shifts = [0 * click.y for click in tracking_clicks]
        self.ctrl.mode.set('diff')

        self.collect(diffraction_run)

        self.camera_length = int(self.ctrl.magnification.get())

        self.log.info('Collected the following run:')
        self.log.info(str(diffraction_run))

    def collect(self, run: RatsRun) -> None:
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

        for expt in run.experiments():
            if has_beamshifts:
                self.ctrl.beamshift.set(expt.beamshift_x, expt.beamshift_y)
            self.ctrl.stage.a = expt.alpha
            self.ctrl.beam.unblank()
            image, meta = self.ctrl.get_image(exposure=expt.exposure)
            self.ctrl.beam.blank()
            images.append(image)
            metas.append(meta)
        run.table['image'] = images
        run.table['meta'] = metas

        pd.set_option('display.max_rows', 500)
        pd.set_option('display.max_columns', 500)
        pd.set_option('display.width', 150)
        print(run.table)
        self.diffraction_run = run
        self.ctrl.beam.unblank()

    def resolve_tracking_delta_xy(
        self,
        alignment_run: RatsRun,
        tracking_run: RatsRun,
    ) -> None:
        # collecting beam center information
        beam_image = alignment_run.table['image'].iloc[0]
        with self.vss.temporary_provider(lambda: beam_image):
            self.display_message('Please click on the center of the beam')
            with self.click_listener as cl:
                click = cl.get_click()
                x_beam, y_beam = click.x, click.y

        # collecting tracking information
        delta_xs, delta_ys = [], []
        for expt in tracking_run.experiments():
            with self.vss.temporary_provider(lambda: expt.image):
                self.display_message(
                    f'Please click on the crystal ' f'(image={expt.Index}, alpha={expt.alpha}°)'
                )
                with self.click_listener as cl:
                    click = cl.get_click()
                    delta_xs.append(click.x - x_beam)
                    delta_ys.append(click.y - y_beam)
            self.display_message('')
        tracking_run.table['delta_x'] = delta_xs
        tracking_run.table['delta_y'] = delta_ys

        # plot tracking results
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
        plt.show()

    def finalize(self):
        self.log.info(f'Saving experiment in: {self.path}')
        rotation_axis = config.camera.camera_rotation_vs_stage_xy
        pixel_size = config.calibration['diff']['pixelsize'][
            self.camera_length
        ]  # px / Angstrom
        physical_pixelsize = config.camera.physical_pixelsize  # mm
        wavelength = config.microscope.wavelength  # angstrom
        stretch_azimuth = config.camera.stretch_azimuth
        stretch_amplitude = config.camera.stretch_amplitude

        img_conv = ImgConversion(
            buffer=self.diffraction_run.buffer,
            osc_angle=self.diffraction_run.osc_angle,
            start_angle=self.diffraction_run.table['alpha'].iloc[0],
            end_angle=self.diffraction_run.table['alpha'].iloc[-1],
            rotation_axis=rotation_axis,
            acquisition_time=self.diffraction_run.table['exposure'].iloc[0],
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
