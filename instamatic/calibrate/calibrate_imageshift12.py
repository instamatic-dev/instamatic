# coding: future_fstrings 

from instamatic.calibrate.fit import fit_affine_transformation
from instamatic.processing.cross_correlate import cross_correlate
import numpy as np

import logging
logger = logging.getLogger(__name__)


def Calibrate_Imageshift(ctrl, diff_defocus, stepsize):

    inp = input("""Calibrate ImageShift
-------------------
 1. Go to diffraction mode.
 2. Focus the diffraction spots.
 3. Center the beam with PLA.
 4. Fill in the desired defocus value.
    
 >> Press <ENTER> to start >> \n""")
    
    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_focus_proper + diff_defocus 
        ctrl.difffocus.value = diff_focus_defocused
    
    x0, y0 = ctrl.imageshift1.get()
    img_cent, h_cent = ctrl.getImage(exposure=0.01, comment="Beam in center of image")

    shifts = []
    imgpos = []
    stepsize = stepsize
    
    for i in range(0, 5):
        for j in range(0, 5):
            ctrl.imageshift1.set(x= x0 + (i-2)*stepsize, y= y0 + (j-2)*stepsize)
            img, h = ctrl.getImage(exposure = 0.01, comment = "imageshifted image")

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
            imgshift = np.array(((i-2)*stepsize, (j-2)*stepsize))
            imgpos.append(imgshift)
            shifts.append(shift)

    ctrl.imageshift1.set(x = x0, y = y0)
    
    r, t = fit_affine_transformation(shifts, imgpos)
    
    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper
    
    print("ImageShift calibration done.")
    print(r)

    return r

def Calibrate_Imageshift2(ctrl, diff_defocus, stepsize):

    inp = input("""Calibrate ImageShift2
-------------------
 1. Go to diffraction mode.
 2. Focus the diffraction spots.
 3. Center the beam with PLA.
 4. Fill in the desired defocus value.
    
 >> Press <ENTER> to start >> \n""")
    
    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_focus_proper + diff_defocus 
        ctrl.difffocus.value = diff_focus_defocused
    
    x0, y0 = ctrl.imageshift2.get()
    img_cent, h_cent = ctrl.getImage(exposure=0.01, comment="Beam in center of image")

    shifts = []
    imgpos = []
    stepsize = stepsize
    
    for i in range(0, 5):
        for j in range(0, 5):
            ctrl.imageshift2.set(x= x0 + (i-2)*stepsize, y= y0 + (j-2)*stepsize)
            img, h = ctrl.getImage(exposure = 0.01, comment = "imageshifted image")

            shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
            imgshift = np.array(((i-2)*stepsize, (j-2)*stepsize))
            imgpos.append(imgshift)
            shifts.append(shift)

    ctrl.imageshift2.set(x = x0, y = y0)
    
    r, t = fit_affine_transformation(shifts, imgpos)
    
    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper
    
    print("ImageShift2 calibration done.")
    print(r)

    return r