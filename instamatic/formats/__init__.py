import os
import warnings
from pathlib import Path

import h5py
import numpy as np
import tifffile
import yaml

from .adscimage import read_adsc
from .adscimage import write_adsc
from .csvIO import read_csv
from .csvIO import read_ycsv
from .csvIO import write_csv
from .csvIO import write_ycsv
from .mrc import read_image as read_mrc
from .mrc import write_image as write_mrc
from .xdscbf import write as write_cbf


def read_image(fname: str) -> (np.array, dict):
    """Guess filetype by extension."""
    ext = Path(fname).suffix.lower()
    if ext in ('.tif', '.tiff'):
        img, h = read_tiff(fname)
    elif ext in ('.h5', '.hdf5'):
        img, h = read_hdf5(fname)
    elif ext in ('.img', '.smv'):
        img, h = read_adsc(fname)
    elif ext in ('.mrc'):
        img, h = read_mrc(fname)
    elif ext in ('.cbf'):
        img, h = read_cbf(fname)
    else:
        raise OSError(f'Cannot open file {fname}, unknown extension: {ext}')
    return img, h


def write_tiff(fname: str, data, header: dict = None):
    """Simple function to write a tiff file.

    fname: str,
        path or filename to which the image should be saved
    data: np.ndarray,
        numpy array containing image data
    header: dict,
        dictionary containing the metadata that should be saved
        key/value pairs are stored as yaml in the TIFF ImageDescription tag
    """
    if isinstance(header, dict):
        header = yaml.dump(header)
    if not header:
        header = ''

    fname = Path(fname).with_suffix('.tiff')

    with tifffile.TiffWriter(fname) as f:
        f.save(data=data, software='instamatic', description=header)


def read_tiff(fname: str) -> (np.array, dict):
    """Simple function to read a tiff file.

    fname: str,
        path or filename to image which should be opened

    Returns:
        image: np.ndarray, header: dict
            a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes
    """
    tiff = tifffile.TiffFile(fname)

    page = tiff.pages[0]
    img = page.asarray()

    if page.software == 'instamatic':
        header = yaml.load(page.tags['ImageDescription'].value, Loader=yaml.Loader)
    elif tiff.is_tvips:
        header = tiff.tvips_metadata
    else:
        header = {}

    return img, header


def write_hdf5(fname: str, data, header: dict = None):
    """Simple function to write data to hdf5 format using h5py.

    fname: str,
        path or filename to which the image should be saved
    data: np.ndarray,
        numpy array containing image data (path="/data")
    header: dict,
        dictionary containing the metadata that should be saved
        key/value pairs are stored as attributes on the data
    """
    fname = Path(fname).with_suffix('.h5')

    f = h5py.File(fname, 'w')
    h5data = f.create_dataset('data', data=data)
    if header:
        h5data.attrs.update(header)
    f.close()


def read_hdf5(fname: str) -> (np.array, dict):
    """Simple function to read a hdf5 file written by Instamatic.

    fname: str,
        path or filename to image which should be opened

    Returns:
        image: np.ndarray, header: dict
            a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes
    """
    if not os.path.exists(fname):
        raise FileNotFoundError(f"No such file: '{fname}'")

    f = h5py.File(fname, 'r')
    return np.array(f['data']), dict(f['data'].attrs)


def read_cbf(fname: str):
    """CBF reader not implemented."""
    raise NotImplementedError('CBF reader not implemented.')
