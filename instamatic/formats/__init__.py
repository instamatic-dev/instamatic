from TiffIO import TiffIO
import time
import os
import yaml
import numpy as np

try:
    import h5py
except ImportError:
    pass


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
    root, ext = os.path.splitext(fname)
    if isinstance(header, dict):
        header = yaml.dump(header)
    if not header:
        header = ""

    if ext == "":
        fname = root + ".tiff"
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
            print "Warning: could not read info from tiff header: {} (input={})".format(e, header.get("imageDescription"))
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
    root, ext = os.path.splitext(fname)

    if ext == "":
        fname = root + ".h5"

    f = h5py.File(fname, "w")
    h5data = f.create_dataset("data", data.shape, dtype=data.dtype)
    h5data[...] = data
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
    return np.array(f["data"]), dict(f.attrs)
