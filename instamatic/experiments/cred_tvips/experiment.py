import datetime
import time
from instamatic import config, version
from pathlib import Path
from instamatic.tools import get_acquisition_time
import time
from instamatic.formats import write_tiff


class SerialExperiment(object):
    """docstring for SerialExperiment"""
    def __init__(self, ctrl, path: str=None, log=None, tracking_file=None, exposure=None):
        super().__init__()
        
        self.tracking_file = Path(tracking_file)
        self.tracking_base_drc = self.tracking_file.parent
        self.tracks = open(tracking_file, "r")
        self.log = log
        self.path = path
        self.ctrl = ctrl
        self.exposure = exposure

    def run(self):
        t0 = time.clock()
        n_measured = 0

        for track in self.tracks:
            track = track.strip()
            if not track:
                continue

            track = self.tracking_base_drc / track
            name = track.name
            stem = track.stem

            out_path = self.path / stem
            out_path.mkdir(exist_ok=True, parents=True)

            print()
            print(f"Track: {stem}")
            print(f"Track file: {self.tracking_base_drc / name}")
            print(f"Data directory: {out_path}")
            print()

            exp = Experiment(self.ctrl, path=out_path, log=self.log, track=track, obtain_track=False, exposure=self.exposure)

            exp.get_ready()

            exp.start_collection(target_angle=0)

            n_measured += 1

            print("--")
            time.sleep(3)

        t1 = time.clock()
        dt = t1 - t0
        print("Serial experiment finished")
        print(f"Time taken: {dt:.1f} s, {dt/n_measured:.1f} s/crystal")


class Experiment(object):
    """Class to control data collection through EMMenu to collect
    continuous rotation electron diffraction data

    ctrl:
        Instance of instamatic.TEMController.TEMController
    path:
        `str` or `pathlib.Path` object giving the path to save data at
    log:
        Instance of `logging.Logger`
    exposure:
        Exposure time in ms
    """
    def __init__(self, ctrl, path: str=None, log=None, track=None, obtain_track=False, track_relative=True, exposure=400):
        super().__init__()

        self.ctrl = ctrl
        self.emmenu = ctrl.cam
        self.path = Path(path)

        self.exposure = exposure
        self.defocus_offset = 1500

        self.logger = log
        
        self.obtain_track = obtain_track  # do not go to diff mode to measure crystal track

        if track:
            track = Path(track)
            self.track = True
        else:
            self.track_routine = 0
            self.track = False
        
        if self.track and track.suffix == ".txt":
            from scipy.interpolate import interp1d
            import numpy as np
            arr = np.loadtxt(track)
            track_a = arr[:,4]
            track_y = arr[:,2]
            print(f"(autotracking) Loading tracking file: {track}")
            print(f"(autotracking) Interpolating a={track_a.min():.1f} -> a={track_a.max():.1f} (+extrapolated)")
            self.track_interval = 2
            self.track_func = interp1d(track_a, track_y, fill_value="extrapolate")
            self.track_relative = track_relative
            self.track_routine = 1
        elif self.track and track.suffix == ".pickle":
            import pickle
            print(f"(autotracking) Loading tracking file: {track}")
            dct = pickle.load(open(track, "rb"))

            self.track_func = dct["y_offset"]
            self.x_offset = dct["x_offset"]
            self.start_x = dct["x_center"]
            self.start_y = dct["y_center"]
            self.start_z = dct["z_pos"]

            self.min_angle = dct["angle_min"]
            self.max_angle = dct["angle_max"]

            self.track_interval = 2
            self.track_relative = False
            self.track_routine = 2

        elif self.track:
            raise IOError("I don't know how to read file `{track}`")

    def get_ready(self):
        # next 2 lines are a workaround for EMMENU 5.0.9.0 bugs, FIXME later
        try:
            self.emmenu.set_autoincrement(False)
            self.emmenu.set_image_index(0)
        except Exception as e:
            print(e)

        self.emmenu.set_exposure(self.exposure)

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
            current_angle = self.ctrl.stageposition.a

            min_angle = self.min_angle
            max_angle = self.max_angle

            # find start angle closest to current angle
            if abs(min_angle - current_angle) > abs(max_angle - current_angle):
                start_angle, target_angle = max_angle, min_angle
            else:
                start_angle, target_angle = min_angle, max_angle

            print(f"(autotracking) Overriding angle range: {start_angle:.0f} -> {target_angle:.0f}")
            
            y_offset = int(self.track_func(start_angle))
            x_offset = self.x_offset

            print(f"(autotracking) setting a={start_angle:.0f}, x={self.start_x+x_offset:.0f}, y={self.start_y+y_offset:.0f}, z={self.start_z:.0f}")
            self.ctrl.stageposition.set(a=start_angle, x=self.start_x+x_offset, y=self.start_y+y_offset, z=self.start_z)

        self.stage_positions = []
        interval = 1.0

        start_position = self.ctrl.stageposition.get()
        start_angle = start_position.a

        if self.track_routine == 2:
            ### Center crystal position
            self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beamblank_off()
    
            input("Center aperture and press <ENTER> to measure crystal ")

            ## cannot do this while lieview is running
            # img1 = self.ctrl.getRawImage()
            # write_tiff(self.path / "image_before.tiff", img1)

            self.ctrl.beamblank_on()
            self.ctrl.difffocus.refocus()
            time.sleep(3)
        
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
                    target_y = self.start_y + int(self.track_func(a))
                    self.ctrl.stageposition.set(y=target_y, wait=False)
                    print(f"Tracking -> set y={target_y:.0f}")

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
            timings = get_acquisition_time(timestamps, exp_time=exposure_time, savefig=True, fn=acq_out)

        print(f"\nRotated {total_angle:.2f} degrees from {start_angle:.2f} to {end_angle:.2f}")
        print("Start stage position:  X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*start_position))
        print("End stage position:    X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*end_position))
        print(f"Data collection camera length: {camera_length} cm")
        print(f"Data collection spot size: {spotsize}")
        print(f"Rotation speed: {rotation_speed:.3f} degrees/s")

        try:
            pixelsize = config.calibration.pixelsize_diff[camera_length] # px / Angstrom
        except KeyError:
            print(f"Warning: No such camera length: {camera_length} in diff calibration, defaulting to 1.0")
            pixelsize = 1.0

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

        if self.track_routine == 2:
            ### Center crystal position
            self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beamblank_off()
    
            img2 = self.ctrl.getRawImage()
            write_tiff(self.path / "image_after.tiff", img2)
    
            self.ctrl.beamblank_on()
            self.ctrl.difffocus.refocus()

        print(f"Wrote {nframes} images to {path_data}")


if __name__ == '__main__':
    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)
    
    start_experiment(ctrl=ctrl, path=expdir)
