import pytest

from instamatic.camera.camera_base import CameraBase
from instamatic.camera.camera_emmenu import CameraEMMENU
from instamatic.camera.camera_gatan import CameraDLL
from instamatic.camera.camera_gatan2 import CameraGatan2
from instamatic.camera.camera_merlin import CameraMerlin
from instamatic.camera.camera_simu import CameraSimu
from instamatic.camera.camera_timepix import CameraTPX

from .mock.camera import (
    CameraDLLMock,
    CameraEMMENUMock,
    CameraGatan2Mock,
    CameraMerlinMock,
    CameraServalMock,
    CameraSimuMock,
    CameraTPXMock,
)


def test_get_image(ctrl):
    bin1 = 1
    bin2 = 2
    bin4 = 4

    img, h = ctrl.get_image(binsize=bin1)
    x1, y1 = img.shape

    img, h = ctrl.get_image(binsize=bin2)
    x2, y2 = img.shape

    img, h = ctrl.get_image(binsize=bin4)
    x4, y4 = img.shape

    assert x1 == bin2 * x2
    assert y1 == bin2 * y2
    assert x1 == bin4 * x4
    assert y1 == bin4 * y4


def test_functions(ctrl):
    dims = ctrl.cam.get_image_dimensions()
    assert isinstance(dims, tuple)
    assert len(dims) == 2


@pytest.mark.parametrize(
    'cam',
    [
        pytest.param(CameraDLLMock, marks=pytest.mark.xfail(reason='establish_connection opens a popup window which halts execution')),
        pytest.param(CameraEMMENUMock, marks=pytest.mark.xfail(reason='Not implemented')),
        CameraGatan2Mock,
        CameraMerlinMock,
        pytest.param(CameraServalMock, marks=pytest.mark.xfail(reason='Not implemented')),
        CameraSimuMock,
        CameraTPXMock,
    ],
)
def test_init_mock(cam):
    c = cam()


@pytest.mark.parametrize(
    'cam',
    [
        CameraSimu,
        pytest.param(CameraDLL, marks=pytest.mark.xfail(reason='Needs config')),
        pytest.param(CameraGatan2, marks=pytest.mark.xfail(reason='Needs config + server')),
        CameraTPX,
        pytest.param(CameraEMMENU, marks=pytest.mark.xfail(reason='WinError: Invalid class string')),
        pytest.param(CameraMerlin, marks=pytest.mark.xfail(reason='Needs config + server')),
    ]
)
def test_init(cam):
    # Use "test" as the name of the camera, as this is where the settings are read from
    c = cam(name='test')
    assert isinstance(c, CameraBase)
