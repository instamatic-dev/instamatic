import datetime
import time
from instamatic import config, version
from pathlib import Path
from instamatic.tools import get_acquisition_time


class Experiment(object):
    """Class to control data collection through EMMenu to collect
    continuous rotation electron diffraction data

    ctrl:
        Instance of instamatic.TEMController.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Instance of `logging.Logger`
    """
    def __init__(self, ctrl, path: str=None, log=None, track=None, obtain_track=False, track_relative=True):
        super().__init__()

        self.ctrl = ctrl
        self.emmenu = ctrl.cam
        self.path = Path(path)

        self.logger = log
        
        self.obtain_track = obtain_track  # do not go to diff mode to measure crystal track

        self.track = False
        if track and track.endswith(".txt"):
            from scipy.interpolate import interp1d
            import numpy as np
            arr = np.loadtxt(track)
            track_a = arr[:,4]
            track_y = arr[:,2]
            print(f"(autotracking) Loading tracking file: {track}")
            print(f"(autotracking) Interpolating a={track_a.min():.1f} -> a={track_a.max():.1f} (+extrapolated)")
            self.track = True
            self.track_interval = 2
            self.track_func = interp1d(track_a, track_y, fill_value="extrapolate")
            self.track_relative = track_relative
            self.track_routine = 1
        elif track and track.endswith(".pickle"):
            import pickle
            print(f"(autotracking) Loading tracking file: {track}")
            dct = pickle.load(open(track, "rb"))

            self.track_func = dct["y_offset"]
            self.x_offset = dct["x_offset"]
            self.start_x = dct["x_center"]
            self.start_y = dct["y_center"]
            self.start_z = dct["z_pos"]
            self.start_angle = dct["angle_min"]
            self.target_angle = dct["angle_max"]

            self.track = True
            self.track_interval = 2
            self.track_relative = False
            self.track_routine = 2

        elif track:
            raise IOError("I don't know how to read file `{track}`")

    def get_ready(self):
        # next 2 lines are a workaround for EMMENU 5.0.9.0 bugs, FIXME later
        self.emmenu.set_autoincrement(False)
        self.emmenu.set_image_index(0)

        if not self.obtain_track:
            self.ctrl.beamblank_on()
            self.ctrl.screen_up()
    
            if self.ctrl.mode != 'diff':
                print("Switching to diffraction mode")
                self.ctrl.mode = 'diff'
        
            spotsize = self.ctrl.spotsize
            if spotsize not in (4, 5):
                print(f"Spotsize is quite high ({spotsize}), maybe you want to lower it?")
    
            self.emmenu.start_liveview()

    def start_collection(self, target_angle: float):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.track and self.track_routine == 2:
            target_angle = self.target_angle
            start_angle = self.start_angle

            y_offset = int(self.track_func(start_angle))
            x_offset = self.x_offset

            print(f"(autotracking) setting a={start_angle:.0f}, x={self.start_x+x_offset:.0f}, y={self.start_y+y_offset:.0f}, z={self.start_z:.0f}")
            self.ctrl.stageposition.set(a=self.start_angle, x=self.start_x+x_offset, y=self.start_y+y_offset, z=self.start_z)
            print(f"(autotracking) Overriding angle range: {self.start_angle:.0f} -> {target_angle:.0f}")

        self.stage_positions = []
        interval = 1.0

        start_position = self.ctrl.stageposition.get()
        start_angle = start_position.a

        self.ctrl.beamblank_off()

        # with autoincrement(False), otherwise use `get_next_empty_image_index()`
        # start_index is set to 1, because EMMENU always takes a single image (0) when liveview is activated
        start_index = 1
        # start_index = self.emmenu.get_next_empty_image_index()

        self.ctrl.stageposition.set(a=target_angle, wait=False)

        if not self.obtain_track:
            self.emmenu.start_record()  # start recording

        t0 = time.perf_counter()
        t_delta = t0       

        n = 0
        
        while self.ctrl.stageposition.is_moving():
            t = time.perf_counter()
            if t - t_delta > interval:
                n += 1
                x, y, z, a, _ = pos = self.ctrl.stageposition.get()
                self.stage_positions.append((t, pos))
                t_delta = t
                # print(t, pos)

                # tracking routine
                if self.track and (n % self.track_interval == 0):
                    target_y = start_position.y - int(self.track_func(a))
                    self.ctrl.stageposition.set(y=target_y, wait=False)
                    print(f"Tracking -> set y={target_y}")

        t1 = time.perf_counter()

        end_position = self.ctrl.stageposition.get()
        end_angle = end_position.a

        if not self.obtain_track:
            self.ctrl.beamblank_on()
            self.emmenu.stop_liveview()  # end liveview and stop recording
        
        end_index = self.emmenu.get_image_index()

        t_start = t0
        t_end = t1
        total_time = t1 - t0
        
        nframes = end_index - start_index

        osc_angle = abs(end_angle - start_angle) / nframes
        
        # acquisition_time = total_time / nframes
        total_angle = abs(end_angle - start_angle)
        rotation_axis = config.camera.camera_rotation_vs_stage_xy

        camera_length = int(self.ctrl.magnification.get())

        spotsize = self.ctrl.spotsize

        rotation_speed = (end_angle-start_angle) / total_time

        exposure_time = self.emmenu.get_exposure()
        
        if not self.obtain_track:
            timestamps = self.emmenu.get_timestamps(start_index, end_index)
            acq_out = self.path / "acquisition_time.png"
            timings = get_acquisition_time(timestamps, exp_time=exposure_time, savefig=True, fn=acq_out, plot=False)

        print(f"\nRotated {total_angle:.2f} degrees from {start_angle:.2f} to {end_angle:.2f}")
        print("Start stage position:  X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*start_position))
        print("End stage position:    X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*end_position))
        print(f"Data collection camera length: {camera_length} cm")
        print(f"Data collection spot size: {spotsize}")
        print(f"Rotation speed: {rotation_speed:.3f} degrees/s")

        pixelsize = config.calibration.pixelsize_diff[camera_length] # px / Angstrom
        physical_pixelsize = config.camera.physical_pixelsize # mm
        
        binX, binY = self.emmenu.getBinning()

        pixelsize *= binX
        physical_pixelsize *= binX

        wavelength = config.microscope.wavelength

        with open(self.path / "cRED_log.txt", "w") as f:
            print(f"Program: {version.__long_title__} + EMMenu 4.0", file=f)
            print(f"Camera: {config.camera.name}", file=f)
            print(f"Microscope: {config.microscope.name}", file=f)
            print(f"Data Collection Time: {now}", file=f)
            print(f"Time Period Start: {t_start}", file=f)
            print(f"Time Period End: {t_end}", file=f)
            print(f"Starting angle: {start_angle:.2f} degrees", file=f)
            print(f"Ending angle: {end_angle:.2f} degrees", file=f)
            print(f"Rotation range: {end_angle-start_angle:.2f} degrees", file=f)
            print(f"Rotation speed: {rotation_speed:.3f} degrees/s", file=f)
            if not self.obtain_track:
                print(f"Exposure Time: {timings.exposure_time:.3f} s", file=f)
                print(f"Acquisition time: {timings.acquisition_time:.3f} s", file=f)
                print(f"Overhead time: {timings.overhead:.3f} s", file=f)
            print(f"Total time: {total_time:.3f} s", file=f)
            print(f"Wavelength: {wavelength} Angstrom", file=f)
            print(f"Spot Size: {spotsize}", file=f)
            print(f"Camera length: {camera_length} cm", file=f)
            print(f"Rotation axis: {rotation_axis} radians", file=f)
            print(f"Oscillation angle: {osc_angle:.4f} degrees", file=f)
            print("Stage start: X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:8.2f} | B {:8.2f}".format(*start_position), file=f)
            print("Beam stopper: yes", file=f)
            print("", file=f)

        print(f"Wrote file {f.name}")

        fn = "stage_positions(tracked).txt" if self.track else "stage_positions.txt"
        with open(self.path / fn, "w") as f:
            print("# timestamp x y z a b", file=f)
            for t, (x, y, z, a, b) in self.stage_positions:
                print(t, x, y, z, a, b, file=f)

        print(f"Wrote file {f.name}")

        if self.obtain_track:
            return

        print("Writing data files...")
        path_data = self.path / "tiff"
        path_data.mkdir(exist_ok=True, parents=True)

        self.emmenu.writeTiffs(start_index, end_index, path=path_data)

        print(f"Wrote {nframes} images to {path_data}")


if __name__ == '__main__':
    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)
    
    start_experiment(ctrl=ctrl, path=expdir)
