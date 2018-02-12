import os
import yaml
from pathlib import Path

import logging
logger = logging.getLogger(__name__)


def get_base_drc():
    """Figure out where configuration files for instamatic are stored"""
    try:
        search = Path(os.environ["instamatic"])  # if installed in portable way
    except KeyError:
        search = Path(os.environ["AppData"]) / "instamatic"

    if search.exists():
        return search

    return Path(__file__).parents[0]


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

assert config_drc.exists()
print(f"App directory: {base_drc}")

cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

microscope = ConfigObject.from_file(base_drc / "config" / "microscope" / f"{cfg.microscope}.yaml")
calibration = ConfigObject.from_file(base_drc / "config" / "calibration" / f"{cfg.calibration}.yaml")
camera = ConfigObject.from_file(base_drc / "config" / "camera" / f"{cfg.camera}.yaml")

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)
