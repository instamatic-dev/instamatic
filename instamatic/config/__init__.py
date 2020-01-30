import datetime
import logging
import os
import shutil
import sys
from pathlib import Path

import yaml
logger = logging.getLogger(__name__)


_global_yaml = 'global.yaml'
_logs = 'logs'
_config = 'config'
_microscope = 'microscope'
_calibration = 'calibration'
_camera = 'camera'
_scripts = 'scripts'
_alignments = 'alignments'
_instamatic = 'instamatic'


def initialize_in_appData():
    """Initialize the configuration directory on first run Default to.

    %appdata%/instamatic.
    """
    src = Path(__file__).parent
    dst = Path(os.environ['AppData']) / _instamatic
    dst.mkdir(exist_ok=True, parents=True)

    print(f'No config directory found, creating new one in {dst}')

    config_drc = dst / _config
    for sub_drc in (_microscope, _calibration, _camera):
        shutil.copytree(src / sub_drc, config_drc / sub_drc)

    shutil.copy(src / _global_yaml, config_drc / _global_yaml)

    os.mkdir(dst / _logs)

    for sub_drc in (_scripts, _alignments):
        shutil.copytree(src / sub_drc, dst / sub_drc)

    print('Configuration directory has been initialized.')
    print(f'Directory: {dst}')
    print('Please review and restart the program.')
    os.startfile(dst)
    sys.exit()


def get_base_drc():
    """Figure out where configuration files for instamatic are stored."""
    try:
        search = Path(os.environ[_instamatic])  # if installed in portable way
        logger.debug('Search directory:', search)
    except KeyError:
        search = Path(os.environ['AppData']) / _instamatic
        logger.debug('Search directory:', search)

    if search.exists():
        return search
    else:
        initialize_in_appData()


def get_alignments() -> dict:
    """Get alignments from the alignment directory and return them as a dict of
    dicts.

    Use `ctrl.from_dict` to load the alignments
    """
    fns = alignments_drc.glob('*.yaml')
    alignments = {fn.name: yaml.full_load(open(fn)) for fn in fns}
    return alignments


class ConfigObject:
    """Namespace for configuration (maps dict items to attributes)."""

    def __init__(self, mapping: dict, tag='config'):
        super().__init__()
        self.tag = tag
        self.name = None  # default parameter
        self.mapping = {}
        self.update(mapping)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.tag}')"

    @classmethod
    def from_file(cls, path: str):
        """Read configuration from yaml file, returns namespace."""
        tag = Path(path).stem
        return cls(yaml.load(open(path, 'r'), Loader=yaml.Loader), tag=tag)

    def update_from_file(self, path: str) -> None:
        """Update configuration from yaml file."""
        self.update(yaml.load(open(path, 'r'), Loader=yaml.Loader))

    def update(self, mapping: dict):
        for key, value in mapping.items():
            setattr(self, key, value)

        self.mapping.update(mapping)


def load(microscope_name=None, calibration_name=None, camera_name=None):
    """Load the global.yaml file and microscope/calib/camera configs The config
    files to load can be overridden by specifying
    microscope_name/calibration_name/camera_name."""

    global microscope
    global calibration
    global camera
    global cfg

    cfg = ConfigObject.from_file(Path(__file__).parent / _global_yaml)  # load defaults
    cfg.update_from_file(base_drc / _config / _global_yaml)             # update user parameters

    if not microscope_name:
        microscope_name = cfg.microscope
    if not calibration_name:
        calibration_name = cfg.calibration
    if not camera_name:
        camera_name = cfg.camera

    microscope_cfg = ConfigObject.from_file(base_drc / _config / _microscope / f'{microscope_name}.yaml')

    if calibration_name:
        calibration_cfg = ConfigObject.from_file(base_drc / _config / _calibration / f'{calibration_name}.yaml')
    else:
        calibration_cfg = ConfigObject({}, tag='NoCalib')
        print('No calibration is loaded.')

    if camera_name:
        camera_cfg = ConfigObject.from_file(base_drc / _config / _camera / f'{camera_name}.yaml')
    else:
        camera_cfg = ConfigObject({}, tag='NoCamera')
        print('No camera is loaded.')

    # assign in two steps to ensure an exception is raised if any of the configs cannot be loaded
    microscope = microscope_cfg
    calibration = calibration_cfg
    camera = camera_cfg

    # load actual name of the object
    cfg.microscope = microscope.name
    cfg.calibration = calibration.name
    cfg.camera = camera.name

    cfg.data_directory = Path(cfg.data_directory)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    cfg.work_directory = cfg.data_directory / f'{today}'


base_drc = get_base_drc()
config_drc = base_drc / _config

assert config_drc.exists(), f'Configuration directory `{config_drc}` does not exist.'

scripts_drc = base_drc / _scripts
logs_drc = base_drc / _logs
alignments_drc = base_drc / _alignments

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)

print(f'Config directory: {config_drc}')

cfg = None
microscope = None
calibration = None
camera = None

load()
