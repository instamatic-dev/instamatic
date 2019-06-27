import datetime
import time
from instamatic import config, version
from pathlib import Path
from instamatic.tools import get_acquisition_time
import time
from instamatic.formats import write_tiff
import numpy as np
from scipy.interpolate import interp1d
import pickle



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

            exp = Experiment(self.ctrl, path=out_path, log=self.log, track=track, exposure=self.exposure)

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
    def __init__(self, ctrl, path: str=None, log=None, track=None, exposure=400, mode="diff"):
        super().__init__()

        self.ctrl = ctrl
        self.emmenu = ctrl.cam
        self.path = Path(path)

        self.exposure = exposure
        self.defocus_offset = 1500

        self.logger = log
        self.mode = mode
        
        if track:
            self.load_tracking_file(track)
            self.track = True
        else:
            self.track = False

    def load_tracking_file(self, trackfile):
        trackfile = Path(trackfile)
        if trackfile.suffix == ".pickle":
            print(f"(autotracking) Loading tracking file: {trackfile}")
            dct = pickle.load(open(trackfile, "rb"))
    
            self.track_func = dct["y_offset"]
            self.x_offset = dct["x_offset"]
            self.start_x = dct["x_center"]
            self.start_y = dct["y_center"]
            self.start_z = dct["z_pos"]
    
            self.min_angle = dct["angle_min"]
            self.max_angle = dct["angle_max"]

            self.crystal_number = dct["i"]

            self.trackfile = trackfile
    
            self.track_interval = 2
            self.track_relative = False
        
        else:
            raise IOError("I don't know how to read file `{trackfile}`")

    def prepare_tracking(self):
        if self.track:
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
            self.ctrl.stageposition.set_xy_with_backlash_correction(x=self.start_x+x_offset, y=self.start_y+y_offset)
            self.ctrl.stageposition.set(a=start_angle, z=self.start_z)

            return start_angle, target_angle

    def track_crystal(self, n, angle):
        # tracking routine
        if (n % self.track_interval == 0):
            target_y = self.start_y + int(self.track_func(angle))
            self.ctrl.stageposition.set(y=target_y, wait=False)
            print(f"(autotracking) set y={target_y:.0f}")

    def get_ready(self):
        # next 2 lines are a workaround for EMMENU 5.0.9.0 bugs, FIXME later
        self.emmenu.stop_liveview()  # just in case

        try:
            self.emmenu.set_autoincrement(False)
            self.emmenu.set_image_index(0)
        except Exception as e:
            print(e)

        self.emmenu.set_exposure(self.exposure)

        self.ctrl.beamblank_on()
        self.ctrl.screen_up()
    
        if self.ctrl.mode != self.mode:
            print(f"Switching to {self.mode} mode")
            self.ctrl.mode = self.mode
        
        spotsize = self.ctrl.spotsize
        if spotsize not in (4, 5):
            print(f"Spotsize is quite high ({spotsize}), maybe you want to lower it?")
    
        self.emmenu.start_liveview()

    def start_collection(self, target_angle: float):
        self.now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.stage_positions = []
        interval = 1.0

        if self.track:
            start_angle, target_angle = self.prepare_tracking()

        self.start_position = self.ctrl.stageposition.get()
        start_angle = self.start_position.a

        if self.track:
            ### Center crystal position
            if self.mode == "diff":
                self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beamblank_off()
    
            input("Move SAED aperture to crystal and press <ENTER> to measure! ")

            ## cannot do this while lieview is running
            # img1 = self.ctrl.getRawImage()
            # write_tiff(self.path / "image_before.tiff", img1)

            self.ctrl.beamblank_on()
            if self.mode == "diff":
                self.ctrl.difffocus.refocus()
            time.sleep(3)
        
        self.ctrl.beamblank_off(delay=0.5)  # give the beamblank some time to dissappear to avoid weak first frame

        # with autoincrement(False), otherwise use `get_next_empty_image_index()`
        # start_index is set to 1, because EMMENU always takes a single image (0) when liveview is activated
        start_index = 1
        # start_index = self.emmenu.get_next_empty_image_index()

        self.ctrl.stageposition.set(a=target_angle, wait=False)
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

                if self.track:
                    self.track_crystal(n=n, angle=a)

        t1 = time.perf_counter()
        self.emmenu.stop_liveview()

        self.end_position = self.ctrl.stageposition.get()
        end_angle = self.end_position.a
        
        end_index = self.emmenu.get_image_index()

        self.t_start = t0
        self.t_end = t1
        self.total_time = t1 - t0
        
        nframes = end_index - start_index

        self.osc_angle = abs(end_angle - start_angle) / nframes
        
        # acquisition_time = total_time / nframes
        self.total_angle = abs(end_angle - start_angle)
        self.rotation_axis = config.camera.camera_rotation_vs_stage_xy
        self.camera_length = int(self.ctrl.magnification.get())
        self.spotsize = self.ctrl.spotsize
        self.rotation_speed = (end_angle-start_angle) / self.total_time
        self.exposure_time = self.emmenu.get_exposure()
        self.start_angle, self.end_angle = start_angle, end_angle
        
        timestamps = self.emmenu.get_timestamps(start_index, end_index)
        acq_out = self.path / "acquisition_time.png"
        self.timings = get_acquisition_time(timestamps, exp_time=self.exposure_time, savefig=True, fn=acq_out)
       
        self.log_end_status()
        self.log_stage_positions()

        print("Writing data files...")
        path_data = self.path / "tiff"
        path_data.mkdir(exist_ok=True, parents=True)

        self.emmenu.writeTiffs(start_index, end_index, path=path_data)

        if self.track:
            ### Center crystal position
            if self.mode == "diff":
                self.ctrl.difffocus.defocus(self.defocus_offset)
            self.ctrl.beamblank_off()
    
            img2 = self.ctrl.getRawImage()
            write_tiff(self.path / "image_after.tiff", img2)
    
            self.ctrl.beamblank_on()
            if self.mode == "diff":
                self.ctrl.difffocus.refocus()

        print(f"Wrote {nframes} images to {path_data}")
        
        if self.track:
            print(f"Done with this crystal (number #{self.crystal_number})!")
        else:
            print("Done with this crystal!")

    def log_end_status(self):
        wavelength = config.microscope.wavelength

        try:
            pixelsize = config.calibration.pixelsize_diff[self.camera_length] # px / Angstrom
        except KeyError:
            print(f"Warning: No such camera length: {self.camera_length} in diff calibration, defaulting to 1.0")
            pixelsize = 1.0

        physical_pixelsize = config.camera.physical_pixelsize # mm
        
        bin_x, bin_y = self.emmenu.getBinning()
        image_dimensions_x, image_dimensions_y = self.emmenu.getImageDimensions()
        camera_dimensions_x, camera_dimensions_y = self.emmenu.getCameraDimensions()

        pixelsize *= bin_x
        physical_pixelsize *= bin_x

        print(f"\nRotated {self.total_angle:.2f} degrees from {self.start_angle:.2f} to {self.end_angle:.2f}")
        print("Start stage position:  X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*self.start_position))
        print("End stage position:    X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*self.end_position))
        print(f"Data collection camera length: {self.camera_length} cm")
        print(f"Data collection spot size: {self.spotsize}")
        print(f"Rotation speed: {self.rotation_speed:.3f} degrees/s")

        with open(self.path / "cRED_log.txt", "w") as f:
            print(f"Program: {version.__long_title__} + EMMenu {self.emmenu.getEMMenuVersion()}", file=f)
            print(f"Camera: {config.camera.name}", file=f)
            print(f"Microscope: {config.microscope.name}", file=f)
            print(f"Camera type: {self.emmenu.getCameraType()}", file=f)
            print(f"Camera config: {self.emmenu.getCurrentConfigName()}", file=f)
            print(f"Mode: {self.mode}", file=f)
            print(f"Data Collection Time: {self.now}", file=f)
            print(f"Time Period Start: {self.t_start}", file=f)
            print(f"Time Period End: {self.t_end}", file=f)
            print(f"Starting angle: {self.start_angle:.2f} degrees", file=f)
            print(f"Ending angle: {self.end_angle:.2f} degrees", file=f)
            print(f"Rotation range: {self.end_angle-self.start_angle:.2f} degrees", file=f)
            print(f"Rotation speed: {self.rotation_speed:.3f} degrees/s", file=f)
            print(f"Exposure Time: {self.timings.exposure_time:.3f} s", file=f)
            print(f"Acquisition time: {self.timings.acquisition_time:.3f} s", file=f)
            print(f"Overhead time: {self.timings.overhead:.3f} s", file=f)
            print(f"Total time: {self.total_time:.3f} s", file=f)
            print(f"Wavelength: {wavelength} Angstrom", file=f)
            print(f"Spot Size: {self.spotsize}", file=f)
            print(f"Camera length: {self.camera_length} cm", file=f)
            print(f"Pixelsize: {pixelsize} px/Angstrom", file=f)
            print(f"Physical pixelsize: {physical_pixelsize} um", file=f)
            print(f"Binning: {bin_x} {bin_y}", file=f)
            print(f"Image dimensions: {image_dimensions_x} {image_dimensions_y}", file=f)
            print(f"Camera dimensions: {camera_dimensions_x} {camera_dimensions_y}", file=f)
            print(f"Stretch amplitude: {config.camera.stretch_azimuth} %", file=f)
            print(f"Stretch azimuth: {config.camera.stretch_amplitude} degrees", file=f)
            print(f"Rotation axis: {self.rotation_axis} radians", file=f)
            print(f"Oscillation angle: {self.osc_angle:.4f} degrees", file=f)
            print("Stage start: X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:8.2f} | B {:8.2f}".format(*self.start_position), file=f)
            print("Beam stopper: yes", file=f)

            if self.track:
                print()
                print(f"Crystal number: {self.crystal_number}", file=f)
                print(f"Tracking data: {self.trackfile}", file=f)
                print(f"Tracking between {self.min_angle} and {self.max_angle}", file=f)

            print("", file=f)

        print(f"Wrote file {f.name}")

    def log_stage_positions(self):
        fn = "stage_positions(tracked).txt" if self.track else "stage_positions.txt"
        with open(self.path / fn, "w") as f:
            print("# timestamp x y z a b", file=f)
            for t, (x, y, z, a, b) in self.stage_positions:
                print(t, x, y, z, a, b, file=f)
        
        print(f"Wrote file {f.name}")

        if self.mode != "diff":
            pos = np.array(self.stage_positions)  # x y z a b
            idx = np.argmin(np.abs(pos[:,3]))
            x_center = pos[:,0].mean()
            y_center = pos[idx,1]
            z_pos = pos[0:,2].mean()
            f = interp1d(pos[:,3], pos[:,1]-y_center, fill_value="extrapolate", kind="quadratic")

            d = {}
            d["y_offset"] = f
            d["x_offset"] = 0
            d["x_center"] = x_center
            d["y_center"] = y_center
            d["z_pos"] = self.startposition.z

            d["angle_min"] = self.start_angle
            d["angle_max"] = self.end_angle

            d["i"] = 0

            fn = self.path / f"track.pickle"
            pickle.dump(d, open(fn, "wb"))

            print(f"Wrote file {fn.name}")


if __name__ == '__main__':
    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)
    
    start_experiment(ctrl=ctrl, path=expdir)
