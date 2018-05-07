from instamatic import config


def Microscope(kind: str, use_server: bool=False):
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
    elif kind == "jeol":
        from .jeol_microscope import JeolMicroscope
        tem = JeolMicroscope()
    elif kind == "fei_simu":
        from .fei_simu_microscope import FEISimuMicroscope
        tem = FEISimuMicroscope()
    elif kind == "simulate":
        from .simu_microscope import SimuMicroscope
        tem = SimuMicroscope()
    else:
        raise ValueError("No such microscope: `{}`".format(kind))

    return tem
