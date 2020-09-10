import logging
from .holder import Holder

from instamatic import config

logger = logging.getLogger(__name__)

_ctrl = None  # store reference of ctrl so it can be accessed without re-initializing

default_holder = config.holder.name

def initialize(holder_name: str = default_holder):
    """"""
    print(f"Holder: {holder_name}")
    holder = Holder(holder_name)

    global _ctrl
    ctrl = _ctrl = HolderController(holder=holder)

    return ctrl

def get_instance():
    """Gets the current `ctrl` instance if it has been initialized, otherwise 
    initialize it using default parameters."""

    global _ctrl

    if _ctrl:
        ctrl = _ctrl
    else:
        ctrl = _ctrl = initialize()

    return ctrl

class HolderController:
    """"""
    def __init__(self, holder):
        self.holder = holder

    def getStagePosition(self):
        """"""
        pass

    def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, wait=True, speed=1):
        """"""
        pass


def main_entry():
    import argparse
    description = """Program to calibrate the electron dose of the camera. Must be performed online."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-n', '--num_images', dest='num_images', type=int, nargs=1, metavar='N', default=10,
                        help=('Specify the number images for determining the total exposure time'))

    parser.add_argument('-t', '--threshold', dest='threshold', nargs=1, type=int, metavar='T', default=50,
                        help=('Specify the minimum length (in stage coordinates) the calibration '))

    options = parser.parse_args()
    parser.set_defaults(num_images=10, threshold=50)
    num_images = options.num_images
    threshold = options.threshold



if __name__ == '__main__':
    from IPython import embed
    ctrl = get_instance()
    
    embed(banner1='\nAssuming direct control.\n')
