from TiffIO import TiffIO
import time
import os
import yaml

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
    if isinstance(header, dict):
        header = yaml.dump(header)

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
    header = tiff.getInfo(0)

    info = header.pop("ImageDescription", None)
    if info:
        try:
            header.update(yaml.load(info))
        except ValueError as e:
            print e, info

    return img, header