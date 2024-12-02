from __future__ import annotations

from typing import Tuple

from instamatic import config
from instamatic.camera.camera_client import CamClient
from instamatic.camera.videostream import VideoStream
from instamatic.microscope.client import MicroscopeClient
from instamatic.simulation.camera import CameraSimulation
from instamatic.simulation.microscope import MicroscopeSimulation


def get_simulation_instances() -> Tuple[CameraSimulation, MicroscopeSimulation]:
    """Initialize simulated camera and microscope.

    Returns
    -------
    Tuple[CameraSimulation, MicroscopeSimulation]
    """
    if config.settings.use_tem_server:
        tem = MicroscopeClient(interface='simulate')
    else:
        tem = MicroscopeSimulation()
    if config.settings.use_cam_server:
        cam = CamClient(name='simulate', interface=config.camera.interface)
    else:
        camsim = CameraSimulation(tem=tem)
        cam = VideoStream(camsim)
    return cam, tem
