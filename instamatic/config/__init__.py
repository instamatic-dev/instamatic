import os, sys
import yaml
from pathlib import Path
import shutil

import logging
logger = logging.getLogger(__name__)


def initialize_in_appData():
    """Initialize the configuration directory on first run
    Default to %appdata%/instamatic"""
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
        initialize_in_appData()


class ConfigObject(object):
    """Namespace for configuration (maps dict items to attributes"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"

    @classmethod
    def from_file(cls, path):
        """Read configuration from yaml file, returns namespace"""
        return cls(yaml.load(open(path, "r"), Loader=yaml.Loader))


def load(microscope_name=None, calibration_name=None, camera_name=None):
    """Load the global.yaml file and microscope/calib/camera configs
    The config files to load can be overridden by specifying 
        microscope_name/calibration_name/camera_name"""
        
    global microscope
    global calibration
    global camera
    global cfg

    cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

    if not microscope_name:
        microscope_name = cfg.microscope
    if not calibration_name:
        calibration_name = cfg.calibration
    if not camera_name:
        camera_name = cfg.camera

    # print(f"Microscope->{microscope_name}; Calibration->{calibration_name}; Camera->{camera_name}")

    microscope_cfg = ConfigObject.from_file(base_drc / "config" / "microscope" / f"{microscope_name}.yaml")
    calibration_cfg = ConfigObject.from_file(base_drc / "config" / "calibration" / f"{calibration_name}.yaml")
    camera_cfg = ConfigObject.from_file(base_drc / "config" / "camera" / f"{camera_name}.yaml")

    # assign in two steps to ensure an exception is raised if any of the configs cannot be loaded
    microscope = microscope_cfg
    calibration = calibration_cfg
    camera = camera_cfg

    # load actual name of the object
    cfg.microscope = microscope.name
    cfg.calibration = calibration.name
    cfg.camera = camera.name


base_drc = get_base_drc()
config_drc = base_drc / "config"

assert config_drc.exists(), f"Configuration directory `{config_drc}` does not exist."

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)

print(f"Config directory: {config_drc}")

cfg = None
microscope = None
calibration = None
camera = None

load()
