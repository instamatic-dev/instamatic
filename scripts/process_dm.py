from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.exposure import rescale_intensity

from instamatic.processing.ImgConversionDM import ImgConversionDM as ImgConversion
from instamatic.tools import relativistic_wavelength

# Script to process cRED data collecting using the DigitalMicrograph script `insteaDMatic`
# https://github.com/instamatic-dev/InsteaDMatic
#
# To use:
#     Run `python process_dm.py cred_log.txt`
#
# Where the first argument is the path to the cred_log.txt file. Assumes the data are stored
# in a subdirectory `tiff/*.tif` from where cred_log.txt is stored.
#
# Defaults to `cred_log.txt` in the current directory if left blank.
#
# If the first argument is given as `all`, the script will look for
# all `cred_log.txt` files in the subdirectories, and iterate over those.


def img_convert(credlog, tiff_path='tiff2', mrc_path='RED', smv_path='SMV'):
    credlog = Path(credlog)
    drc = credlog.parent

    image_fns = list(drc.glob('tiff/*.tif'))

    n = len(image_fns)
    if n == 0:
        print('No files found matching `tiff/*.tif`')
        exit()
    else:
        print(n)

    buffer = []

    with open(credlog) as f:
        for line in f:
            if line.startswith('Data Collection Time'):
                timestamp = line.split(':', 1)[-1].strip()
            if line.startswith('Camera length (mm):'):
                camera_length = float(line.split()[-1])
            if line.startswith('Oscillation angle'):
                osc_angle = float(line.split()[-1])
            if line.startswith('High tension (kV):'):
                high_tension = float(line.split()[-1])
            if line.startswith('Starting angle'):
                start_angle = float(line.split()[-1])
            if line.startswith('Ending angle'):
                end_angle = float(line.split()[-1])
            if line.startswith('Rotation axis'):
                rotation_axis = float(line.split()[-1])
            if line.startswith('Acquisition time'):
                acquisition_time = float(line.split()[-1])
            if line.startswith('Exposure Time'):
                exposure_time = float(line.split()[-1])
            if line.startswith('Image pixelsize x/y (1/nm):'):
                inp = line.split()
                pixelsize = (float(inp[-2]), float(inp[-1]))
            if line.startswith('Image physical pixelsize x/y (um):'):
                inp = line.split()
                physical_pixelsize = (float(inp[-2]), float(inp[-1]))
            if line.startswith('Binsize:'):
                binsize = float(line.split()[-1])
            if line.startswith('Image resolution x/y (px):'):
                inp = line.split()
                resolution = (int(inp[-2]), int(inp[-1]))
            if line.startswith('Camera:'):
                camera = line.split()[-1]
            if line.startswith('Resolution:'):
                resolution = line.split()[-1]

    wavelength = relativistic_wavelength(high_tension * 1000)

    # convert from um to mm
    physical_pixelsize = physical_pixelsize[0] / 1000

    # convert from 1/nm to 1/angstrom
    pixelsize = pixelsize[0] * 10

    # rotation axis
    # for themisZ/Oneview: -171.0; for 2100LaB6/Orius: 53.0; otherwise: 0.0
    rotation_axis = np.radians(rotation_axis)

    print('timestamp:', timestamp)
    print('Wavelength:', wavelength)
    print('Camera:', camera)
    print('Resolution (px):', resolution)
    print('TEM Camera length (mm):', camera_length)
    print('Pixelsize (1/Angstrom):', pixelsize)
    print('Physical pixelsize (um):', physical_pixelsize)
    print('Starting angle (deg.):', start_angle)
    print('Ending angle (deg.):', end_angle)
    print('Oscillation angle (deg./frame):', osc_angle)
    print('Acquisition time (s/frame):', acquisition_time)
    print('Rotation axis (rad.):', rotation_axis)
    # print("Binsize:", binsize)

    def extract_image_number(s):
        p = Path(s)
        return int(p.stem.split('_')[-1])

    for i, fn in enumerate(image_fns):
        j = extract_image_number(fn)
        img = np.array(Image.open(fn))

        h = {'ImageGetTime': timestamp, 'ImageExposureTime': exposure_time}
        buffer.append((j, img, h))

    if img.dtype != np.uint16:
        max_val = max(img.max() for _, img, _ in buffer)
        min_val = min(img.min() for _, img, _ in buffer)
        for item in buffer:
            # cast to 16 bit uint16
            item[1] = rescale_intensity(
                item[1], out_range='uint16', in_range=(min_val, max_val)
            )

    img_conv = ImgConversion(
        buffer=buffer,
        osc_angle=osc_angle,
        start_angle=start_angle,
        end_angle=end_angle,
        rotation_axis=rotation_axis,
        acquisition_time=acquisition_time,
        flatfield=None,
        pixelsize=pixelsize,
        physical_pixelsize=physical_pixelsize,
        wavelength=wavelength,
    )

    if mrc_path:
        mrc_path = drc / mrc_path
    if smv_path:
        smv_path = drc / smv_path
    if tiff_path:
        tiff_drc_name = tiff_path
        tiff_path = drc / tiff_path

    img_conv.threadpoolwriter(
        tiff_path=tiff_path, mrc_path=mrc_path, smv_path=smv_path, workers=8
    )

    if mrc_path:
        img_conv.write_ed3d(mrc_path)

    if smv_path:
        img_conv.write_xds_inp(smv_path)
        # img_conv.to_dials(smv_path)

    img_conv.write_pets_inp(path=drc, tiff_path=tiff_drc_name)


def main():
    try:
        credlog = sys.argv[1]
    except IndexError:
        credlog = 'cRED_log.txt'

    if credlog == 'all':
        fns = Path('.').glob('**/cRED_log.txt')

        for fn in fns:
            print(fn)
            img_convert(fn)

    else:
        img_convert(credlog)


if __name__ == '__main__':
    main()
