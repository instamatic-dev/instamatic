from instamatic import config

default_tem_interface = config.microscope.interface

__all__ = ['Microscope', 'get_tem']


def get_tem(interface: str):
    """Grab tem class with the specific 'interface'."""

    simulate = config.settings.simulate

    if config.settings.tem_require_admin:
        from instamatic import admin
        if not admin.is_admin():
            raise PermissionError('Access to the TEM interface requires admin rights.')

    if simulate or interface == 'simulate':
        from .simu_microscope import SimuMicroscope as cls
    elif interface == 'jeol':
        from .jeol_microscope import JeolMicroscope as cls
    elif interface == 'fei':
        from .fei_microscope import FEIMicroscope as cls
    elif interface == 'fei_simu':
        from .fei_simu_microscope import FEISimuMicroscope as cls
    else:
        raise ValueError(f'No such microscope interface: `{interface}`')

    return cls


def Microscope(name: str = None, use_server: bool = False):
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
        from .microscope_client import MicroscopeClient
        tem = MicroscopeClient(name=name)
    else:
        cls = get_tem(interface)
        tem = cls(name=name)

    return tem
