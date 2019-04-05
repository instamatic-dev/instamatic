from pathlib import Path
from instamatic import config

import logging
logger = logging.getLogger(__name__)

__all__ = ["Camera"]

default_cam = config.camera.name


def Camera(name: str=None, as_stream: bool=False):
    """Initialize the camera identified by the 'name' parameter
    if `as_stream` is True, it will return a VideoStream object
    if `as_stream` is False, it will return the raw Camera object
    """
    if name == None:
        name = default_cam
    elif name != config.cfg.camera:
        config.load(camera_name=name)
        name = config.cfg.camera

    if name == "simulate":
        from .camera_simu import CameraSimu
        cam = CameraSimu(name)
    elif name == "simulateDLL":
        from .camera_gatan import CameraDLL
        cam = CameraDLL(name)
    elif name in ("orius", "gatan"):
        from .camera_gatan import CameraDLL
        cam = CameraDLL("gatan")
    elif name in ("timepix", "pytimepix"):
        from . import camera_timepix
        tpx_config = Path(__file__).parent / "tpx" / "config.txt"  # TODO: put this somewhere central
        cam = camera_timepix.initialize(tpx_config)
    elif name == "emmenu":
        from .camera_emmenu import EMMenuWrapper
        cam = EMMenuWrapper()
        as_stream = False  # override `as_stream` for this interface
    else:
        raise ValueError(f"No such camera: {name}")

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
    # usage = """acquire"""

    description = """Program to acquire image data from gatan gatan ccd camera"""

    parser = argparse.ArgumentParser(  # usage=usage,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # parser.add_argument("args",
    #                     type=str, metavar="FILE",
    #                     help="Path to save cif")

    parser.add_argument("-b", "--binsize",
                        action="store", type=int, metavar="N", dest="binsize",
                        help="""Binsize to use. Must be one of 1, 2, or 4 (default 1)""")

    parser.add_argument("-e", "--exposure",
                        action="store", type=float, metavar="N", dest="exposure",
                        help="""Exposure time (default 0.5)""")

    parser.add_argument("-o", "--out",
                        action="store", type=str, metavar="image.png", dest="outfile",
                        help="""Where to store image""")

    parser.add_argument("-d", "--display",
                        action="store_true", dest="show_fig",
                        help="""Show the image (default True)""")

    # parser.add_argument("-t", "--tem",
    #                     action="store", type=str, dest="tem",
    #                     help="""Simulate microscope connection (default False)""")

    parser.add_argument("-u", "--simulate",
                        action="store_true", dest="simulate",
                        help="""Simulate camera/microscope connection (default False)""")
    
    parser.add_argument("-s", "--series",
                        action="store_true", dest="take_series",
                        help="""Enable mode to take a series of images (default False)""")
    
    parser.set_defaults(
        binsize=1,
        exposure=1,
        outfile=None,
        show_fig=False,
        test=False,
        simulate=False,
        camera="simulate",
        take_series=False
    )

    options = parser.parse_args()

    binsize = options.binsize
    exposure = options.exposure

    outfile = options.outfile
    show_fig = options.show_fig

    take_series = options.take_series

    from instamatic import TEMController
    ctrl = TEMController.initialize()
    
    if take_series:
        i = 1
        print("\nUsage:")
        print("    set b/e/i X -> set binsize/exposure/file number to X")
        print("    XXX         -> Add comment to header")
        print("    exit        -> exit the program")
    while take_series:
        outfile = "image_{:04d}".format(i)
        inp = input("\nHit enter to take an image: \n >> [{}] ".format(outfile))
        if inp == "exit":
            break
        elif inp.startswith("set"):
            try:
                key, value = inp.split()[1:3]
            except ValueError:
                print("Input not understood")
                continue
            if key == "e":
                try:
                    value = float(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    exposure = value
            elif key == "b":
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value in (1,2,4):
                    binsize = value
            elif key == "i":
                try:
                    value = int(value)
                except ValueError as e:
                    print(e)
                if value > 0:
                    i = value
            print("binsize = {} | exposure = {} | file #{}".format(binsize, exposure, i))
        else:
            arr, h = ctrl.getImage(binsize=binsize, exposure=exposure, comment=inp)

            write_tiff(outfile, arr, header=h)
    
            i += 1
    else:
        import matplotlib.pyplot as plt

        arr, h = ctrl.getImage(binsize=binsize, exposure=exposure)

        if show_fig:
            # save_header(sys.stdout, h)
            plt.imshow(arr, cmap="gray", interpolation="none")
            plt.show()
    
        if outfile:
            write_tiff(outfile, arr, header=h)
        else:
            write_tiff("out", arr, header=h)

    # cam.releaseConnection()


if __name__ == '__main__':
    # main_entry()
    cam = Camera(name="timepix")
    arr = cam.getImage(exposure=0.1)
    print(arr)
    print(arr.shape)
