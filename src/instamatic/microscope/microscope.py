from __future__ import annotations

from typing import Optional

from instamatic import config
from instamatic.microscope.base import MicroscopeBase

default_tem_interface = config.microscope.interface

__all__ = ['get_microscope', 'get_microscope_class']


def get_microscope_class(interface: str) -> 'type[MicroscopeBase]':
    """Grab tem class with the specific 'interface'."""
    simulate = config.settings.simulate

    if config.settings.tem_require_admin:
        from instamatic import admin

        if not admin.is_admin():
            raise PermissionError('Access to the TEM interface requires admin rights.')

    if simulate or interface == 'simulate':
        from .interface.simu_microscope import SimuMicroscope as cls
    elif interface == 'jeol':
        from .interface.jeol_microscope import JeolMicroscope as cls
    elif interface == 'fei':
        from .interface.fei_microscope import FEIMicroscope as cls
    elif interface == 'fei_simu':
        from .interface.fei_simu_microscope import FEISimuMicroscope as cls
    else:
        raise ValueError(f'No such microscope interface: `{interface}`')

    return cls


def get_microscope(name: Optional[str] = None, use_server: bool = False) -> MicroscopeBase:
    """Generic class to load microscope interface class.

    name: str
        Specify which microscope to use, must be one of `jeol`, `fei_simu`, `simulate`
    use_server: bool
        Connect to microscope server running on the host/port defined in the config file

    returns: TEM interface class
    """
    if name is None:
        interface = default_tem_interface
        name = interface
    elif name != config.settings.microscope:
        config.load_microscope_config(microscope_name=name)
        interface = config.microscope.interface
    else:
        interface = config.microscope.interface

    if use_server:
        from .client import MicroscopeClient

        tem = MicroscopeClient(interface=interface)
    else:
        cls = get_microscope_class(interface=interface)
        tem = cls(name=name)

    return tem
