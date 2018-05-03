from instamatic import config


def Microscope(kind, use_server=False):
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
