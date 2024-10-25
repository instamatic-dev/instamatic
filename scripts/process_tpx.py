"""Script to re-process cRED data collecting using instamatic with a Timepix
camera.

To use:     Run `python process_tpx.py cred_log.txt`

Where the first argument is the path to the cred_log.txt file. Assumes
the data are stored in a subdirectory `tiff/*.tif` from where
cred_log.txt is stored.

Defaults to `cred_log.txt` in the current directory if left blank.

If the first argument is given as `all`, the script will look for all
`cred_log.txt` files in the subdirectories, and iterate over those.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from instamatic.formats import read_tiff
from instamatic.processing.ImgConversionTPX import ImgConversionTPX as ImgConversion


def mark_cross(img, mask_value=0):
    img[255:258] = mask_value
    img[:, 255:258] = mask_value

    img[258:261] = mask_value
    img[:, 258:261] = mask_value

    return img


def center_images(img_conv, plot=True):
    centers = img_conv._beam_centers

    beam_center_mean, beam_center_std = img_conv.mean_beam_center, img_conv.beam_center_std
    print(f'Old mean: {beam_center_mean}, std: {beam_center_std}')

    target = img_conv.mean_beam_center.astype(int)

    print(len(centers), len(img_conv.data))

    j = 0
    for i, img in img_conv.data.items():
        center = centers[j].astype(int)
        shift = center - target
        new = np.roll(img, -shift, axis=(0, 1))
        # img_conv.data[i] = mark_cross(new)
        img_conv.data[i] = new

        j += 1

    beam_center_mean, beam_center_std = img_conv.get_beam_centers()
    img_conv.mean_beam_center = beam_center_mean
    img_conv.beam_center_std = beam_center_std
    print(f'New mean: {beam_center_mean}, std: {beam_center_std}')

    if plot:
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot(centers[:, 0], label='X old')
        ax.plot(centers[:, 1], label='Y old')
        ax.plot(img_conv._beam_centers[:, 0], label='X new')
        ax.plot(img_conv._beam_centers[:, 1], label='Y new')
        ax.legend()
        ax.axhline(target[0], color='red', linestyle='--', linewidth=0.5)
        ax.axhline(target[1], color='red', linestyle='--', linewidth=0.5)
        plt.show()


def reprocess(credlog, tiff_path=None, mrc_path=None, smv_path='SMV_reprocessed'):
    credlog = Path(credlog)
    drc = credlog.parent
    image_fns = list(drc.glob('tiff/*.tiff'))

    n = len(image_fns)
    if n == 0:
        print('No files found matching `tiff/*.tiff`')
        exit()
    else:
        print(n)

    buffer = []

    rotation_axis = -2.24  # add np.pi/2 for old files
    acquisition_time = None

    # osc_angle = 0.53

    with open(credlog) as f:
        for line in f:
            if line.startswith('Camera length'):
                camera_length = float(line.split()[2])
            if line.startswith('Oscillation angle'):
                osc_angle = float(line.split()[2])
            if line.startswith('Starting angle'):
                start_angle = float(line.split()[2])
            if line.startswith('Ending angle'):
                end_angle = float(line.split()[2])
            if line.startswith('Rotation axis'):
                rotation_axis = float(line.split()[2])
            if line.startswith('Acquisition time'):
                acquisition_time = float(line.split()[2])
            if line.startswith('Exposure Time'):
                exposure_time = float(line.split()[2])
            if line.startswith('Pixelsize'):
                pixelsize = float(line.split()[1])
            if line.startswith('Physical pixelsize'):
                physical_pixelsize = float(line.split()[2])
            if line.startswith('Wavelength'):
                wavelength = float(line.split()[1])
            if line.startswith('Stretch amplitude'):
                stretch_azimuth = float(line.split()[2])
            if line.startswith('Stretch azimuth'):
                stretch_amplitude = float(line.split()[2])

    if not acquisition_time:
        acquisition_time = exposure_time + 0.015

    print('camera_length:', camera_length)
    print('Oscillation angle:', osc_angle)
    print('Starting angle:', start_angle)
    print('Ending angle:', end_angle)
    print('Rotation axis:', rotation_axis)
    print('Acquisition time:', acquisition_time)

    def extract_image_number(s):
        p = Path(s)
        return int(p.stem.split('_')[-1])

    for i, fn in enumerate(image_fns):
        j = extract_image_number(fn)
        img, h = read_tiff(fn)
        buffer.append((j, img, h))

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
        stretch_amplitude=stretch_amplitude,
        stretch_azimuth=stretch_azimuth,
    )

    # azimuth, amplitude = 83.37, 2.43  # add 90 to azimuth for old files
    # img_conv.stretch_azimuth, img_conv.stretch_amplitude = azimuth, amplitude
    print('Stretch amplitude', img_conv.stretch_amplitude)
    print('Stretch azimuth', img_conv.stretch_azimuth)

    # if img_conv.beam_center_std.mean() > 5:
    #     print("Large beam center variation detected, aligning images!")
    #     center_images(img_conv)

    if mrc_path:
        mrc_path = drc / mrc_path
    if smv_path:
        smv_path = drc / smv_path
    if tiff_path:
        smv_path = drc / tiff_path

    img_conv.threadpoolwriter(
        tiff_path=tiff_path, mrc_path=mrc_path, smv_path=smv_path, workers=8
    )

    if mrc_path:
        img_conv.write_ed3d(mrc_path)

    if smv_path:
        img_conv.write_xds_inp(smv_path)
        # img_conv.to_dials(smv_path)


def main():
    try:
        credlog = sys.argv[1]
    except IndexError:
        credlog = 'cRED_log.txt'

    if credlog == 'all':
        fns = Path('.').glob('**/cRED_log.txt')

        for fn in fns:
            print(fn)
            reprocess(fn)

    else:
        reprocess(credlog)


if __name__ == '__main__':
    main()
