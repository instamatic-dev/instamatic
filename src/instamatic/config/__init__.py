import datetime
import logging
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

import yaml

from .config_updater import (
    check_defaults_yaml,
    check_settings_yaml,
    convert_config,
    is_oldstyle,
)

logger = logging.getLogger(__name__)


_settings_yaml = 'settings.yaml'
_defaults_yaml = 'defaults.yaml'
_logs = 'logs'
_config = 'config'
_microscope = 'microscope'
_calibration = 'calibration'
_camera = 'camera'
_scripts = 'scripts'
_alignments = 'alignments'
_instamatic = 'instamatic'


def nested_update(d: dict, u: dict) -> dict:
    """Nested dictionary update, updates `d` with `u`"""
    for k, v in u.items():
        if isinstance(v, Mapping):
            d[k] = nested_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


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

    shutil.copy(src / _settings_yaml, config_drc / _settings_yaml)
    shutil.copy(src / _defaults_yaml, config_drc / _defaults_yaml)

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

    def __init__(self, mapping: dict, name: str = 'config', location: str = None):
        super().__init__()
        self.name = name
        self.location = location
        self.mapping = {}
        self.update(mapping)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"

    def __getitem__(self, item):
        return self.mapping[item]

    @classmethod
    def from_file(cls, path: str):
        """Read configuration from yaml file, returns namespace."""
        name = Path(path).stem
        return cls(yaml.load(open(path), Loader=yaml.Loader), name=name, location=path)

    def update_from_file(self, path: str) -> None:
        """Update configuration from yaml file."""
        self.update(yaml.load(open(path), Loader=yaml.Loader))
        self.location = path

    def update(self, mapping: dict):
        for key, value in mapping.items():
            if isinstance(value, dict):
                try:
                    nested_update(getattr(self, key), value)
                except AttributeError:
                    setattr(self, key, value)
            else:
                setattr(self, key, value)
        nested_update(self.mapping, mapping)


def load_calibration(calibration_name: str = None):
    global calibration

    if not calibration_name:
        calibration_name = settings.calibration

    calibration_yaml = calibration_drc / f'{calibration_name}.yaml'

    if calibration_name:
        calibration_config = ConfigObject.from_file(calibration_yaml)
    else:
        calibration_config = ConfigObject({}, name='NoCalib')
        print('No calibration config is loaded.')

    if is_oldstyle(calibration_config, kind='calibration'):
        d = convert_config(calibration_yaml, kind='calibration')
        calibration_config.update(d)

    calibration = calibration_config

    settings.calibration = calibration.name


def load_microscope_config(microscope_name: str = None):
    global microscope

    if not microscope_name:
        microscope_name = settings.microscope

    microscope_yaml = microscope_drc / f'{microscope_name}.yaml'

    microscope_config = ConfigObject.from_file(microscope_yaml)

    # Check and update oldstyle configs (overwrite .yaml)
    if is_oldstyle(microscope_config, kind='microscope'):
        d = convert_config(microscope_yaml, kind='microscope')
        microscope_config.update(d)

    microscope = microscope_config

    settings.microscope = microscope.name


def load_camera_config(camera_name: str = None):
    global camera

    if not camera_name:
        camera_name = settings.camera

    camera_yaml = camera_drc / f'{camera_name}.yaml'

    if camera_name:
        camera_config = ConfigObject.from_file(camera_yaml)
    else:
        camera_config = ConfigObject({}, name='NoCamera')
        print('No camera config is loaded.')

    # Check and update oldstyle configs (overwrite .yaml)
    if is_oldstyle(camera_config, kind='camera'):
        d = convert_config(camera_yaml, kind='camera')
        camera_config.update(d)

    camera = camera_config
    camera.name = camera_name

    settings.camera = camera.name


def load_defaults():
    global defaults

    check_defaults_yaml(config_drc, _defaults_yaml)

    defaults = ConfigObject.from_file(Path(__file__).parent / _defaults_yaml)
    defaults.update_from_file(config_drc / _defaults_yaml)


def load_settings():
    global settings

    check_settings_yaml(config_drc / 'global.yaml', config_drc / _settings_yaml)

    settings = ConfigObject.from_file(Path(__file__).parent / _settings_yaml)
    settings.update_from_file(config_drc / _settings_yaml)

    settings.data_directory = Path(settings.data_directory)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    settings.work_directory = settings.data_directory / f'{today}'


def load_all(microscope_name: str = None,
             calibration_name: str = None,
             camera_name: str = None,
             ):
    """Load the settings.yaml file and microscope/calib/camera configs The
    config files to load can be overridden by specifying
    microscope_name/calibration_name/camera_name."""

    load_settings()
    load_defaults()
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

settings = None
defaults = None
microscope = None
calibration = None
camera = None

load_all()

locations = {
    'base': base_drc,
    'config': config_drc,
    'logs': logs_drc,
    'scripts': scripts_drc,
    'camera': alignments_drc,
    'calibration': calibration.location.parent,
    'microscope': microscope.location.parent,
    'alignments': camera.location.parent,
    'data': settings.data_directory,
    'work': settings.work_directory,
    'calibration_config': calibration.location,
    'microscope_config': microscope.location,
    'alignments_config': camera.location,
    'settings': config_drc / _settings_yaml,
    'defaults': config_drc / _defaults_yaml,
}
