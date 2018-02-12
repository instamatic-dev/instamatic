import os
import yaml
from pathlib import Path

import logging
logger = logging.getLogger(__name__)

# print "config dir: ", config_dir
# print "search dirs:", search_drcs

def get_base_drc():
    portable = Path(os.environ["instamatic"])  # if installed in portable way
    app_data = Path(os.environ["AppData"])

    search_drcs = (portable, app_data / "instamatic", Path(__file__).parents[0]) 

    for drc in search_drcs:
        if drc.exists():
            return drc


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

assert base_drc.joinpath("config").exists()
print(f"(Instamatic base directory: {base_drc}")

cfg = ConfigObject.from_file(base_drc / "config" / "global.yaml")

microscope = ConfigObject.from_file(base_drc / "config" / cfg.microscope / "microscope.yaml")
calibration = ConfigObject.from_file(base_drc / "config" / cfg.calibration / "calibration.yaml")
camera = ConfigObject.from_file(base_drc / "config" / cfg.camera / "camera.yaml")

scripts_drc = base_drc / "scripts"
logs_drc = base_drc / "logs"

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)
