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

    for sub_drc in ("microscope", "calibration", "camera"):
        shutil.copytree(src / sub_drc, dst / sub_drc)

    shutil.copy(src / "global.yaml", dst / "global.yaml")

    print("Configuration directory has been initialized.")
    print("Directory: {dst}")
    print("Please review and restart the program.")
    sys.exit()


def get_base_drc():
    """Figure out where configuration files for instamatic are stored"""
    try:
        search = Path(os.environ["instamaticx"])  # if installed in portable way
    except KeyError:
        search = Path(os.environ["AppData"]) / "instamaticx"

    if search.exists():
        return search

    return Path(__file__).parents[1]


class ConfigObject(object):
    """docstring for ConfigObject"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)

    @classmethod
    def from_file(cls, path):
        return cls(yaml.load(open(path, "r")))


base_drc = get_base_drc()
config_drc = base_drc / "config"

if not config_drc.exists():
    initialize_in_AppData()

assert config_drc.exists(), f"Configuration directory `{config_drc}` does not exist."
print(f"Config directory: {config_drc}")

cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

microscope = ConfigObject.from_file(base_drc / "config" / "microscope" / f"{cfg.microscope}.yaml")
calibration = ConfigObject.from_file(base_drc / "config" / "calibration" / f"{cfg.calibration}.yaml")
camera = ConfigObject.from_file(base_drc / "config" / "camera" / f"{cfg.camera}.yaml")

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)
