import datetime
import os
import time
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm

from instamatic import config
from instamatic.formats import write_tiff
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


class Experiment:
    """Initialize stepwise rotation electron diffraction experiment.

    ctrl:
        Instance of instamatic.TEMController.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Instance of `logging.Logger`
    flatfield:
        Path to flatfield correction image
    """

    def __init__(self, ctrl, path: str = None, log=None, flatfield=None):
        super().__init__()
        self.ctrl = ctrl
        self.path = Path(path)

        self.mrc_path = self.path / 'mrc'
        self.tiff_path = self.path / 'tiff'
        self.tiff_image_path = self.path / 'tiff_image'

        self.tiff_path.mkdir(exist_ok=True, parents=True)
        self.tiff_image_path.mkdir(exist_ok=True, parents=True)
        self.mrc_path.mkdir(exist_ok=True, parents=True)

        self.logger = log
        self.camtype = ctrl.cam.name

        self.flatfield = flatfield

        self.offset = 1
        self.current_angle = None
        self.buffer = []

        self.img_ref = None

    def start_collection(self, exposure_time: float, end_angle: float, stepsize: float):
        """Start or continue data collection for `tilt_range` degrees with
        steps given by `stepsize`, To finalize data collection and write data
        files, run `self.finalize`.

        The number of images collected is defined by `tilt_range / stepsize`.

        exposure_time:
            Exposure time for each image in seconds
        tilt_range:
            Tilt range starting from the current angle in degrees. Must be positive.
        stepsize:
            Step size for the angle in degrees, controls the direction and can be positive or negative
        """
        self.spotsize = self.ctrl.spotsize
        ctrl = self.ctrl

        if self.current_angle is None:
            self.start_angle = start_angle = ctrl.stage.a
        else:
            start_angle = self.current_angle + stepsize

        if start_angle > end_angle:
            stepsize = -stepsize
        else:
            stepsize = stepsize

        self.now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info('Data recording started at: {self.now}')
        self.logger.info(f'Exposure time: {exposure_time} s, start angle: {start_angle}, end angle: {end_angle}, step size: {stepsize}')

        tilt_positions = np.arange(start_angle, end_angle, stepsize)
        print(f'\nStart_angle: {start_angle:.3f}')
        # print "Angles:", tilt_positions

        image_mode = ctrl.mode.get()
        if config.settings.microscope[:3] == "fei":
            if image_mode in ('D', 'LAD'):
                raise RuntimeError("Please set the microscope to IMAGE mode")
        else:
            if image_mode == 'diff':
                raise RuntimeError("Please set the microscope to IMAGE mode")

        self.img_ref, h = self.ctrl.get_image(exposure_time)

        if ctrl.cam.streamable:
            ctrl.cam.block()

        isFocused = False
        isAligned = False

        for i, angle in enumerate(tqdm(tilt_positions)):
            ctrl.stage.a = angle

            j = i + self.offset
            while isFocused and isAligned:
                img, h = self.ctrl.get_image(exposure_time)
                if not isFocused:
                    isFocused = self.focus_image(self, img)
                if not isAligned:
                    isAligned = self.align_image(self, img)

            img, h = self.ctrl.get_image(exposure_time)

            # suppose eccentric height is near 0 degree
            if abs(angle) >= 50 and i % 2 == 1: 
                isFocused = False
            elif abs(angle) >= 25 and i % 5 == 4:
                isFocused = False
            elif abs(angle) >= 0 and i % 9 == 8:
                isFocused = False
            isAligned = False

            self.buffer.append((j, img, h))

        self.offset += len(tilt_positions)
        self.nframes = j

        self.end_angle = end_angle = ctrl.stage.a

        if ctrl.cam.streamable:
            ctrl.cam.unblock()

        self.camera_length = int(self.ctrl.magnification.get())
        self.stepsize = stepsize
        self.exposure_time = exposure_time

        with open(self.path / 'summary.txt', 'a') as f:
            print(f'{self.now}: Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree in {len(tilt_positions)} frames.', file=f)
            print(f'Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree in {len(tilt_positions)} frames.')

        self.logger.info('Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree (camera length: {camera_length} mm).')

        self.current_angle = angle
        print(f'Done, current angle = {self.current_angle:.2f} degrees')

    def focus_image(self, img):
        pass

    def align_image(self, img):
        pass

    def finalize(self):
        """Finalize data collection after `self.start_collection` has been run.

        Write data in `self.buffer` to path given by `self.path`.
        """
        self.logger.info(f'Data saving path: {self.path}')
        self.rotation_axis = config.camera.camera_rotation_vs_stage_xy

        if config.settings.microscope[:3] == "fei":
            self.ctrl.tem.setProjectionMode(2)
            self.pixelsize = config.calibration[self.ctrl.mode.get()]['pixelsize'][self.camera_length]  # px / Angstrom
            self.ctrl.tem.setProjectionMode(1)
        else:
            self.pixelsize = config.calibration['diff']['pixelsize'][self.camera_length]  # px / Angstrom
        self.physical_pixelsize = config.camera.physical_pixelsize  # mm
        self.wavelength = config.microscope.wavelength  # angstrom
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        with open(self.path / 'summary.txt', 'a') as f:
            print(f'Rotation range: {self.end_angle-self.start_angle:.2f} degrees', file=f)
            print(f'Exposure Time: {self.exposure_time:.3f} s', file=f)
            print(f'Spot Size: {self.spotsize}', file=f)
            print(f'Camera length: {self.camera_length} mm', file=f)
            print(f'Pixelsize: {self.pixelsize} px/Angstrom', file=f)
            print(f'Physical pixelsize: {self.physical_pixelsize} um', file=f)
            print(f'Wavelength: {self.wavelength} Angstrom', file=f)
            print(f'Stretch amplitude: {self.stretch_azimuth} %', file=f)
            print(f'Stretch azimuth: {self.stretch_amplitude} degrees', file=f)
            print(f'Rotation axis: {self.rotation_axis} radians', file=f)
            print(f'Stepsize: {self.stepsize:.4f} degrees', file=f)
            print(f'Number of frames: {self.nframes}', file=f)

        img_conv = ImgConversion(buffer=self.buffer,
                                 osc_angle=self.stepsize,
                                 start_angle=self.start_angle,
                                 end_angle=self.end_angle,
                                 rotation_axis=self.rotation_axis,
                                 acquisition_time=self.exposure_time,
                                 flatfield=self.flatfield,
                                 pixelsize=self.pixelsize,
                                 physical_pixelsize=self.physical_pixelsize,
                                 wavelength=self.wavelength,
                                 stretch_amplitude=self.stretch_amplitude,
                                 stretch_azimuth=self.stretch_azimuth,
                                 )

        print('Writing data files...')
        img_conv.threadpoolwriter(tiff_path=self.tiff_path,
                                  mrc_path=self.mrc_path,
                                  workers=8)

        print('Writing input files...')
        img_conv.write_ed3d(self.mrc_path)
        img_conv.write_pets_inp(self.path)

        img_conv.write_beam_centers(self.path)

        print('Data Collection and Conversion Done.')
        print()

        return True


def main():
    from instamatic import TEMController
    ctrl = TEMController.initialize()

    import logging
    log = logging.getLogger(__name__)

    exposure_time = 0.5
    end_angle = 10
    stepsize = 1.0

    i = 1
    while True:
        expdir = f'experiment_{i}'
        if os.path.exists(expdir):
            i += 1
        else:
            break

    print(f'\nData directory: {expdir}')

    red_exp = Experiment(ctrl=ctrl, path=expdir, log=log, flatfield=None)
    red_exp.start_collection(exposure_time=exposure_time, end_angle=end_angle, stepsize=stepsize)

    input('Press << Enter >> to start the experiment... ')

    while not input(f'\nPress << Enter >> to continue for another {tilt_range} degrees. [any key to finalize] '):
        red_exp.start_collection(exposure_time=exposure_time, end_angle=end_angle, stepsize=stepsize)

    red_exp.finalize()


if __name__ == '__main__':
    main()
