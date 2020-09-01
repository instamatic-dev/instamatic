import logging

from instamatic.formats import read_image
from instamatic import config

logger = logging.getLogger(__name__)

def calibrate_dose(ctrl, num_imgs: int = 10, threshold: int = 50, logger=logger):
    '''Function to calibrate electron dose for cameras so the readings from the cameras 
        can be represented as e/s or e/A^2/s, not just a number without physical units
        1 coulomb = 6.242 × 10^18 electrons
        1 ampere is equal to 1 coulomb per second, which means:
        1 ampere = 6.242 × 10^18 electrons per second'''
    input("""Calibrate Electron Dose
        -------------------------------------------------------------------------------------------
    1. The image obtained from camera supposed to be after dark substraction and gain normalization
    2. Focus the beam on to the camera (not too focused)
    3. The beam should cover the whole camera as much as possible but should never go beyond the camera

    >> Press <Enter> to start >> \n""")

    exposure = ctrl.cam.default_exposure * num_imgs
    img, h = ctrl.get_image(exposure=exposure)

    input("""1. Extract the camera 
    2. Put down the fluorescent screen
    3. Reading out the current or current density reading from the fluorescent screen 
        
    >> Press <Enter> to continue >> \n""")

    diff = threshold
    while abs(diff) > 1:
        tmp_thresh = img[img <= threshold].mean()
        diff = threshold - tmp_thresh
        threshold = tmp_thresh

    print(f"Final threshold is {threshold}")

    num_pixels = (img > threshold).sum()
    avg_reading = img[img > threshold].mean()

    if ctrl.tem.name[:3] == 'fei':
        e_per_pixel_per_reading_per_sec = ctrl.current * 1e-9 / num_pixels / avg_reading * 6.242e18
    else:
        e_per_pixel_per_reading_per_sec = ctrl.current_density * 1e-12 / avg_reading * 6.242e18 * (ctrl.cam.cam.binsize*ctrl.cam.cam.physical_pixelsize*0.1)**2

    print('Electron dose calibration done.')
    print(f'The result for electron conversion ratio for the camera is {e_per_pixel_per_reading_per_sec} e/(pixel*reading*s).')

    return e_per_pixel_per_reading_per_sec

def convert_to_dose_rate(ctrl, num_imgs: int = 10, img_fn: str = None, e_per_pixel_per_reading_per_sec: float = None):
    '''Convert the readings in a camera into dose rate e/(s*Angstrom^2). Notice: find a blank hole to 
        take the image. No sample or carbon film should be presented in the image'''
    input("""Convert the readings in a camera into dose rate. Note:
    1. Find a blank hole to take an image
    2. No sample or carbon film should be presented in the image
    -------------------------------------------------------------
    >> Press <Enter> to continue >> \n""")

    if img_fn is None:
        img, h = ctrl.get_image(exposure=ctrl.cam.default_exposure * num_imgs)
        e_per_Angstrom2_per_second = e_per_pixel_per_reading_per_sec * img.mean() / (ctrl.cam.cam.binsize*ctrl.cam.cam.physical_pixelsize*1e7)**2
    else:
        img, h = read_image(img_fn)
        e_per_Angstrom2_per_second = e_per_pixel_per_reading_per_sec * img.mean() / (config.camera.default_binsize*config.camera.physical_pixelsize*1e7)**2

    print(f'Dose for the sample is {e_per_Angstrom2_per_second} e/(s*Angstrom^2)')


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

    from instamatic import TEMController
    ctrl = TEMController.initialize()
    e = calibrate_dose(ctrl=ctrl, num_imgs=num_images, threshold=threshold)
    convert_to_dose_rate(ctrl=ctrl, num_imgs=num_images, e_per_pixel_per_reading_per_sec=e)

if __name__ == '__main__':
    main_entry()
    