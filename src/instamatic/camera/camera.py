from __future__ import annotations

import logging
from pathlib import Path

from instamatic import config

logger = logging.getLogger(__name__)

__all__ = ['Camera']

default_cam_interface = config.camera.interface


def get_cam(interface: str = None):
    """Grabs the camera object defined by `interface`"""

    simulate = config.settings.simulate

    if simulate or interface == 'simulate':
        from instamatic.camera.camera_simu import CameraSimu as cam
    elif interface == 'simulateDLL':
        from instamatic.camera.camera_gatan import CameraDLL as cam
    elif interface in ('orius', 'gatan'):
        from instamatic.camera.camera_gatan import CameraDLL as cam
    elif interface == 'gatansocket':
        from instamatic.camera.camera_gatan2 import CameraGatan2 as cam
    elif interface in ('timepix', 'pytimepix'):
        from instamatic.camera.camera_timepix import CameraTPX as cam
    elif interface in ('emmenu', 'tvips'):
        from instamatic.camera.camera_emmenu import CameraEMMENU as cam
    elif interface == 'serval':
        from instamatic.camera.camera_serval import CameraServal as cam
    elif interface == 'merlin':
        from instamatic.camera.camera_merlin import CameraMerlin as cam
    else:
        raise ValueError(f'No such camera interface: {interface}')

    return cam


def Camera(name: str = None, as_stream: bool = False, use_server: bool = False):
    """Initialize the camera identified by the 'name' parameter if `as_stream`
    is True, it will return a VideoStream object if `as_stream` is False, it
    will return the raw Camera object."""

    if name is None:
        name = config.camera.name
    elif name != config.settings.camera:
        # load specific config/interface
        config.load_camera_config(camera_name=name)

    interface = config.camera.interface

    if use_server:
        from instamatic.camera.camera_client import CamClient

        cam = CamClient(name=name, interface=interface)
        as_stream = False  # precaution
    else:
        cam_cls = get_cam(interface)

        if interface in ('timepix', 'pytimepix'):
            tpx_config = (
                Path(__file__).parent / 'tpx' / 'config.txt'
            )  # TODO: put this somewhere central
            cam = cam_cls.initialize(tpx_config, name=name)
        elif interface in ('emmenu', 'tvips'):
            cam = cam_cls(name=name)
            as_stream = False  # override `as_stream` for this interface
        else:
            cam = cam_cls(name=name)

    if as_stream:
        if cam.streamable:
            from .videostream import VideoStream
        else:
            from .fakevideostream import VideoStream
        return VideoStream(cam)
    else:
        return cam


def main_entry():
    import argparse

    from instamatic.formats import write_tiff

    description = """Simple program to acquire image data from the camera."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-b',
        '--binsize',
        action='store',
        type=int,
        metavar='N',
        dest='binsize',
        help="""Binsize to use. Must be one of 1, 2, or 4 (default 1)""",
    )

    parser.add_argument(
        '-e',
        '--exposure',
        action='store',
        type=float,
        metavar='N',
        dest='exposure',
        help="""Exposure time (default 0.5)""",
    )

    parser.add_argument(
        '-o',
        '--out',
        action='store',
        type=str,
        metavar='image.png',
        dest='outfile',
        help="""Where to store image""",
    )

    parser.add_argument(
        '-d',
        '--display',
        action='store_true',
        dest='show_fig',
        help="""Show the image (default True)""",
    )

    parser.add_argument(
        '-s',
        '--series',
        action='store_true',
        dest='take_series',
        help="""Enable mode to take a series of images (default False)""",
    )

    parser.set_defaults(
        binsize=1,
        exposure=1,
        outfile=None,
        show_fig=False,
        test=False,
        take_series=False,
    )

    options = parser.parse_args()

    binsize = options.binsize
    exposure = options.exposure

    outfile = options.outfile
    show_fig = options.show_fig

    take_series = options.take_series

    from instamatic import controller

    ctrl = controller.initialize()

    if take_series:
        i = 1
        print('\nUsage:')
        print('    set b/e/i X -> set binsize/exposure/file number to X')
        print('    XXX         -> Add comment to header')
        print('    exit        -> exit the program')
    while take_series:
        outfile = f'image_{i:04d}'
        inp = input(f'\nHit enter to take an image: \n >> [{outfile}] ')
        if inp == 'exit':
            break
        elif inp.startswith('set'):
            try:
                key, value = inp.split()[1:3]
            except ValueError:
                print('Input not understood')
                continue
            if key == 'e':
                try:
                    value = float(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    exposure = value
            elif key == 'b':
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value in (1, 2, 4):
                    binsize = value
            elif key == 'i':
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    i = value
            print(f'binsize = {binsize} | exposure = {exposure} | file #{i}')
        else:
            arr, h = ctrl.get_image(binsize=binsize, exposure=exposure, comment=inp)

            write_tiff(outfile, arr, header=h)

            i += 1
    else:
        import matplotlib.pyplot as plt

        arr, h = ctrl.get_image(binsize=binsize, exposure=exposure)

        if show_fig:
            plt.imshow(arr, cmap='gray', interpolation='none')
            plt.show()

        if outfile:
            write_tiff(outfile, arr, header=h)
        else:
            write_tiff('out', arr, header=h)


if __name__ == '__main__':
    # main_entry()
    cam = Camera(use_server=True)
    arr = cam.get_image(exposure=0.1)
    print(arr)
    print(arr.shape)

    from IPython import embed

    embed(banner1='')
