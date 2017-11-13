import os

import logging
logger = logging.getLogger(__name__)

config_dir = os.path.join(os.environ["AppData"], "instamatic")

if not os.path.exists(config_dir):
    logger.info("Created config directory:", config_dir)
    os.makedirs(config_dir)

search_drcs = (config_dir, os.path.dirname(__file__)) 
print "config dir: ", config_dir
print "search dirs:", search_drcs

for drc in search_drcs:
    TEM_config = os.path.join(drc, "config.yaml")
    if os.path.exists(TEM_config):
        break

print TEM_config

def get_camera_config(name):
    fn = os.path.join("camera", "{}.json".format(name))
    for drc in search_drcs:
        config = os.path.join(drc, fn)
        if os.path.exists(config):
            break
    return config

orius_config = get_camera_config("orius")
simulate_config = get_camera_config("simulate")
simulateDLL_config = get_camera_config("simulateDLL")
timepix_config = get_camera_config("timepix")

print orius_config
print simulate_config
print simulateDLL_config
print timepix_config
