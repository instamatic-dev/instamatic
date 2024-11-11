from __future__ import annotations

import shutil
from math import sin
from pathlib import Path

from instamatic import config
from instamatic.config.utils import yaml
from instamatic.tools import relativistic_wavelength


def get_tvips_calibs(ctrl, rng: list, mode: str, wavelength: float) -> dict:
    """Loop over magnification ranges and return calibrations from EMMENU."""
    if mode == 'diff':
        print('Warning: Pixelsize can be a factor 10 off in diff mode (bug in EMMENU)')

    calib_range = {}

    binning = ctrl.cam.get_binning()

    ctrl.mode.set(mode)

    for i, mag in enumerate(rng):
        ctrl.magnification.index = i
        d = ctrl.cam.get_current_camera_info()

        img = ctrl.get_image(exposure=10)  # set to minimum allowed value
        index = ctrl.cam.get_image_index()
        v = ctrl.cam.get_emvector_by_index(index)

        PixelSizeX = v['fImgDistX']
        PixelSizeY = v['fImgDistY']

        assert (
            PixelSizeX == PixelSizeY
        ), 'Pixelsizes differ in X and Y direction?! (X: {PixelSizeX} | Y: {PixelSizeY})'

        if mode == 'diff':
            pixelsize = sin(PixelSizeX / 1_000_000) / wavelength  # µrad/px -> rad/px -> px/Å
        else:
            pixelsize = PixelSizeX

        calib_range[mag] = pixelsize

        # print("mode", mode, "mag", mag, "pixelsize", pixelsize)

    return calib_range


def choice_prompt(choices: list = [], default=None, question: str = 'Which one?'):
    """Simple cli to prompt for a list of choices."""
    print()

    try:
        default_choice = choices.index(default)
        suffix = f' [{default}]'
    except ValueError:
        default_choice = 0
        suffix = ''

    for i, choice in enumerate(choices):
        print(f'{i+1: 2d}: {choice}')

    q = input(f'\n{question}{suffix} >> ')
    if not q:
        q = default_choice
    else:
        q = int(q) - 1

    picked = choices[q]

    # print(choices, picked)
    print(picked)

    return picked


def main():
    import argparse

    description = """
This tool will help to set up the configuration files for `instamatic`.
It establishes a connection to the microscope and reads out the camera lengths and magnification ranges.
"""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    options = parser.parse_args()

    # Connect to microscope

    tem_name = choice_prompt(
        choices=['jeol', 'fei', 'simulate'],
        default='simulate',
        question='Which microscope can I connect to?',
    )

    # Fetch camera config

    drc = Path(__file__).parent
    choices = list(drc.glob('camera/*.yaml'))
    choices.append(None)

    cam_config = choice_prompt(
        choices=choices,
        default=None,
        question='Which camera type do you want to use (select closest one and modify if needed)?',
    )

    if cam_config:
        with open(cam_config) as f:
            cam_config_dict = yaml.safe_load(f)
            cam_name = cam_config_dict['interface']

            cam_connect = (
                input(
                    f'\nShould I connect to `{cam_name}` immediately?'
                    '\nThis is usually OK for gatan/simulate/TVIPS. [y/N] >> ',
                )
                == 'y'
            )
    else:
        cam_connect = False
        cam_name = None

    from instamatic.camera.camera import get_cam
    from instamatic.controller import TEMController
    from instamatic.microscope import get_microscope_class

    if cam_connect:
        cam = get_cam(cam_name)() if cam_name else None
    else:
        cam = None

    tem = get_microscope_class(tem_name)()

    ctrl = TEMController(tem=tem, cam=cam)

    try:
        ranges = ctrl.magnification.get_ranges()
    except BaseException:
        print('Warning: Cannot access magnification ranges')
        ranges = {}

    ht = ctrl.high_tension  # in V

    wavelength = relativistic_wavelength(ht)

    tem_config = {}
    tem_config['name'] = tem_name
    tem_config['wavelength'] = wavelength

    for mode, rng in ranges.items():
        tem_config['ranges'] = {mode: rng}

    calib_config = {}
    calib_config['name'] = tem_name

    # Find magnification ranges

    for mode, rng in ranges.items():
        calib_config[mode] = {}

        if cam_name == 'tvips':
            pixelsizes = get_tvips_calibs(ctrl=ctrl, rng=rng, mode=mode, wavelength=wavelength)
        else:
            pixelsizes = {r: 1.0 for r in rng}
        calib_config[mode]['pixelsize'] = pixelsizes

        stagematrices = {r: [1, 0, 0, 1] for r in rng}

        calib_config[mode]['stagematrix'] = stagematrices

    # Write/copy configs

    tem_config_fn = f'{tem_name}_tem.yaml'
    calib_config_fn = f'{tem_name}_calib.yaml'
    if cam_config:
        cam_config_fn = f'{cam_name}_cam.yaml'
        shutil.copyfile(cam_config, cam_config_fn)

    yaml.dump(tem_config, open(tem_config_fn, 'w'), sort_keys=False)
    yaml.dump(calib_config, open(calib_config_fn, 'w'), sort_keys=False)

    microscope_drc = config.locations['microscope']
    camera_drc = config.locations['camera']
    calibration_drc = config.locations['calibration']
    settings_yaml = config.locations['settings']

    print()
    print('Wrote files config files:')
    print(f'    Copy {tem_config_fn} -> `{microscope_drc / tem_config_fn}`')
    print(f'    Copy {calib_config_fn} -> `{calibration_drc / calib_config_fn}`')
    if cam_config:
        print(f'    Copy {cam_config_fn} -> `{camera_drc / cam_config_fn}`')
    print()
    print(f'In `{settings_yaml}`:')
    print(f'    microscope: {tem_name}_tem')
    print(f'    calibration: {tem_name}_calib')
    if cam_config:
        print(f'    camera: {cam_name}_cam')
    print()
    print('Todo:')
    print(f' 1. Check and update the pixelsizes in `{calib_config_fn}`')
    print('    - In real space, pixelsize in nm')
    print('    - In reciprocal space, pixelsize in px/Angstrom')
    print(f' 2. Check and update magnification ranges in `{microscope_config_fn}`')


if __name__ == '__main__':
    main()
