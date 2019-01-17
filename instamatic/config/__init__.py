import os, sys
import yaml
from pathlib import Path
import shutil

import logging
logger = logging.getLogger(__name__)


def initialize_in_AppData():
    src = Path(__file__).parent
    dst = Path(os.environ["AppData"]) / "instamatic"
    dst.mkdir(exist_ok=True, parents=True)

    print(f"No config directory found, creating new one in {dst}")

    config_drc = dst / "config"
    for sub_drc in ("microscope", "calibration", "camera"):
        shutil.copytree(src / sub_drc, config_drc / sub_drc)

    shutil.copy(src / "global.yaml", config_drc / "global.yaml")
    
    os.mkdir(dst / "scripts")
    os.mkdir(dst / "logs")

    print("Configuration directory has been initialized.")
    print(f"Directory: {dst}")
    print("Please review and restart the program.")
    os.startfile(dst)
    sys.exit()


def get_base_drc():
    """Figure out where configuration files for instamatic are stored"""
    try:
        search = Path(os.environ["instamatic"])  # if installed in portable way
        logger.debug("Search directory:", search)
    except KeyError:
        search = Path(os.environ["AppData"]) / "instamatic"
        logger.debug("Search directory:", search)

    if search.exists():
        return search
    else:
        initialize_in_AppData()


class ConfigObject(object):
    """docstring for ConfigObject"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"

    @classmethod
    def from_file(cls, path):
        return cls(yaml.load(open(path, "r")))


base_drc = get_base_drc()
config_drc = base_drc / "config"

assert config_drc.exists(), f"Configuration directory `{config_drc}` does not exist."

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)

print(f"Config directory: {config_drc}")

cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

microscope = None
calibration = None
camera = None

def load_cfg(microscope_name=cfg.microscope, calibration_name=cfg.calibration, camera_name=cfg.camera):
    global microscope
    global calibration
    global camera

    # print(f"Microscope->{microscope_name}; Calibration->{calibration_name}; Camera->{camera_name}")

    new_microscope = ConfigObject.from_file(base_drc / "config" / "microscope" / f"{microscope_name}.yaml")
    new_calibration = ConfigObject.from_file(base_drc / "config" / "calibration" / f"{calibration_name}.yaml")
    new_camera = ConfigObject.from_file(base_drc / "config" / "camera" / f"{camera_name}.yaml")

    # assign in two steps to ensure an exception is raised if any of the configs cannot be loaded
    microscope = new_microscope
    calibration = new_calibration
    camera = new_camera

    # load actual name of the object
    cfg.microscope = microscope.name
    cfg.calibration = calibration.name
    cfg.camera = camera.name

load_cfg()
