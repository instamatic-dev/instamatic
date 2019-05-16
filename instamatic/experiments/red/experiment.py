import os
import time, datetime, tqdm
import numpy as np
from pathlib import Path
from instamatic import config
from instamatic.formats import write_tiff
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


class Experiment(object):
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
    def __init__(self, ctrl, path: str=None, log=None, flatfield=None):
        super(Experiment,self).__init__()
        self.ctrl = ctrl
        self.path = Path(path)

        self.mrc_path = path / "mrc"
        self.tiff_path = path / "tiff"
        self.tiff_image_path = path / "tiff_image"

        self.tiff_path.mkdir(exist_ok=True, parents=True)
        self.tiff_image_path.mkdir(exist_ok=True, parents=True)
        self.mrc_path.mkdir(exist_ok=True, parents=True)

        self.logger = log
        self.camtype = ctrl.cam.name

        self.flatfield = flatfield

        self.offset = 1
        self.current_angle = None
        self.buffer = []
        
    def start_collection(self, exposure_time: float, tilt_range: float, stepsize: float):
        """Start or continue data collection for `tilt_range` degrees with steps given by `stepsize`,
        To finalize data collection and write data files, run `self.finalize`.

        The number of images collected is defined by `tilt_range / stepsize`.

        exposure_time:
            Exposure time for each image in seconds
        tilt_range:
            Tilt range starting from the current angle in degrees. Must be positive.
        stepsize:
            Step size for the angle in degrees, controls the direction and can be positive or negative

        """
        self.spotsize = self.ctrl.spotsize
        self.now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.info("Data recording started at: {self.now}")
        self.logger.info(f"Exposure time: {exposure_time} s, Tilt range: {tilt_range}, step size: {stepsize}")

        ctrl = self.ctrl

        if stepsize < 0:
            tilt_range = -abs(tilt_range)
        else:
            tilt_range =  abs(tilt_range)

        if self.current_angle is None:
            self.start_angle = start_angle = ctrl.stageposition.a
        else:
            start_angle = self.current_angle + stepsize

        tilt_positions = np.arange(start_angle, start_angle+tilt_range, stepsize)
        print(f"\nStart_angle: {start_angle:.3f}")
        # print "Angles:", tilt_positions

        image_mode = ctrl.mode
        if image_mode != "diff":
            fn = self.tiff_image_path / f"image_{self.offset}.tiff"
            img, h = self.ctrl.getImage(exposure_time / 5)
            write_tiff(fn, img, header=h)
            ctrl.mode_diffraction()
            time.sleep(1.0)  # add some delay to account for beam lag

        ctrl.cam.block()
        # for i, a in enumerate(tilt_positions):
        for i, angle in enumerate(tqdm.tqdm(tilt_positions)):
            ctrl.stageposition.a = angle

            j = i + self.offset

            img, h = self.ctrl.getImage(exposure_time)

            self.buffer.append((j, img, h))

        self.offset += len(tilt_positions)
        self.nframes = j

        self.end_angle = end_angle = ctrl.stageposition.a

        ctrl.cam.unblock()

        self.camera_length = camera_length = int(self.ctrl.magnification.get())
        self.stepsize = stepsize
        self.exposure_time = exposure_time

        with open(self.path / "summary.txt", "a") as f:
            print(f"{self.now}: Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree in {len(tilt_positions)} frames.", file=f)
            print(f"Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree in {len(tilt_positions)} frames.")

        self.logger.info("Data collected from {start_angle:.2f} degree to {end_angle:.2f} degree (camera length: {camera_length} mm).")
        
        self.current_angle = angle
        print(f"Done, current angle = {self.current_angle:.2f} degrees")

        if image_mode != "diff":
            ctrl.mode = image_mode

    def finalize(self):
        """Finalize data collection after `self.start_collection` has been run.
        Write data in `self.buffer` to path given by `self.path`.
        """
        self.logger.info(f"Data saving path: {self.path}")
        self.rotation_axis = config.camera.camera_rotation_vs_stage_xy

        self.pixelsize = config.calibration.pixelsize_diff[camera_length] # px / Angstrom
        self.physical_pixelsize = config.camera.physical_pixelsize # mm
        self.wavelength = config.microscope.wavelength # angstrom
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        with open(self.path / "summary.txt", "a") as f:
            print(f"Rotation range: {self.end_angle-self.start_angle:.2f} degrees", file=f)
            print(f"Exposure Time: {self.exposure_time:.3f} s", file=f)
            print(f"Spot Size: {self.spotsize}", file=f)
            print(f"Camera length: {self.camera_length} mm", file=f)
            print(f"Pixelsize: {self.pixelsize} px/Angstrom", file=f)
            print(f"Physical pixelsize: {self.physical_pixelsize} um", file=f)
            print(f"Wavelength: {self.wavelength} Angstrom", file=f)
            print(f"Stretch amplitude: {self.stretch_azimuth} %", file=f)
            print(f"Stretch azimuth: {self.stretch_amplitude} degrees", file=f)
            print(f"Rotation axis: {self.rotation_axis} radians", file=f)
            print(f"Stepsize: {self.stepsize:.4f} degrees", file=f)
            print(f"Number of frames: {self.nframes}", file=f)

        img_conv = ImgConversion(buffer=buffer, 
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
                 stretch_azimuth=self.stretch_azimuth
                 )

        print("Writing data files...")
        img_conv.threadpoolwriter(tiff_path=self.tiff_path,
                                  mrc_path=self.mrc_path,
                                  workers=8)
        
        print("Writing input files...")
        img_conv.write_ed3d(self.mrc_path)
        img_conv.write_pets_inp(self.path)

        img_conv.write_beam_centers(self.path)

        print("Data Collection and Conversion Done.")
        print()

        return True


def main():
    from instamatic import TEMController
    ctrl = TEMController.initialize()

    import logging
    log = logging.getLogger(__name__)

    exposure_time = 0.5
    tilt_range = 10
    stepsize = 1.0

    i = 1
    while True:
        expdir = f"experiment_{i}"
        if os.path.exists(expdir):
            i += 1
        else:
            break

    print(f"\nData directory: {expdir}")
    
    red_exp = Experiment(ctrl=ctrl, path=expdir, log=log, flatfield=None)
    red_exp.start_collection(exposure_time=exposure_time, tilt_range=tilt_range, stepsize=stepsize)

    input("Press << Enter >> to start the experiment... ")
    
    while not input(f"\nPress << Enter >> to continue for another {tilt_range} degrees. [any key to finalize] ") :
        red_exp.start_collection(exposure_time=exposure_time, tilt_range=tilt_range, stepsize=stepsize)

    red_exp.finalize()


if __name__ == '__main__':
    main()
