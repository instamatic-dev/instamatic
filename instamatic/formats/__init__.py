from TiffIO import TiffIO
import time
import os

def write_tiff(fname, data, header=None):
    """Simple function to write a tiff file

    fname: str,
        path or filename to which the image should be saved
    data: np.ndarray,
        numpy array containing image data
    header: dict,
        dictionary containing the custom tags that should be saved
        key/value pairs are stored as yaml in the TIFF ImageDescription tag
    """
    root, ext = os.path.splitext(fname)
    if ext == "":
        fname = root + ".tiff"
    tiffIO = TiffIO(fname, mode="w")
    tiffIO.writeImage(data, info=header, software="instamatic", date=time.ctime())

def read_tiff(fname):
    """Simple function to read a tiff file

    fname: str,
        path or filename to image which should be opened

    Returns:
        image: np.ndarray, headerfile: dict
            a tuple of the image as numpy array and dictionary with all the tem parameters and image attributes
    """
    tiff = TiffIO(fname)
    img = tiff.getImage(0)
    h = tiff.getInfo(0)
    return img, h