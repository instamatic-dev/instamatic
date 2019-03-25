from .ImgConversion import *


class ImgConversionTPX(ImgConversion):
    """This class is for post RED/cRED data collection image conversion.
    Files can be generated for REDp, DIALS, XDS, and PETS.

    The image buffer is passed as a list of tuples, where each tuple contains the
    index (int), image data (2D numpy array), metadata/header (dict).
    The buffer index must start at 1.
    """

    def __init__(self, 
                 buffer: list,                   # image buffer, list of (index [int], image data [2D numpy array], header [dict])
                 camera_length: float,           # virtual camera length read from the microscope
                 osc_angle: float,               # degrees, oscillation angle of the rotation
                 start_angle: float,             # degrees, start angle of the rotation
                 end_angle: float,               # degrees, end angle of the rotation
                 rotation_axis: float,           # radians, specifies the position of the rotation axis
                 acquisition_time: float,        # seconds, acquisition time (exposure time + overhead)
                 flatfield: str='flatfield.tiff'  
                 ):
        if flatfield is not None:
            flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.headers = {}
        self.data = {}

        self.smv_subdrc = "data"

        self.untrusted_areas = [ ("rectangle", ((0,   255), (517, 262)) ),
                                 ("rectangle", ((255, 0  ), (262, 517)) ) ]


        while len(buffer) != 0:
            i, img, h = buffer.pop(0)

            self.headers[i] = h

            if self.flatfield is not None:
                self.data[i] = apply_flatfield_correction(img, self.flatfield)
            else:
                self.data[i] = img

        self.observed_range = set(self.data.keys())
        self.complete_range = set(range(min(self.observed_range), max(self.observed_range) + 1))
        self.missing_range = self.observed_range ^ self.complete_range

        self.data_shape = img.shape
        try:
            self.pixelsize = config.calibration.diffraction_pixeldimensions[camera_length] # px / Angstrom
        except KeyError:
            self.pixelsize = 1
            print("No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length))
            logger.warning("No calibrated pixelsize for camera length={}. Setting pixelsize to 1.".format(camera_length))

        self.physical_pixelsize = config.camera.physical_pixelsize # mm
        self.wavelength = config.microscope.wavelength # angstrom
        # NOTE: Stretch correction - not sure if the azimuth and amplitude are correct anymore.
        self.stretch_azimuth = config.camera.stretch_azimuth
        self.stretch_amplitude = config.camera.stretch_amplitude

        self.mean_beam_center, self.beam_center_std = self.get_beam_centers()
        self.distance = (1/self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osc_angle = osc_angle
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.rotation_axis = rotation_axis
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = get_calibrated_rotation_speed(osc_angle / self.acquisition_time) 

        logger.debug("Primary beam at: {}".format(self.mean_beam_center))

        self.name = "TimePix_SU"

        from .XDS_templateTPX import XDS_template
        self.XDS_template = XDS_template

        self.check_settings()
