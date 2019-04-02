import datetime
import time
from math import floor
from instamatic import config, version
from pathlib import Path
from .emmenu import EMMenuWrapper


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
    def __init__(self, ctrl, path: str=None, log=None):
        super().__init__()

        self.ctrl = ctrl
        self.path = Path(path)

        self.emmenu = self.ctrl.emmenu = EMMenuWrapper()

        self.logger = log

    def get_ready(self):
        self.ctrl.beamblank_on()
        self.ctrl.screen_up()

        if self.ctrl.mode != 'diff':
            print("Switching to diffraction mode")
            self.ctrl.mode = 'diff'
    
        spotsize = self.ctrl.spotsize
        if spotsize not in (4, 5):
            print(f"Spotsize is quite high ({spotsize}), maybe you want to lower it?")

        if not self.emmenu.live_view_is_running:
            delay = 2.0
            self.emmenu.toggle_liveview()
            time.sleep(delay)

    def start_collection(self, target_angle: float):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        start_position = self.ctrl.stageposition.get()
        start_angle = start_position[3]  

        self.ctrl.beamblank_off()

        self.emmenu.toggle_record()  # start recording

        t0 = time.perf_counter()
        self.ctrl.stageposition.a = target_angle
        # time.sleep(5.0)
        t1 = time.perf_counter()

        self.ctrl.beamblank_on()

        self.emmenu.toggle_liveview()  # end liveview and stop recording

        end_position = self.ctrl.stageposition.get()
        end_angle = end_position[3]

        t_start = t0
        t_end = t1
        total_time = t1 - t0
        
        # nframes = floor(total_time / 1)  # Is there a way to guess this ?
        
        # osc_angle = abs(end_angle - start_angle) / nframes
        
        # acquisition_time = total_time / nframes
        total_angle = abs(end_angle - start_angle)
        rotation_axis = config.camera.camera_rotation_vs_stage_xy

        camera_length = int(self.ctrl.magnification.get())

        spotsize = self.ctrl.spotsize

        rotation_speed = (end_angle-start_angle) / total_time

        print(f"\nRotated {total_angle:.2f} degrees from {start_angle:.2f} to {end_angle:.2f}")
        print("Start stage position:  X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*start_position))
        print("End stage position:    X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:6.1f} | B {:6.1f}".format(*end_position))
        print(f"Data collection camera length: {camera_length} cm")
        print(f"Data collection spot size: {spotsize}")
        print(f"Rotation speed: {rotation_speed:.3f} degrees/s")

        with open(self.path / "cRED_log.txt", "w") as f:
            print(f"Program: {version.__long_title__} + EMMenu 4.0", file=f)
            print(f"Data Collection Time: {now}", file=f)
            print(f"Time Period Start: {t_start}", file=f)
            print(f"Time Period End: {t_end}", file=f)
            print(f"Starting angle: {start_angle:.2f} degrees", file=f)
            print(f"Ending angle: {end_angle:.2f} degrees", file=f)
            print(f"Rotation range: {end_angle-start_angle:.2f} degrees", file=f)
            print(f"Rotation speed: {rotation_speed:.3f} degrees/s", file=f)
            # print(f"Exposure Time: {exposure:.3f} s", file=f)
            # print(f"Acquisition time: {acquisition_time:.3f} s", file=f)
            print(f"Total time: {total_time:.3f} s", file=f)
            print(f"Spot Size: {spotsize}", file=f)
            print(f"Camera length: {camera_length} cm", file=f)
            print(f"Rotation axis: {rotation_axis} radians", file=f)
            # print(f"Oscillation angle: {osc_angle:.4f} degrees", file=f)
            print("Stage start: X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:8.2f} | B {:8.2f}".format(*start_position), file=f)
            print("Stage end:   X {:6.0f} | Y {:6.0f} | Z {:6.0f} | A {:8.2f} | B {:8.2f}".format(*end_position), file=f)
            print("", file=f)

        print(f"Wrote file {f.name}")

        path_data = self.path / "raw"
        path_data.mkdir(exist_ok=True, parents=True)

        print(f"Don't forget to save the data to {path_data}")


if __name__ == '__main__':
    expdir = controller.module_io.get_new_experiment_directory()
    expdir.mkdir(exist_ok=True, parents=True)
    
    start_experiment(ctrl=ctrl, path=expdir)
