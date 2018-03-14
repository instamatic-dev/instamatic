from .TiffIO import TiffIO
import time
import os
import yaml
import numpy as np
from pathlib import Path

from .csvIO import read_csv, write_csv, read_ycsv, write_ycsv, yaml_ordered_load, yaml_ordered_dump
from .adscimage import write_adsc, read_adsc

import warnings
with warnings.catch_warnings():
    # TODO: remove me later
    # Catch annoying futurewarning on import
    warnings.simplefilter("ignore")
    import h5py

from .mrc import read_image as read_mrc
from .mrc import write_image as write_mrc


def read_image(fname):
    """Guess filetype by extension"""
    ext = Path(fname).suffix.lower()
    if ext in (".tif", ".tiff"):
        img, h = read_tiff(fname)
    elif ext in (".h5", ".hdf5"):
        img, h = read_hdf5(fname)
    elif ext in (".img", ".smv"):
        img, h = read_adsc(fname)
    elif ext in (".mrc"):
        img, h = read_mrc(fname)
    else:
        raise IOError(f"Cannot open file {fname}, unknown extension: {ext}")
    return img, h 


def write_tiff(fname, data, header=None):
    """Simple function to write a tiff file

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
        header = "No description"

    fname = Path(fname).with_suffix(".tiff")

    tiffIO = TiffIO(fname, mode="w")
    tiffIO.writeImage(data, info=header, software="instamatic", date=time.ctime())


def read_tiff(fname):
    """Simple function to read a tiff file

    fname: str,
        path or filename to image which should be opened

    Returns:
        image: np.ndarray, header: dict
            a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes
    """

    tiff = TiffIO(fname)
    img = tiff.getImage(0)
    header = tiff.getInfo(0)

    if "imageDescription" in header:
        try:
            d = yaml.load(header.get("imageDescription"))
        except (Exception, ValueError) as e:
            print("Warning: could not read info from tiff header: {} (input={})".format(e, header.get("imageDescription")))
        else:
            if isinstance(d, dict):
                header.update(d)
                del header["imageDescription"]

    return img, header


def write_hdf5(fname, data, header=None):
    """Simple function to write data to hdf5 format using h5py

    fname: str,
        path or filename to which the image should be saved
    data: np.ndarray,
        numpy array containing image data (path="/data")
    header: dict,
        dictionary containing the metadata that should be saved
        key/value pairs are stored as attributes on the data
        """
    fname = Path(fname).with_suffix(".h5")

    f = h5py.File(fname, "w")
    h5data = f.create_dataset("data", data=data)
    if header:
        h5data.attrs.update(header)
    f.close()
 

def read_hdf5(fname):
    """Simple function to read a hdf5 file written by Instamatic
    
    fname: str,
        path or filename to image which should be opened

    Returns:
        image: np.ndarray, header: dict
            a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes
    """
    f = h5py.File(fname)
    return np.array(f["data"]), dict(f["data"].attrs)
