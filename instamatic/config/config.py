import yaml
import os

from instamatic import config
cfg_file = config.TEM_config

camera = None
microscope = None
calibration = None


class ConfigObject(object):
    """docstring for ConfigObject"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)


def load(microscope_name=None, camera_name=None):
    global camera
    global microscope
    global calibration
    
    microscope_dct = config.get_microscope_config(microscope_name)

    if not camera_name:
        camera_name = microscope_dct["cameras"][0]
    else:
        if not camera_name in microscope_dct["cameras"]:
            raise ValueError("Camera {} not found in 'config' file.".format(camera_name))

    microscope = ConfigObject(microscope_dct)

    camera_dct = config.get_camera_config(camera)
    camera = ConfigObject(camera_dct)

    calibration_dct = config.get_calibration_dct(microscope_name, camera_name)

    calibration = ConfigObject(calibration_dct)


load()

# config.camera
# config.TEM
# config.calibration






        