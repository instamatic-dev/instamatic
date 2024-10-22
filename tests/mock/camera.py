from instamatic.camera.camera_gatan2 import CameraGatan2
from instamatic.camera.camera_merlin import CameraMerlin
from instamatic.camera.camera_simu import CameraSimu
from instamatic.camera.camera_gatan import CameraDLL
from instamatic.camera.camera_timepix import CameraTPX
from instamatic.camera.camera_emmenu import CameraEMMENU
from instamatic.camera.camera_base import CameraBase

try:
    from instamatic.camera.camera_serval import CameraServal
except ImportError:

    class CameraServal:
        pass


from instamatic import config

from .socket import SockMock, GatanSocketMock

__all__ = [
    "CameraDLLMock",
    "CameraEMMENUMock",
    "CameraGatan2Mock",
    "CameraMerlinMock",
    "CameraServalMock",
    "CameraSimuMock",
    "CameraTPXMock",
    "CameraMock",
]


class CameraMockBase:
    def load_defaults(self):
        for key, val in config.camera.mapping.items():
            setattr(self, key, val)


class CameraGatan2Mock(CameraMockBase, CameraGatan2):
    def __init__(self, name: str = "gatan2"):
        self.name = name
        self.g = GatanSocketMock(port="")
        self._recording = False
        self.load_defaults()


class CameraMerlinMock(CameraMockBase, CameraMerlin):
    host = "127.0.0.1"
    commandport = 0
    dataport = 1

    def establish_connection(self) -> None:
        self.s_cmd = SockMock()

    def establish_data_connection(self) -> None:
        self.s_data = SockMock()


class CameraSimuMock(CameraMockBase, CameraSimu):
    pass


class CameraDLLMock(CameraMockBase, CameraDLL):
    pass


class CameraTPXMock(CameraMockBase, CameraTPX):
    pass


class CameraEMMENUMock(CameraMockBase, CameraEMMENU):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError()


class CameraServalMock(CameraMockBase, CameraServal):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError()


class CameraMock(CameraMockBase, CameraBase):
    pass  # Will raise a error as not all abstract methods are implemented
