from .ImgConversion import *


class ImgConversionTVIPS(ImgConversion):
    """This class is for converting data collected with a TVIPS camera
    Files can be generated for REDp, DIALS, XDS, and PETS.

    The image buffer is passed as a list of tuples, where each tuple contains the
    index (int), image data (2D numpy array), metadata/header (dict).
    The buffer index must start at 1.
    """

    def __init__(self, 
                 buffer: list,                   # image buffer, list of (index [int], image data [2D numpy array], header [dict])
                 osc_angle: float,               # degrees, oscillation angle of the rotation
                 start_angle: float,             # degrees, start angle of the rotation
                 end_angle: float,               # degrees, end angle of the rotation
                 rotation_axis: float,           # radians, specifies the position of the rotation axis
                 acquisition_time: float,        # seconds, acquisition time (exposure time + overhead)
                 flatfield: str='flatfield.tiff',
                 pixelsize: float=None,          # p/Angstrom, size of the pixels (overrides camera_length)
                 physical_pixelsize: float=None, # mm, physical size of the pixels (overrides camera length)
                 wavelength: float=None,         # Angstrom, relativistic wavelength of the electron beam
                 ):
        if flatfield is not None:
            flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.headers = {}
        self.data = {}

        self.smv_subdrc = "data"

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

        self.pixelsize = pixelsize
        self.physical_pixelsize = physical_pixelsize
        self.wavelength = wavelength
        
        self.use_beamstop = True
        self.mean_beam_center, self.beam_center_std = self.get_beam_centers()

        self.distance = (1/self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osc_angle = osc_angle
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.rotation_axis = rotation_axis
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = 0  # n/a

        logger.debug("Primary beam at: {}".format(self.mean_beam_center))

        self.name = "TVIPS F416"

        from .XDS_templateTVIPS import XDS_template
        self.XDS_template = XDS_template

        self.check_settings()
