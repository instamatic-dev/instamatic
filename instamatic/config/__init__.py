import os
import yaml

import logging
logger = logging.getLogger(__name__)

config_dir = os.path.join(os.environ["AppData"], "instamatic")

if not os.path.exists(config_dir):
    logger.info("Created config directory:", config_dir)
    os.makedirs(config_dir)

search_drcs = (config_dir, os.path.dirname(__file__)) 
# print "config dir: ", config_dir
# print "search dirs:", search_drcs


class ConfigObject(object):
    """docstring for ConfigObject"""
    def __init__(self, d):
        super(ConfigObject, self).__init__()
        self.d = d

        for key, value in d.items():
            setattr(self, key, value)


def get_config(name, drc=""):
    fn = os.path.join(drc, "{}.yaml".format(name))
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return ConfigObject(yaml.load(open(config, "r")))


cfg = get_config("global")

microscope = get_config(cfg.microscope, "microscope")
calibration = get_config(cfg.calibration, "calibration")
camera = get_config(cfg.camera, "camera")

