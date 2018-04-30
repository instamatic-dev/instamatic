from instamatic import config
from instamatic.TEMController.server_microscope import ServerMicroscope

microscope_id = config.cfg.microscope


if __name__ == '__main__':
    tem = ServerMicroscope(microscope_id)

    from IPython import embed
    embed()
