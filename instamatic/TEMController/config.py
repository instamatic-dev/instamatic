import yaml, json
import os

from instamatic import config
cfg_file = config.TEM_config

CFG = {}
CAMERA = None
CFG_CAMERA = []

specifications = None
lowmag_pixeldimensions = None
mag1_camera_dimensions = None
diffraction_pixeldimensions = None
camera_rotation_vs_stage_xy = None
stretch_azimuth = None
stretch_amplitude = None
wavelength = None

diffraction_pixelsize_fit_parameters = [ -3.72964471e-05,  -1.00023069e+00,   7.36028832e+04]

def load(fn=None, camera=None):
    if not fn:
        fn = cfg_file
    d = yaml.load(open(fn, "r"))

    if not camera:
        camera = d["cameras"][0]
    else:
        if not camera in d["cameras"]:
            raise ValueError("Camera {} not found in 'config' file.".format(camera))

    CFG.update(d)

    global CAMERA
    CAMERA = camera

    global specifications
    specifications = CFG["specifications"]

    global lowmag_pixeldimensions
    lowmag_pixeldimensions = CFG[CAMERA]["lowmag_pixeldimensions"]

    global mag1_camera_dimensions
    mag1_camera_dimensions = CFG[CAMERA]["mag1_camera_dimensions"]

    global diffraction_pixeldimensions
    diffraction_pixeldimensions = CFG[CAMERA]["diffraction_pixeldimensions"]
    
    global camera_rotation_vs_stage_xy
    camera_rotation_vs_stage_xy = CFG["camera_rotation_vs_stage_xy"]

    global stretch_azimuth
    stretch_azimuth = CFG["stretch_azimuth"]
    
    global stretch_amplitude
    stretch_amplitude = CFG["stretch_amplitude"]

    global wavelength
    wavelength = CFG["wavelength"]

    global CFG_CAMERA
    fn = config.get_camera_config(camera)
    CFG_CAMERA = json.load(open(fn))

load()

# config.camera
# config.TEM
# config.calibration
