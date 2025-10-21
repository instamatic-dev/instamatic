from __future__ import annotations

import collections
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from instamatic import config
from instamatic._typing import AnyPath
from instamatic.formats import read_tiff, write_adsc, write_mrc, write_tiff
from instamatic.processing.flatfield import apply_flatfield_correction
from instamatic.processing.PETS_input_factory import PetsInputFactory
from instamatic.processing.stretch_correction import affine_transform_ellipse_to_circle
from instamatic.tools import (
    find_beam_center,
    find_beam_center_with_beamstop,
    find_subranges,
    to_xds_untrusted_area,
)

logger = logging.getLogger(__name__)


def rotation_axis_to_xyz(rotation_axis, invert=False, setting='xds'):
    """Convert rotation axis angle to XYZ vector compatible with 'xds', or
    'dials' Set invert to 'True' for anti-clockwise rotation."""
    if invert:
        rotation_axis += np.pi

    rot_x = np.cos(rotation_axis)
    rot_y = np.sin(rotation_axis)
    rot_z = 0

    if setting == 'dials':
        return rot_x, rot_y, rot_z
    elif setting == 'xds':
        return rot_x, -rot_y, rot_z
    else:
        raise ValueError("Must be one of {'dials', 'xds'}")


def export_dials_variables(path, *, sequence=(), missing=(), rotation_xyz=None):
    """Export variables for DIALS to account for missing frames writes
    dials_variables.sh (bash) and dials_variables.bat (cmd)

    `sequence` is a tuple of sequence numbers of the data frames
    `missing `is a tuple of sequence numbers of the missing frames
    """
    scanranges = find_subranges(sequence)

    scanrange = ' '.join(f'scan_range={i},{j}' for i, j in scanranges)
    excludeimages = ','.join(str(n) for n in missing)

    if rotation_xyz:
        rot_x, rot_y, rot_z = rotation_xyz

    # newline='\n' to have unix line endings
    with open(path / 'dials_variables.sh', 'w', newline='\n') as f:
        print('#!/usr/bin/env bash', file=f)
        print(f"scan_range='{scanrange}'", file=f)
        print(f"exclude_images='exclude_images={excludeimages}'", file=f)
        if rotation_xyz:
            print(
                f"rotation_axis='geometry.goniometer.axes={rot_x:.4f},{rot_y:.4f},{rot_z:.4f}'",
                file=f,
            )
        print('#', file=f)
        print('# To run:', file=f)
        print('#     source dials_variables.sh', file=f)
        print('#', file=f)
        print('# and:', file=f)
        print('#     dials.import directory=data $rotation_axis', file=f)
        print('#     dials.find_spots datablock.json $scan_range', file=f)
        print('#     dials.integrate $exclude_images refined.pickle refined.json', file=f)
        print('#', file=f)

    with open(path / 'dials_variables.bat', 'w', newline='\n') as f:
        print('@echo off', file=f)
        print('', file=f)
        print(f'set scan_range={scanrange}', file=f)
        print(f'set exclude_images=exclude_images={excludeimages}', file=f)
        if rotation_xyz:
            print(
                f'set rotation_axis=geometry.goniometer.axes={rot_x:.4f},{rot_y:.4f},{rot_z:.4f}',
                file=f,
            )
        print('', file=f)
        print(':: To run:', file=f)
        print('::     call dials_variables.bat', file=f)
        print('::', file=f)
        print('::     dials.import directory=data %rotation_axis%', file=f)
        print('::     dials.find_spots datablock.json %scan_range%', file=f)
        print('::     dials.integrate %exclude_images% refined.pickle refined.json', file=f)


def get_calibrated_rotation_speed(val):
    """Correct for the overestimation of the oscillation angle if the rotation
    was stopped before interrupting the data collection.

    It uses calibrated values for the rotation speeds of the microscope,
    and matches them to the observed one
    """

    rotation_speeds = set(
        config.microscope.rotation_speeds['coarse'] + config.microscope.rotation_speeds['fine']
    )
    calibrated_value = min(rotation_speeds, key=lambda x: abs(x - val))
    logger.info(
        f'Correcting oscillation angle from {val:.3f} to calibrated value {calibrated_value:.3f}'
    )
    return calibrated_value


class ImgConversion:
    """This class is for post RED/cRED data collection image conversion. Files
    can be generated for REDp, DIALS, XDS, and PETS.

    The image buffer is passed as a list of tuples, where each tuple
    contains the index (int), image data (2D numpy array),
    metadata/header (dict). The buffer index must start at 1.
    """

    def __init__(
        self,
        buffer: list,  # image buffer, list of (index [int], image data [2D numpy array], header [dict])
        camera_length: float,  # virtual camera length read from the microscope
        osc_angle: float,  # degrees, oscillation angle of the rotation
        start_angle: float,  # degrees, start angle of the rotation
        end_angle: float,  # degrees, end angle of the rotation
        rotation_axis: float,  # radians, specifies the position of the rotation axis
        acquisition_time: float,  # seconds, acquisition time (exposure time + overhead)
        flatfield: str = 'flatfield.tiff',
        method: str = 'continuous-rotation 3D ED',  # or 'stills' or 'precession', used for CIF/documentation
    ):
        if flatfield is not None:
            flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.headers = {}
        self.data = {}

        self.smv_subdrc = 'data'

        while len(buffer) != 0:
            i, img, h = buffer.pop(0)

            self.headers[i] = h

            if self.flatfield is not None:
                self.data[i] = apply_flatfield_correction(img, self.flatfield)
            else:
                self.data[i] = img

        self.untrusted_areas = []

        self.observed_range = set(self.data.keys())
        self.complete_range = set(range(min(self.observed_range), max(self.observed_range) + 1))
        self.missing_range = self.observed_range ^ self.complete_range

        self.data_shape = img.shape
        try:
            self.pixelsize = config.calibration['diff']['pixelsize'][
                camera_length
            ]  # px / Angstrom
        except KeyError:
            self.pixelsize = 1
            print(
                f'No calibrated pixelsize for camera length={camera_length}. Setting pixelsize to 1.'
            )
            logger.warning(
                f'No calibrated pixelsize for camera length={camera_length}. Setting pixelsize to 1.'
            )

        self.physical_pixelsize = config.camera.physical_pixelsize  # mm
        self.wavelength = config.microscope.wavelength  # angstrom
        # NOTE: Stretch correction - not sure if the azimuth and amplitude are correct anymore.
        self.do_stretch_correction = True
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        self.distance = (1 / self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osc_angle = osc_angle
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.rotation_axis = rotation_axis

        self.acquisition_time = acquisition_time
        # self.rotation_speed = get_calibrated_rotation_speed(osc_angle / self.acquisition_time)

        self.name = 'Instamatic'
        self.method = method

        from .XDS_template import (
            XDS_template,  # hook XDS_template here, because it is difficult to override as a global
        )

        self.XDS_template = XDS_template

        self.check_settings()  # check if all required parameters are present, and fill default values if needed

        self.mean_beam_center, self.beam_center_std = self.get_beam_centers()
        logger.debug(f'Primary beam at: {self.mean_beam_center}')

    def check_settings(self) -> None:
        """Check for the presence of all required attributes.

        If possible, optional missing attributes are set to their
        defaults.
        """

        kw_attrs = {
            'name': 'instamatic',
            'use_beamstop': False,
            'untrusted_areas': [],
            'smv_subdrc': 'data',
            'do_stretch_correction': False,
        }

        for attr, default in kw_attrs.items():
            if not hasattr(self, attr):
                print(f'self.{attr} = {default}')
                setattr(self, attr, default)

        attrs = [
            # "rotation_speed",
            'acquisition_time',
            'start_angle',
            'end_angle',
            'osc_angle',
            'distance',
            'mean_beam_center',
            'wavelength',
            'physical_pixelsize',
            'pixelsize',
            'data_shape',
            'missing_range',
            'complete_range',
            'observed_range',
            'headers',
            'data',
            'XDS_template',
        ]

        for attr in attrs:
            if not hasattr(self, attr):
                raise AttributeError(f'`{self.__class__.__name__}` has no attribute `{attr}`')

        if self.do_stretch_correction:
            stretch_attrs = ('stretch_amplitude', 'stretch_azimuth')
            if not all(hasattr(self, attr) for attr in stretch_attrs):
                raise AttributeError(
                    f'`{self.__class__.__name__}` is missing stretch attrs `{stretch_attrs[0]}/{stretch_attrs[1]}`'
                )

    def get_beam_centers(
        self, invert_x: bool = False, invert_y: bool = False
    ) -> (float, float):
        """Obtain beam centers from the diffraction data Returns a tuple with
        the median beam center and its standard deviation."""
        shape_x, shape_y = self.data_shape
        centers = []
        for i, h in self.headers.items():
            if self.use_beamstop:
                cx, cy = find_beam_center_with_beamstop(self.data[i], z=99)
            else:
                cx, cy = find_beam_center(self.data[i], sigma=10)

            if invert_x:
                cx = shape_x - cx
            if invert_y:
                cy = shape_y - cy

            h['beam_center'] = (float(cx), float(cy))
            centers.append((cx, cy))

        self._beam_centers = beam_centers = np.array(centers)

        # avg_center = np.mean(centers, axis=0)
        median_center = np.median(beam_centers, axis=0)
        std_center = np.std(beam_centers, axis=0)

        return median_center, std_center

    def write_geometric_correction_files(self, path) -> None:
        """Make geometric correction images for XDS Writes files XCORR.cbf and
        YCORR.cbf to `path`

        To use:
            DETECTOR= PILATUS     ! fake being a PILATUS detector
            X-GEO_CORR= XCORR.cbf
            Y-GEO_CORR= YCORR.cbf

        Reads the stretch amplitude/azimuth from the config file
        """
        from instamatic.formats import write_cbf

        center = np.array(self.mean_beam_center)

        amplitude_pc = self.stretch_amplitude / (2 * 100)

        # To create the correct corrections the azimuth is mirrored
        azimuth_rad = np.radians(180 - self.stretch_azimuth)

        shape = self.data_shape

        xi, yi = np.mgrid[0 : shape[0], 0 : shape[1]]
        coords = np.stack([xi.flatten(), yi.flatten()], axis=1) - center

        s = affine_transform_ellipse_to_circle(azimuth_rad, amplitude_pc)

        new = np.dot(coords, s)

        xcorr = (new[:, 0].reshape(shape) + center[0]) - xi
        ycorr = (new[:, 1].reshape(shape) + center[1]) - yi

        # reverse XY coordinates for XDS
        xcorr, ycorr = ycorr, xcorr

        # In XDS, the geometrically corrected coordinates of a pixel at IX,IY
        # are found by adding the table_value(IX,IY)/100.0 for the X- and Y-tables, respectively.
        write_cbf(path / 'XCORR.cbf', np.int32(xcorr * 100))
        write_cbf(path / 'YCORR.cbf', np.int32(ycorr * 100))

    def tiff_writer(self, path: Path) -> None:
        """Write all data as tiff files to given `path`"""
        print('\033[k', 'Writing TIFF files......', end='\r')

        path.mkdir(exist_ok=True)

        for i in self.observed_range:
            self.write_tiff(path, i)

        logger.debug(f'Tiff files saved in folder: {path}')

    def smv_writer(self, path: Path) -> None:
        """Write all data as SMV files compatible with XDS/DIALS to `path`"""
        print('\033[k', 'Writing SMV files......', end='\r')

        path = path / self.smv_subdrc
        path.mkdir(exist_ok=True)

        for i in self.observed_range:
            self.write_smv(path, i)

        logger.debug(f'SMV files saved in folder: {path}')

    def mrc_writer(self, path: Path) -> None:
        """Write all data as mrc files to `path`"""
        print('\033[k', 'Writing MRC files......', end='\r')

        path.mkdir(exist_ok=True)

        for i in self.observed_range:
            self.write_mrc(path, i)

        logger.debug(f'MRC files created in folder: {path}')

    def threadpoolwriter(
        self,
        tiff_path: Optional[Path] = None,
        smv_path: Optional[Path] = None,
        mrc_path: Optional[Path] = None,
        workers: int = 8,
    ) -> None:
        """Efficiently write all data to the specified formats using a
        threadpool.

        If a path is given, write data in the corresponding format, i.e.
        if `tiff_path` is specified TIFF files are written to that path.
        """
        write_tiff = tiff_path is not None
        write_smv = smv_path is not None
        write_mrc = mrc_path is not None

        if write_smv:
            smv_path = smv_path / self.smv_subdrc
            smv_path.mkdir(exist_ok=True, parents=True)
            logger.debug(f'SMV files saved in folder: {smv_path}')

        if write_tiff:
            tiff_path.mkdir(exist_ok=True, parents=True)
            logger.debug(f'Tiff files saved in folder: {tiff_path}')

        if write_mrc:
            mrc_path.mkdir(exist_ok=True, parents=True)
            logger.debug(f'MRC files saved in folder: {mrc_path}')

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for i in self.observed_range:
                if write_tiff:
                    futures.append(executor.submit(self.write_tiff, tiff_path, i))
                if write_mrc:
                    futures.append(executor.submit(self.write_mrc, mrc_path, i))
                if write_smv:
                    futures.append(executor.submit(self.write_smv, smv_path, i))

            for future in futures:
                ret = future.result()

    def to_dials(self, smv_path: Path) -> None:
        """Convert the buffer to output compatible with DIALS.

        Files are written to the path given by `smv_path`.
        """
        observed_range = self.observed_range
        self.missing_range = self.missing_range

        invert_rotation_axis = self.start_angle > self.end_angle
        rotation_xyz = rotation_axis_to_xyz(
            self.rotation_axis, invert=invert_rotation_axis, setting='dials'
        )

        export_dials_variables(
            smv_path,
            sequence=observed_range,
            missing=self.missing_range,
            rotation_xyz=rotation_xyz,
        )

        path = smv_path / self.smv_subdrc

        i = min(observed_range)
        empty = np.zeros_like(self.data[i])
        # copy header from first frame
        h = self.headers[i].copy()
        h['ImageGetTime'] = time.time()

        # add data to self.data/self.headers so that existing functions can be used
        # make sure to remove them afterwards, not to interfere with other data writing
        logger.debug(f'Writing missing files for DIALS: {self.missing_range}')

        for n in self.missing_range:
            self.data[n] = empty
            self.headers[n] = h

            self.write_smv(path, n)

            del self.data[n]
            del self.headers[n]

    def write_tiff(self, path: Path, i: int) -> Path:
        """Write the image+header with sequence number `i` to the directory
        `path` in TIFF format.

        Returns the path to the written image.
        """
        img = self.data[i]
        h = self.headers[i]

        fn = path / f'{i:05d}.tiff'
        write_tiff(str(fn), img, header=h)
        return fn

    def write_smv(self, path: Path, i: int) -> Path:
        """Write the image+header with sequence number `i` to the directory
        `path` in SMV format.

        Returns the path to the written image.
        """
        img = self.data[i]
        h = self.headers[i]

        img = np.ushort(img)
        shape_x, shape_y = img.shape

        phi = self.start_angle + self.osc_angle * (i - 1)

        # TODO: Dials reads the beam_center from the first image and uses that for the whole range
        # For now, use the average beam center and consider it stationary, remove this line later
        mean_beam_center = self.mean_beam_center

        try:
            date = str(datetime.fromtimestamp(h['ImageGetTime']))
        except BaseException:
            date = '0'

        header = collections.OrderedDict()
        header['HEADER_BYTES'] = 512
        header['DIM'] = 2
        header['BYTE_ORDER'] = 'little_endian'
        header['TYPE'] = 'unsigned_short'
        header['SIZE1'] = shape_x
        header['SIZE2'] = shape_y
        header['PIXEL_SIZE'] = self.physical_pixelsize
        header['BIN'] = '1x1'
        header['BIN_TYPE'] = 'HW'
        header['ADC'] = 'fast'
        header['CREV'] = 1
        header['BEAMLINE'] = self.name  # special ID for DIALS
        header['DETECTOR_SN'] = 901  # special ID for DIALS
        header['DATE'] = date
        header['TIME'] = str(h['ImageExposureTime'])
        header['DISTANCE'] = f'{self.distance:.4f}'
        header['TWOTHETA'] = 0.00
        header['PHI'] = '{phi:.4f}'
        header['OSC_START'] = f'{phi:.4f}'
        header['OSC_RANGE'] = f'{self.osc_angle:.4f}'
        header['WAVELENGTH'] = f'{self.wavelength:.4f}'
        # reverse XY coordinates for XDS
        header['BEAM_CENTER_X'] = f'{mean_beam_center[1]:.4f}'
        header['BEAM_CENTER_Y'] = f'{mean_beam_center[0]:.4f}'
        header['DENZO_X_BEAM'] = f'{mean_beam_center[0] * self.physical_pixelsize:.4f}'
        header['DENZO_Y_BEAM'] = f'{mean_beam_center[1] * self.physical_pixelsize:.4f}'
        fn = path / f'{i:05d}.img'
        write_adsc(str(fn), img, header=header)
        return fn

    def write_mrc(self, path: Path, i: int) -> Path:
        """Write the image+header with sequence number `i` to the directory
        `path` in TIFF format.

        Returns the path to the written image.
        """
        img = self.data[i]

        fn = path / f'{i:05d}.mrc'

        # for RED these need to be as integers
        dtype = np.uint16
        if False:
            # Use maximum range available in data type for extra precision when converting from FLOAT to INT
            dynamic_range = 11900  # a little bit higher just in case
            maxval = np.iinfo(dtype).max
            img = (img / dynamic_range) * maxval

        img = np.round(img, 0).astype(dtype)

        # flip up/down because RED reads images from the bottom left corner
        img = np.flipud(img)

        write_mrc(fn, img)

        return fn

    def write_ed3d(self, path: Path) -> None:
        """Write .ed3d input file for REDp in directory `path`"""
        path.mkdir(exist_ok=True)

        omega = np.degrees(self.rotation_axis)
        omega = ((omega + 180) % 360) - 180  # for red, -180 <= omega <= 180
        sign = -1 if self.start_angle > self.end_angle else +1

        with open(path / '1.ed3d', 'w') as f:
            print(f'WAVELENGTH    {self.wavelength}', file=f)
            print(f'ROTATIONAXIS    {omega:5f}', file=f)
            print(f'CCDPIXELSIZE    {self.pixelsize:5f}', file=f)
            print(f'GONIOTILTSTEP    {self.osc_angle:5f}', file=f)
            print('BEAMTILTSTEP    0', file=f)
            print('BEAMTILTRANGE    0.000', file=f)
            print('STRETCHINGMP    0.0', file=f)
            print('STRETCHINGAZIMUTH    0.0', file=f)
            print('', file=f)
            print('FILELIST', file=f)

            for i in self.observed_range:
                fn = f'{i:05d}.mrc'
                angle = self.start_angle + sign * self.osc_angle * i
                print(f'FILE {fn}    {angle: 12.4f}    0    {angle: 12.4f}', file=f)

            print('ENDFILELIST', file=f)

        logger.debug(f'ED3D file created in path: {path}')

    def write_xds_inp(self, path: Path) -> None:
        """Write XDS.INP input file for XDS in directory `path`"""

        path.mkdir(exist_ok=True)

        nframes = max(self.complete_range)

        invert_rotation_axis = self.start_angle > self.end_angle
        rot_x, rot_y, rot_z = rotation_axis_to_xyz(
            self.rotation_axis, invert=invert_rotation_axis
        )

        shape_x, shape_y = self.data_shape

        if self.do_stretch_correction:
            self.write_geometric_correction_files(path)
            stretch_correction = 'DETECTOR= PILATUS      ! Pretend to be PILATUS detector to enable geometric corrections\nX-GEO_CORR= XCORR.cbf  ! X stretch correction\nY-GEO_CORR= YCORR.cbf  ! Y stretch correction\n'
        else:
            stretch_correction = ''

        if self.missing_range:
            exclude = '\n'.join(
                [f'EXCLUDE_DATA_RANGE={i} {j}' for i, j in find_subranges(self.missing_range)]
            )
        else:
            exclude = '!EXCLUDE_DATA_RANGE='

        untrusted_areas = ''

        for kind, coords in self.untrusted_areas:
            untrusted_areas += to_xds_untrusted_area(kind, coords) + '\n'

        s = self.XDS_template.format(
            date=str(time.ctime()),
            data_drc=self.smv_subdrc,
            data_begin=1,
            data_end=nframes,
            exclude=exclude,
            stretch_correction=stretch_correction,
            starting_angle=self.start_angle,
            wavelength=self.wavelength,
            # reverse XY coordinates for XDS
            origin_x=self.mean_beam_center[1],
            origin_y=self.mean_beam_center[0],
            untrusted_areas=untrusted_areas,
            NX=shape_y,
            NY=shape_x,
            sign='+',
            detector_distance=self.distance,
            QX=self.physical_pixelsize,
            QY=self.physical_pixelsize,
            osc_angle=self.osc_angle,
            rot_x=rot_x,
            rot_y=rot_y,
            rot_z=rot_z,
        )

        with open(path / 'XDS.INP', 'w') as f:
            print(s, file=f)

        logger.info('XDS INP file created.')

    def write_beam_centers(self, path: Path) -> None:
        """Write list of beam centers to file `beam_centers.txt` in `path`"""
        centers = np.zeros((max(self.observed_range), 2), dtype=float)
        for i, h in self.headers.items():
            centers[i - 1] = h['beam_center']
        for i in self.missing_range:
            centers[i - 1] = [np.nan, np.nan]

        np.savetxt(path / 'beam_centers.txt', centers, fmt='%10.4f')

    def write_pets_inp(self, path: AnyPath, tiff_path: str = 'tiff') -> None:
        sign = 1 if self.start_angle < self.end_angle else -1
        omega = np.degrees(self.rotation_axis) % 360

        if 'continuous' in self.method.lower():
            geometry = 'continuous'
        elif 'precess' in self.method.lower():
            geometry = 'precession'
        else:
            geometry = 'static'

        p = PetsInputFactory()
        p.add('geometry', geometry)
        p.add('lambda', self.wavelength)
        p.add('Aperpixel', self.pixelsize)
        p.add('phi', float(self.osc_angle) / 2)
        p.add('omega', omega)
        p.add('bin', 1)
        p.add('reflectionsize', 20)
        p.add('noiseparameters', 3.5, 38)
        p.add('')

        s = []
        for i in self.observed_range:
            angle = self.start_angle + sign * self.osc_angle * i
            s.append(f'{tiff_path}/{i:05d}.tiff {angle:10.4f} 0.00')
        p.add('imagelist', *s)

        with open(Path(path) / 'pets.pts', 'w') as f:
            f.write(str(p.compile(self.__dict__)))

    def write_REDp_shiftcorrection(self, path: Path) -> None:
        """Write .sc (shift correction) file for REDp in directory `path`"""
        path.mkdir(exist_ok=True)

        cx, cy = self.mean_beam_center
        with open(path / 'shifts.sc', 'w') as f:
            print(f' {cy:.2f} {cx:.2f}', file=f)  # cx/cy must be switched around, y first
            for i in self.observed_range:
                print(f'{i:4d}{0:8.2f}{0:8.2f}', file=f)

    def add_beamstop(self, rect):
        """Rect must be a 2x4 coordinate array."""
        self.untrusted_areas.append(('quadrilateral', rect))
