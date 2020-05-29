import logging

import numpy as np
from skimage.registration import phase_cross_correlation
from tqdm.auto import tqdm

from instamatic.calibrate.fit import fit_affine_transformation
logger = logging.getLogger(__name__)


def Calibrate_Imageshift(ctrl, diff_defocus, stepsize, logger, key='IS1'):

    if key != 'S':
        input(f"""Calibrate {key}
    -------------------
     1. Go to diffraction mode.
     2. Focus the diffraction spots.
     3. Center the beam with PLA.

     >> Press <ENTER> to start >> \n""")
    else:
        input("""Calibrate stage vs camera
        ------------------
        1. Go to mag1.
        2. Find area with particles.

        >> Press <ENTER> to start >> \n""")

    d = {'IS1': ctrl.imageshift1,
         'IS2': ctrl.imageshift2,
         'BS': ctrl.beamshift,
         'S': ctrl.stage}

    if diff_defocus != 0:
        diff_focus_proper = ctrl.difffocus.value
        diff_focus_defocused = diff_focus_proper + diff_defocus
        ctrl.difffocus.value = diff_focus_defocused

    deflector = d[key]

    if key != 'S':
        x0, y0 = deflector.get()
        scaling = True
    else:
        x0 = deflector.x
        y0 = deflector.y
        scaling = False

    img_cent, h_cent = ctrl.get_image(exposure=0.01, comment='Beam in center of image')

    shifts = []
    imgpos = []
    stepsize = stepsize

    for i in tqdm(range(0, 5)):
        for j in range(0, 5):
            deflector.set(x=x0 + (i - 2) * stepsize, y=y0 + (j - 2) * stepsize)
            img, h = ctrl.get_image(exposure=0.01, comment='imageshifted image')

            shift, error, phasediff = phase_cross_correlation(img_cent, img, upsample_factor=10)
            imgshift = np.array(((i - 2) * stepsize, (j - 2) * stepsize))
            imgpos.append(imgshift)
            shifts.append(shift)

    deflector.set(x=x0, y=y0)

    fit_result = fit_affine_transformation(shifts, imgpos, scaling=scaling)

    r = fit_result.r
    t = fit_result.t

    if diff_defocus != 0:
        ctrl.difffocus.value = diff_focus_proper

    print('ImageShift calibration done.')

    print('Transformation matrix: ', r)
    logger.debug(f'Transformation matrix: {r}')
    logger.debug(f'Parameters: angle: {fit_result.angle}')
    logger.debug(f'sx: {fit_result.sx}')
    logger.debug(f'sy: {fit_result.sy}')
    logger.debug(f'tx: {fit_result.tx}')
    logger.debug(f'ty: {fit_result.ty}')
    logger.debug(f'k1: {fit_result.k1}')
    logger.debug(f'k2: {fit_result.k2}')

    r_i = np.linalg.inv(r)
    imgpos_ = np.dot(imgpos, r_i)
    shifts = np.array(shifts)
    imgpos_ = np.array(imgpos_)

    c = [imgpos_, shifts]

    return r, c


def Calibrate_Imageshift2(ctrl, diff_defocus, stepsize, logger):
    return Calibrate_Imageshift(ctrl=ctrl, diff_defocus=diff_defocus, stepsize=stepsize, logger=logger, key='IS2')


def Calibrate_Beamshift_D(ctrl, stepsize, logger):
    return Calibrate_Imageshift(ctrl=ctrl, diff_defocus=0, stepsize=stepsize, logger=logger, key='BS')


def Calibrate_Beamshift_D_Defoc(ctrl, diff_defocus, stepsize, logger):
    return Calibrate_Imageshift(ctrl=ctrl, diff_defocus=diff_defocus, stepsize=stepsize, logger=logger, key='BS')


def Calibrate_Stage(ctrl, stepsize, logger):
    if ctrl.mode != 'mag1':
        ctrl.mode.set('mag1')
    ctrl.brightness.value = 65535
    return Calibrate_Imageshift(ctrl=ctrl, diff_defocus=0, stepsize=stepsize, logger=logger, key='S')
