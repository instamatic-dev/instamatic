from __future__ import annotations

import datetime
import msvcrt
import pickle
import time
from pathlib import Path

import numpy as np
from pyserialem import read_nav_file
from scipy.interpolate import interp1d

import instamatic
from instamatic import config
from instamatic.experiments.experiment_base import ExperimentBase
from instamatic.formats import write_tiff
from instamatic.tools import get_acquisition_time


class SerialExperiment:
    """Class to handle serial red data acquisition using a TVIPS camera."""

    def __init__(
        self,
        ctrl,
        path: str = None,
        log=None,
        instruction_file: str = None,
        exposure: float = 400,
        mode: str = 'diff',
        target_angle: float = 40,
        rotation_speed=None,
    ):
        super().__init__()

        self.instruction_file = Path(instruction_file)
        self.base_drc = self.instruction_file.parent

        if self.instruction_file.suffix == '.nav':
            self.nav_items = read_nav_file(self.instruction_file, acquire_only=True)
            self.run = self.run_from_nav_file
            self.start_angle = target_angle / 2
            self.end_angle = -self.start_angle
        else:
            self.tracks = open(self.instruction_file).readlines()
            self.run = self.run_from_tracking_file

        self.log = log
        self.path = path
        self.ctrl = ctrl
        self.exposure = exposure
        self.mode = mode
        self.rotation_speed = rotation_speed

    def run(self):
        raise RuntimeError(f'`{self.__class__.__name__}` has not been initialized.')

    def run_from_nav_file(self):
        """Run serial RED on all the coordinates from the `.nav` file."""
        start_angle = self.start_angle
        end_angle = self.end_angle
        path = self.path
        mode = self.mode
        log = self.log
        exposure = self.exposure

        if self.rotation_speed:
            self.ctrl.stage.set_rotation_speed(self.rotation_speed)

        def go_to_first_position(ctrl):
            ctrl.stage.set(a=start_angle)

        def acquire_cred_data(ctrl):
            nonlocal start_angle
            nonlocal end_angle

            tag = ctrl.current_item.tag
            out_path = path / tag

            out_path.mkdir(exist_ok=True, parents=True)

            print()
            print(f'Data directory: {out_path}')
            print(f'Rotating from {start_angle} to {end_angle} degrees')
            print(ctrl.stage)

            exp = Experiment(ctrl, path=out_path, log=log, exposure=exposure, mode=mode)
            exp.get_ready()
            exp.start_collection(target_angle=end_angle, start_angle=start_angle)

            start_angle, end_angle = end_angle, start_angle

        def stop_liveview(ctrl):
            ctrl.cam.stop_liveview()

        self.ctrl.acquire_at_items(
            self.nav_items,
            acquire=acquire_cred_data,
            pre_acquire=go_to_first_position,
            post_acquire=stop_liveview,
        )

        if self.rotation_speed:
            self.ctrl.stage.set_rotation_speed(12)

    def run_from_tracking_file(self):
        t0 = time.perf_counter()
        n_measured = 0

        n_items = len(self.tracks)

        for i, track in enumerate(self.tracks):
            track = track.strip()
            if not track:
                continue

            track = self.base_drc / track
            name = track.name
            stem = track.stem

            out_path = self.path / stem
            out_path.mkdir(exist_ok=True, parents=True)

            print()
            print(f'({i} / {n_items}) Acquiring track: {stem}')
            print(f'Track file: {self.base_drc / name}')
            print(f'Data directory: {out_path}')
            print(self.ctrl.stage)
            print()

            exp = Experiment(
                self.ctrl,
                path=out_path,
                log=self.log,
                track=track,
                exposure=self.exposure,
                mode=self.mode,
            )

            exp.get_ready()

            try:
                exp.start_collection(target_angle=0)
            except InterruptedError:
                self.ctrl.cam.stop_liveview()
                break
            finally:
                del exp

            n_measured += 1

            time.sleep(3)

        t1 = time.perf_counter()
        dt = t1 - t0
        print(f'Serial experiment finished -> {n_measured} crystals measured')
        print(f'Time taken: {dt:.1f} s, {dt / n_measured:.1f} s/crystal')
        print(f'Data directory: {self.path}')


class Experiment(ExperimentBase):
    """Class to control data collection through EMMenu to collect continuous
    rotation electron diffraction data.

    ctrl: `TEMController`
        Instance of instamatic.controller.TEMController
    path: str
        `str` or `pathlib.Path` object giving the path to save data at
    log: `logging.Logger`
        Instance of `logging.Logger`
    exposure: float
        Exposure time in ms
    mode: str
    """

    def __init__(
        self,
        ctrl,
        path: str = None,
        log=None,
        track: str = None,
        exposure: float = 400,
        mode: str = 'diff',
        rotation_speed: int = None,
    ):
        super().__init__()

        self.ctrl = ctrl
        self.emmenu = ctrl.cam
        self.path = Path(path)

        self.exposure = exposure
        self.defocus_offset = 1500

        self.logger = log
        self.mode = mode

        self.rotation_speed = rotation_speed

        if track:
            self.load_tracking_file(track)
            self.track = True
        else:
            self.track = False

    def load_tracking_file(self, trackfile):
        trackfile = Path(trackfile)
        if trackfile.suffix == '.pickle':
            print(f'(autotracking) Loading tracking file: {trackfile}')
            dct = pickle.load(open(trackfile, 'rb'))

            self.track_func = dct['y_offset']
            self.x_offset = dct['x_offset']
            self.start_x = dct['x_center']
            self.start_y = dct['y_center']
            self.start_z = dct['z_pos']

            self.min_angle = dct['angle_min']
            self.max_angle = dct['angle_max']

            self.crystal_number = dct['i']

            self.trackfile = trackfile

            self.track_interval = 2
            self.track_relative = False

        else:
            raise OSError("I don't know how to read file `{trackfile}`")

    def prepare_tracking(self):
        if self.track:
            current_angle = self.ctrl.stage.a

            min_angle = self.min_angle
            max_angle = self.max_angle

            # find start angle closest to current angle
            if abs(min_angle - current_angle) > abs(max_angle - current_angle):
                start_angle, target_angle = max_angle, min_angle
            else:
                start_angle, target_angle = min_angle, max_angle

            print(
                f'(autotracking) Overriding angle range: {start_angle:.0f} -> {target_angle:.0f}'
            )

            y_offset = int(self.track_func(start_angle))
            x_offset = self.x_offset

            print(
                f'(autotracking) setting a={start_angle:.0f}, x={self.start_x + x_offset:.0f}, y={self.start_y + y_offset:.0f}, z={self.start_z:.0f}'
            )
            self.ctrl.stage.set_xy_with_backlash_correction(
                x=self.start_x + x_offset, y=self.start_y + y_offset, step=10000
            )
            self.ctrl.stage.set(a=start_angle, z=self.start_z)

            return start_angle, target_angle

    def track_crystal(self, n, angle):
        # tracking routine
        if n % self.track_interval == 0:
            target_y = self.start_y + int(self.track_func(angle))
            self.ctrl.stage.set(y=target_y, wait=False)
            print(f'(autotracking) set y={target_y:.0f}')

    def get_ready(self):
        self.emmenu.stop_liveview()  # just in case

        try:
            # next 2 lines are a workaround for EMMENU 5.0.9.0 bugs, FIXME later
            self.emmenu.set_autoincrement(False)
            self.emmenu.set_image_index(0)
        except Exception as e:
            print(e)

        self.emmenu.set_exposure(self.exposure)

        if not self.ctrl.beam.is_blanked:
            self.ctrl.beam.blank()

        self.ctrl.screen.up()

        if self.ctrl.mode != self.mode:
            print(f'Switching to {self.mode} mode')
            self.ctrl.mode.set(self.mode)

        if self.mode == 'diff':
            self.ctrl.difffocus.refocus()

        self.emmenu.start_liveview()

        print('Ready...')

    def setup(self):
        self.get_ready()

    def manual_activation(self) -> float:
        ACTIVATION_THRESHOLD = 0.2

        print('Waiting for rotation to start...', end=' ')
        a0 = a = self.ctrl.stage.a
        while abs(a - a0) < ACTIVATION_THRESHOLD:
            a = self.ctrl.stage.a

        print('Rotation started...')

        return a

    def start_collection(
        self, target_angle: float, start_angle: float = None, manual_control: bool = False
    ):
        """manual_control : bool Control the rotation using the buttons or
        pedals."""
        angle_tolerance = 0.5  # degrees

        self.now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.stage_positions = []
        interval = 0.7  # interval at which it check for rotation to end / does tracking

        if self.track:
            start_angle, target_angle = self.prepare_tracking()

        if start_angle:
            print(f'Going to starting angle: {start_angle:.1f}')
            self.ctrl.stage.a = start_angle

        self.start_position = self.ctrl.stage.get()
        start_angle = self.start_position.a

        if self.track:
            # Center crystal position
            if self.mode == 'diff':
                self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beam.unblank()

            input('Move SAED aperture to crystal and press <ENTER> to measure! ')

            # cannot do this while lieview is running
            # img1 = self.ctrl.get_rotated_image()
            # write_tiff(self.path / "image_before.tiff", img1)

            self.ctrl.beam.blank()
            if self.mode == 'diff':
                self.ctrl.difffocus.refocus()
            time.sleep(3)

        self.ctrl.beam.unblank(
            delay=0.2
        )  # give the beamblank some time to dissappear to avoid weak first frame

        # with autoincrement(False), otherwise use `get_next_empty_image_index()`
        # start_index is set to 1, because EMMENU always takes a single image (0) when liveview is activated
        start_index = 1
        # start_index = self.emmenu.get_next_empty_image_index()

        if manual_control:
            start_angle = self.manual_activation()
            last_angle = 999
        elif self.rotation_speed:
            self.ctrl.stage.set_a_with_speed(
                a=target_angle, speed=self.rotation_speed, wait=False
            )
        else:
            self.ctrl.stage.set(a=target_angle, wait=False)

        self.emmenu.start_record()  # start recording

        t0 = time.perf_counter()
        t_delta = t0

        n = 0

        print('Acquiring data...')

        while True:
            t = time.perf_counter()

            if not manual_control:
                if abs(self.ctrl.stage.a - target_angle) < angle_tolerance:
                    print('Target angle reached!')
                    break

            if t - t_delta > interval:
                n += 1
                x, y, z, a, _ = pos = self.ctrl.stage.get()
                self.stage_positions.append((t, pos))
                t_delta = t
                # print(t, pos)

                if manual_control:
                    current_angle = a
                    if last_angle == current_angle:
                        print(
                            f'Manual rotation was interrupted (current: {current_angle:.2f} | last {last_angle:.2f})'
                        )
                        break
                    last_angle = current_angle

                    print(f' >> Current angle: {a:.2f}', end='      \r')

                if self.track:
                    self.track_crystal(n=n, angle=a)

            # Stop/interrupt and go to next crystal
            if msvcrt.kbhit():
                key = msvcrt.getch().decode()
                if key == ' ':
                    print('Stopping the stage!')
                    self.ctrl.stage.stop()
                    break
                if key == 'q':
                    self.ctrl.stage.stop()
                    raise InterruptedError('Data collection was interrupted!')

        t1 = time.perf_counter()
        self.emmenu.stop_liveview()

        if self.ctrl.beam.is_blanked:
            self.ctrl.beam.blank()

        self.end_position = self.ctrl.stage.get()
        end_angle = self.end_position.a

        end_index = self.emmenu.get_image_index()

        self.t_start = t0
        self.t_end = t1
        self.total_time = t1 - t0

        self.nframes = nframes = end_index - start_index + 1
        if nframes < 1:
            print('No frames measured??')
            return

        self.osc_angle = abs(end_angle - start_angle) / nframes

        # acquisition_time = total_time / nframes
        self.total_angle = abs(end_angle - start_angle)
        self.rotation_axis = config.camera.camera_rotation_vs_stage_xy
        self.camera_length = int(self.ctrl.magnification.get())
        self.spotsize = self.ctrl.spotsize
        self.rotation_speed = (end_angle - start_angle) / self.total_time
        self.exposure_time = self.emmenu.get_exposure()
        self.start_angle, self.end_angle = start_angle, end_angle

        try:
            # sometimes breaks with:
            # AttributeError: 'NoneType' object has no attribute 'EMVector'
            timestamps = self.emmenu.get_timestamps(start_index, end_index)
        except AttributeError as e:
            print(e)
            print(f'Timestamps from {start_index} to {end_index}')
            timestamps = [1, 2, 3, 4, 5]  # just to make it work

        self.timings = get_acquisition_time(
            timestamps, exp_time=self.exposure_time, savefig=True, drc=self.path
        )

        self.log_end_status()
        self.log_stage_positions()

        print('Writing data files...')
        path_data = self.path / 'tiff'
        path_data.mkdir(exist_ok=True, parents=True)

        self.emmenu.write_tiffs(start_index, end_index, path=path_data)

        if self.track:
            # Center crystal position
            if self.mode == 'diff':
                self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beam.unblank()

            img2 = self.ctrl.get_rotated_image()
            write_tiff(self.path / 'image_after.tiff', img2)

            self.ctrl.beam.blank()
            if self.mode == 'diff':
                self.ctrl.difffocus.refocus()

        print(f'Wrote {nframes} images (#{start_index}->#{end_index}) to {path_data}')

        if self.track:
            print(f'Done with this crystal (number #{self.crystal_number})!')
        else:
            print('Done with this crystal!')

    def log_end_status(self):
        wavelength = config.microscope.wavelength

        try:
            pixelsize = config.calibration['diff']['pixelsize'][
                self.camera_length
            ]  # px / Angstrom
        except KeyError:
            print(
                f'Warning: No such camera length: {self.camera_length} in diff calibration, defaulting to 1.0'
            )
            pixelsize = 1.0

        physical_pixelsize = config.camera.physical_pixelsize  # mm

        binning = self.emmenu.get_binning()
        image_dimensions_x, image_dimensions_y = self.emmenu.get_image_dimensions()
        camera_dimensions_x, camera_dimensions_y = self.emmenu.get_camera_dimensions()

        pixelsize *= binning
        physical_pixelsize *= binning

        print(
            f'\nRotated {self.total_angle:.2f} degrees from {self.start_angle:.2f} to {self.end_angle:.2f}'
        )
        print(
            'Start stage position:  X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}'.format(
                *self.start_position
            )
        )
        print(
            'End stage position:    X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}'.format(
                *self.end_position
            )
        )
        print(f'Data collection camera length: {self.camera_length} cm')
        print(f'Data collection spot size: {self.spotsize}')
        print(f'Rotation speed: {self.rotation_speed:.3f} degrees/s')

        with open(self.path / 'cRED_log.txt', 'w') as f:
            print(
                f'Program: {instamatic.__long_title__} + EMMenu {self.emmenu.get_emmenu_version()}',
                file=f,
            )
            print(f'Camera: {config.camera.name}', file=f)
            print(f'Microscope: {config.microscope.name}', file=f)
            print(f'Camera type: {self.emmenu.get_camera_type()}', file=f)
            print(f'Camera config: {self.emmenu.get_current_config_name()}', file=f)
            print(f'Mode: {self.mode}', file=f)
            print(f'Data Collection Time: {self.now}', file=f)
            print(f'Time Period Start: {self.t_start}', file=f)
            print(f'Time Period End: {self.t_end}', file=f)
            print(f'Number of frames: {self.nframes}', file=f)
            print(f'Starting angle: {self.start_angle:.2f} degrees', file=f)
            print(f'Ending angle: {self.end_angle:.2f} degrees', file=f)
            print(f'Rotation range: {self.end_angle - self.start_angle:.2f} degrees', file=f)
            print(f'Rotation speed: {self.rotation_speed:.3f} degrees/s', file=f)
            print(f'Exposure Time: {self.timings.exposure_time:.3f} s', file=f)
            print(f'Acquisition time: {self.timings.acquisition_time:.3f} s', file=f)
            print(f'Overhead time: {self.timings.overhead:.3f} s', file=f)
            print(f'Total time: {self.total_time:.3f} s', file=f)
            print(f'Wavelength: {wavelength} Angstrom', file=f)
            print(f'Spot Size: {self.spotsize}', file=f)
            print(f'Camera length: {self.camera_length} cm', file=f)
            print(f'Pixelsize: {pixelsize} px/Angstrom', file=f)
            print(f'Physical pixelsize: {physical_pixelsize} um', file=f)
            print(f'Binning: {binning}', file=f)
            print(f'Image dimensions: {image_dimensions_x} {image_dimensions_y}', file=f)
            print(f'Camera dimensions: {camera_dimensions_x} {camera_dimensions_y}', file=f)
            print(f'Stretch amplitude: {config.camera.stretch_azimuth} %', file=f)
            print(f'Stretch azimuth: {config.camera.stretch_amplitude} degrees', file=f)
            print(f'Rotation axis: {self.rotation_axis} radians', file=f)
            print(f'Oscillation angle: {self.osc_angle:.4f} degrees', file=f)
            print(
                'Stage start: X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:8.2f} | B {:8.2f}'.format(
                    *self.start_position
                ),
                file=f,
            )
            print('Beam stopper: yes', file=f)

            if self.track:
                print()
                print(f'Crystal number: {self.crystal_number}', file=f)
                print(f'Tracking data: {self.trackfile}', file=f)
                print(f'Tracking between {self.min_angle} and {self.max_angle}', file=f)

            print('', file=f)

        print(f'Wrote file {f.name}')

    def log_stage_positions(self):
        fn = 'stage_positions(tracked).txt' if self.track else 'stage_positions.txt'
        with open(self.path / fn, 'w') as f:
            print('# timestamp x y z a b', file=f)
            for t, (x, y, z, a, b) in self.stage_positions:
                print(t, x, y, z, a, b, file=f)

        print(f'Wrote file {f.name}')

        if self.mode != 'diff':
            if len(self.stage_positions) < 3:
                print('Not enough stage positions for interpolation')
            else:
                pos = np.array([p[1] for p in self.stage_positions])  # (t, (x y z a b))
                idx = np.argmin(np.abs(pos[:, 3]))
                x_center = pos[:, 0].mean()
                y_center = pos[idx, 1]
                z_pos = pos[0:, 2].mean()
                f = interp1d(
                    pos[:, 3], pos[:, 1] - y_center, fill_value='extrapolate', kind='quadratic'
                )

                d = {}
                d['y_offset'] = f
                d['x_offset'] = 0
                d['x_center'] = x_center
                d['y_center'] = y_center
                d['z_pos'] = z_pos

                d['angle_min'] = self.start_angle
                d['angle_max'] = self.end_angle

                d['i'] = 0

                fn = self.path / 'track.pickle'
                pickle.dump(d, open(fn, 'wb'))

                print(f'Wrote file {fn.name}')


if __name__ == '__main__':
    from instamatic import controller
    from instamatic.io import get_new_work_subdirectory

    ctrl = controller.initialize()

    expdir = get_new_work_subdirectory()
    expdir.mkdir(exist_ok=True, parents=True)

    exp = Experiment(ctrl, path=expdir)
    exp.get_ready()
    exp.run(target_angle=20)
