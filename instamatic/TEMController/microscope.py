from instamatic import config

default_tem = config.cfg.microscope


def get_tem(kind: str=default_tem):
    """Grab tem class"""
    
    if kind == "jeol":
        from .jeol_microscope import JeolMicroscope as cls
    elif kind == "fei_simu":
        from .fei_simu_microscope import FEISimuMicroscope as cls
    elif kind == "simulate":
        from .simu_microscope import SimuMicroscope as cls
    else:
        raise ValueError("No such microscope: `{}`".format(kind))

    return cls


def Microscope(kind: str=default_tem, use_server: bool=False):
    """Generic class to load microscope interface class

    kind: str
        Specify which microscope to use, must be one of `jeol`, `fei_simu`, `simulate`
    use_server: bool
        Connect to microscope server running on the host/port defined in the config file

    returns: TEM interface class
    """
    if use_server:
        from .server_microscope import ServerMicroscope
        tem = ServerMicroscope(kind)
    else:
        cls = get_tem(kind=kind)
        tem = cls()

    return tem
