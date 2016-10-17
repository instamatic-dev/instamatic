from TiffIO import TiffIO
import time

def write_tiff(fname, data, header=None):
    """
    Overrides the FabioImage.write method and provides a simple TIFF image writer.
    @param fname: name of the file to save the image to
    @tag_type fname: string or unicode (file?)...
    """
    tiffIO = TiffIO(fname, mode="w")
    tiffIO.writeImage(data, info=header, software="instamatic", date=time.ctime())
