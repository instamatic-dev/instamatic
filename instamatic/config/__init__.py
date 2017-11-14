import os
import json, yaml

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


def get_global_config():
    fn = os.path.join("global.yaml")
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return ConfigObject(yaml.load(open(config, "r")))


def get_camera_config(name):
    fn = os.path.join("camera", "{}.json".format(name))
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return ConfigObject(json.load(open(config, "r")))


def get_microscope_config(name):
    fn = os.path.join("microscope", "{}.yaml".format(name))
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return ConfigObject(yaml.load(open(config, "r")))


def get_calibration_config(name):
    fn = os.path.join("calibration", "{}.yaml".format(name))
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return ConfigObject(yaml.load(open(config, "r")))

cfg = get_global_config()

microscope = get_microscope_config(cfg.microscope)
calibration = get_calibration_config(cfg.calibration)
camera = get_camera_config(cfg.camera)



