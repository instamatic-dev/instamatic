"""Script to process cRED data collecting using instamatic with the EMMENU
plugin.

To use, run: `python process_tvips.py cred_log.txt`

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

import numpy as np
import tifffile

from instamatic.processing.ImgConversionTVIPS import ImgConversionTVIPS as ImgConversion
from instamatic.tools import get_acquisition_time, relativistic_wavelength


def extract_image_number(s):
    p = Path(s)
    return int(p.stem.split('_')[-1])


def img_convert(credlog, tiff_path=None, pets_path='PETS', mrc_path='RED', smv_path='SMV'):
    credlog = Path(credlog)
    drc = credlog.parent

    pattern = 'tiff/*.tif*'

    image_fns = list(drc.glob(pattern))

    # sort by frame number (avoid confusion with _9.tif -> _10.tif)
    image_numbers = [extract_image_number(fn) for fn in image_fns]
    image_numbers, image_fns = zip(*sorted(zip(image_numbers, image_fns)))

    nframes = len(image_fns)
    if nframes == 0:
        print(f'No files found matching `{pattern}`')
        exit()
    else:
        print(nframes)

    ims = [tifffile.TiffFile(fn) for fn in image_fns]
    hs = [im.tvips_metadata for im in ims]

    ts = [h['Time'] for h in hs]  # sort by timestamps

    h0 = hs[0]
    exposure_time = h0['ExposureTime']

    res = get_acquisition_time(timestamps=ts, exp_time=exposure_time, savefig=True, drc=drc)
    acquisition_time = res.acquisition_time
    overhead = res.overhead

    with open(credlog) as f:
        for line in f:
            if line.startswith('Data Collection Time'):
                timestamp = line.split(':', 1)[-1].strip()
            if line.startswith('Starting angle'):
                start_angle = float(line.split()[2])
            if line.startswith('Ending angle'):
                end_angle = float(line.split()[2])
            if line.startswith('Rotation axis'):
                rotation_axis = float(line.split()[2])
            if line.startswith('Rotation speed'):
                rotation_speed = float(line.split()[2])
            if line.startswith('Beam stopper:'):
                beamstop = 'yes' in line.split()[2]
            if line.startswith('Camera length:'):
                camera_length = float(line.split()[2])
            if line.startswith('Pixelsize:'):
                pixelsize = float(line.split()[1])
            if line.startswith('Physical pixelsize:'):
                physical_pixelsize = float(line.split()[2])
            if line.startswith('Wavelength:'):
                wavelength = float(line.split()[1])

    beamstop = True

    # from cred_log

    osc_angle = abs(rotation_speed * acquisition_time)
    direction = [1, -1][end_angle < start_angle]
    end_angle = start_angle + direction * nframes * osc_angle

    # from header

    high_tension = h0['TemHighTension']  # ev
    camera = h0['CameraType']

    # It seems that this number cannot be trusted, either in cm or mm, depending on the mode used
    camera_length_tvips = int(h0['TemMagnification'])

    wavelength_tvips = relativistic_wavelength(high_tension)

    binning_x = h0['BinningX']
    binning_y = h0['BinningY']

    physical_pixelsize_x_tvips = binning_x * h0['PhysicalPixelSizeX'] / 1_000_000  # nm -> mm
    physical_pixelsize_y_tvips = binning_y * h0['PhysicalPixelSizeY'] / 1_000_000  # nm -> mm

    # pixelsize can be a factor 10 off, depending on the mode used
    pixelsize_x_tvips = (
        np.sin(h0['PixelSizeX'] / 1_000_000) / wavelength
    )  # µrad/px -> rad/px -> px/Å
    pixelsize_y_tvips = (
        np.sin(h0['PixelSizeY'] / 1_000_000) / wavelength
    )  # µrad/px -> rad/px -> px/Å

    image_res_x_tvips = h0['ImageSizeX']
    image_res_y_tvips = h0['ImageSizeY']

    print(f'Number of frames: {nframes}')
    print()
    print('# cRED_log.txt')
    print(f'Timestamp:                {timestamp}')
    print(f'Start angle:              {start_angle:.2f} degrees')
    print(f'End angle:                {end_angle:.2f} degrees')
    print(f'Oscillation angle:        {osc_angle:.2f} degrees')
    print(f'Rotation speed:           {rotation_speed:.2f} degrees/s')
    print(
        f'Rotation axis at:         {rotation_axis:.2f} radians ({np.degrees(rotation_axis):.2f} degrees)'
    )
    print(f'Beamstop:                 {beamstop}')
    print(f'Pixelsize:                {pixelsize} px/Ångstrom')
    print(f'Physical Pixelsize:       {physical_pixelsize} mm')
    print(f'Wavelength:               {wavelength} Ångstrom')
    print(f'TEM Camera length:        {camera_length:.1f} mm')

    print()
    print('# TVIPS header')
    print(f'Camera:                   {camera}')
    print(f'Acquisition time:         {acquisition_time:.3f} s')
    print(f'Exposure time:            {exposure_time / 1000:.3f} s')
    print(f'Overhead time:            {overhead:.3f} s')
    print(f'Binning (X/Y):            {binning_x} {binning_y} px/bin')
    print(f'Image resolution (X/Y):   {image_res_x_tvips} {image_res_y_tvips} pixels')
    print(
        f'Pixelsize (X/Y):          {pixelsize_x_tvips:.5f} {pixelsize_y_tvips:.5f} px/Ångstrom???'
    )
    print(
        f'Physical pixelsize (X/Y): {physical_pixelsize_x_tvips} {physical_pixelsize_y_tvips} μm'
    )
    print(f'High tension:             {high_tension / 1000} kV')
    print(f'Wavelength:               {wavelength_tvips} Ångstrom')
    print(f'Camera length:            {camera_length_tvips} mm')

    # implement this later if it turns out to be necessary
    assert pixelsize_x_tvips == pixelsize_y_tvips, 'Pixelsize is different in X / Y direction'
    assert physical_pixelsize_x_tvips == physical_pixelsize_y_tvips, (
        'Physical pixelsize is different in X / Y direction'
    )

    buffer = []

    print()
    print('Reading data')
    for i, fn in enumerate(image_fns):
        j = i + 1  # j must be 1-indexed

        im = ims[i]
        h = hs[i]

        img = im.asarray()

        if img.dtype.type is np.int16:
            if img.min() >= 0 and img.max() < 2**16:
                img = img.astype(np.uint16)

        assert img.dtype.type is np.uint16, (
            f'Image (#{i}:{fn.stem}) dtype is {img.dtype} (must be np.uint16)'
        )

        h = {'ImageGetTime': timestamp, 'ImageExposureTime': exposure_time}

        buffer.append((j, img, h))

    print('Setting up image conversion')
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

    if beamstop:
        from instamatic.utils.beamstop import find_beamstop_rect

        print('Finding beam stop')
        stack_mean = np.mean(tuple(img_conv.data.values()), axis=0)
        img_conv.mean_beam_center
        beamstop_rect = find_beamstop_rect(
            stack_mean, img_conv.mean_beam_center, pad=1, savefig=True, drc=drc
        )
        img_conv.add_beamstop(beamstop_rect)

    if mrc_path:
        mrc_path = drc / mrc_path
    if smv_path:
        smv_path = drc / smv_path
    if tiff_path:
        tiff_drc_name = tiff_path
        tiff_path = drc / tiff_path
    if pets_path:
        pets_path = drc / pets_path

    print('Writing data')
    img_conv.threadpoolwriter(
        tiff_path=tiff_path, mrc_path=mrc_path, smv_path=smv_path, workers=8
    )

    print('Writing input files')
    if mrc_path:
        img_conv.write_ed3d(mrc_path)
        img_conv.write_REDp_shiftcorrection(mrc_path)

    if smv_path:
        img_conv.write_xds_inp(smv_path)
        # img_conv.to_dials(smv_path)

    if tiff_path:
        img_conv.write_pets_inp(path=drc, tiff_path=tiff_drc_name)

    if pets_path:
        pets_tiff_path = '../tiff'
        img_conv.write_pets2_inp(pets_path, tiff_path=pets_tiff_path)

    img_conv.write_beam_centers(path=drc)


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
