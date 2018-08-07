import os, sys
import yaml
from pathlib import Path
import shutil

import logging
logger = logging.getLogger(__name__)


def initialize_in_AppData():
    src = Path(__file__).parent
    dst = Path(os.environ["AppData"]) / "instamatic"
    if not dst.exists():
        dst.mkdir(parents=True)

    print("No config directory found, creating new one in {dst}".format(dst=dst))

    config_drc = dst / "config"
    for sub_drc in ("microscope", "calibration", "camera"):
        shutil.copytree(str(src / sub_drc), str(config_drc / sub_drc))

    shutil.copy(str(src / "global.yaml"), str(config_drc / "global.yaml"))
    
    os.mkdir(str(dst / "scripts"))
    os.mkdir(str(dst / "logs"))

    print("Configuration directory has been initialized.")
    print("Directory: {dst}".format(dst=dst))
    print("Please review and restart the program.")
    os.startfile(str(dst))
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

    # return Path(__file__).parents[1]


class ConfigObject(object):
    """docstring for ConfigObject"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)

    @classmethod
    def from_file(cls, path):
        return cls(yaml.load(open(str(path), "r")))


base_drc = get_base_drc()
config_drc = base_drc / "config"

# if not config_drc.exists():
#     initialize_in_AppData()

assert config_drc.exists(), "Configuration directory `{config_drc}` does not exist.".format(config_drc=config_drc)
print("Config directory: {config_drc}".format(config_drc=config_drc))

cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

microscope = ConfigObject.from_file(base_drc / "config" / "microscope" / "{}.yaml".format(cfg.microscope))
calibration = ConfigObject.from_file(base_drc / "config" / "calibration" / "{}.yaml".format(cfg.calibration))
camera = ConfigObject.from_file(base_drc / "config" / "camera" / "{}.yaml".format(cfg.camera))

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

if not scripts_drc.exists():
    scripts_drc.mkdir()
if not logs_drc.exists():
    logs_drc.mkdir()
