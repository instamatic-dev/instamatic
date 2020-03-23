import datetime
import logging
import os
import shutil
import sys
from pathlib import Path

import yaml

from .config_updater import convert_config
from .config_updater import is_oldstyle
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

    def __init__(self, mapping: dict, tag: str = 'config', location: str = None):
        super().__init__()
        self.name = tag
        self.location = location
        self.mapping = {}
        self.update(mapping)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.tag}')"

    def __getitem__(self, item):
        return self.mapping[item]

    @classmethod
    def from_file(cls, path: str):
        """Read configuration from yaml file, returns namespace."""
        tag = Path(path).stem
        return cls(yaml.load(open(path, 'r'), Loader=yaml.Loader), tag=tag, location=path)

    def update_from_file(self, path: str) -> None:
        """Update configuration from yaml file."""
        self.update(yaml.load(open(path, 'r'), Loader=yaml.Loader))

    def update(self, mapping: dict):
        for key, value in mapping.items():
            setattr(self, key, value)
        self.mapping.update(mapping)


def load_calibration(calibration_name: str = None):
    global calibration

    if not calibration_name:
        calibration_name = cfg.calibration

    calibration_yaml = calibration_drc / f'{calibration_name}.yaml'

    if calibration_name:
        calibration_cfg = ConfigObject.from_file(calibration_yaml)
    else:
        calibration_cfg = ConfigObject({}, tag='NoCalib')
        print('No calibration config is loaded.')

    if is_oldstyle(calibration_cfg):
        d = convert_config(calibration_yaml, kind='calibration')
        calibration_cfg.update(d, clear=True)

    calibration = calibration_cfg

    cfg.calibration = calibration.name


def load_microscope_config(microscope_name: str = None):
    global microscope

    if not microscope_name:
        microscope_name = cfg.microscope

    microscope_yaml = microscope_drc / f'{microscope_name}.yaml'

    microscope_cfg = ConfigObject.from_file(microscope_yaml)

    # Check and update oldstyle configs (overwrite .yaml)
    if is_oldstyle(microscope_cfg):
        d = convert_config(microscope_yaml, kind='microscope')
        microscope_cfg.update(d, clear=True)

    microscope = microscope_cfg

    cfg.microscope = microscope.name


def load_camera_config(camera_name: str = None):
    global camera

    if not camera_name:
        camera_name = cfg.camera

    camera_yaml = camera_drc / f'{camera_name}.yaml'

    if camera_name:
        camera_cfg = ConfigObject.from_file(camera_yaml)
    else:
        camera_cfg = ConfigObject({}, tag='NoCamera')
        print('No camera config is loaded.')

    camera = camera_cfg
    camera.name = camera_name

    cfg.camera = camera.name


def load_global_config():
    global cfg

    cfg = ConfigObject.from_file(Path(__file__).parent / _global_yaml)  # load defaults
    cfg.update_from_file(config_drc / _global_yaml)             # update user parameters

    cfg.data_directory = Path(cfg.data_directory)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    cfg.work_directory = cfg.data_directory / f'{today}'


def load_all(microscope_name: str = None,
             calibration_name: str = None,
             camera_name: str = None,
             ):
    """Load the global.yaml file and microscope/calib/camera configs The config
    files to load can be overridden by specifying
    microscope_name/calibration_name/camera_name."""

    load_global_config()
    load_microscope_config(microscope_name)
    load_camera_config(camera_name)
    load_calibration(calibration_name)


base_drc = get_base_drc()
config_drc = base_drc / _config

assert config_drc.exists(), f'Configuration directory `{config_drc}` does not exist.'

scripts_drc = base_drc / _scripts
logs_drc = base_drc / _logs
alignments_drc = base_drc / _alignments
microscope_drc = config_drc / _microscope
calibration_drc = config_drc / _calibration
camera_drc = config_drc / _camera

scripts_drc.mkdir(exist_ok=True)
logs_drc.mkdir(exist_ok=True)

print(f'Config directory: {config_drc}')

cfg = None
microscope = None
calibration = None
camera = None

load_all()
