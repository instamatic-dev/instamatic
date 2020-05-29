import time

import numpy as np
from skimage.registration import phase_cross_correlation

from instamatic.processing.find_crystals import find_crystals_timepix


def reject_outlier(data, m=2):
    """Reject outliers if they are outside of m standard deviations from the
    mean value."""
    m = 2
    u = np.mean(data)
    s = np.std(data)
    filtered = [e for e in data if (u - m * s < e < u + m * s)]
    return filtered


def eliminate_backlash_in_tiltx(ctrl):
    a_i = ctrl.stage.a
    if a_i < 0:
        ctrl.stage.set(a=a_i + 0.5, wait=True)
        return 0
    else:
        ctrl.stage.set(a=a_i - 0.5, wait=True)
        return 1


def center_z_height(ctrl, verbose=False):
    """Automated routine to find the z-height.

    Koster, A. J., et al. "Automated microscopy for electron tomography."
    Ultramicroscopy 46.1-4 (1992): 207-227.
    http://www.msg.ucsf.edu/agard/Publications/52-Koster.pdf
    """
    print('\033[k', 'Finding eucentric height...', end='\r')
    if ctrl.mode != 'mag1':
        ctrl.mode.set('mag1')

    ctrl.brightness.value = 65535
    ctrl.magnification.value = 2500

    z0 = ctrl.stage.z
    ctrl.stage.set(a=-5)
    a0 = ctrl.stage.a
    z = []
    d = []
    ctrl.stage.z = z0 - 2000
    ctrl.stage.z = z0 - 1000
    ctrl.stage.z = z0

    for i in range(0, 10):
        z1 = ctrl.stage.z
        ctrl.stage.set(a=a0)
        img0, h = ctrl.get_image(exposure=0.01, comment='z height finding')
        z.append(z0 + i * 1000)
        ctrl.stage.set(a=a0 + 10)
        img1, h = ctrl.get_image(exposure=0.01, comment='z height finding')
        shift, error, phasediff = phase_cross_correlation(img0, img1, upsample_factor=10)
        d1 = np.linalg.norm(shift)
        if shift[0] < 0:
            d1 = -d1
        d.append(d1)
        if verbose:
            print(f'Step {i}: z = {z1}, d = {np.linalg.norm(shift)}')
        ctrl.stage.set(z=z1 + 1000)
        time.sleep(1)

    d_f = reject_outlier(d)
    z_f = []
    for e in d_f:
        z_f.append(z[d.index(e)])
    p = np.polyfit(z, d, 1)
    z_center = -p[1] / p[0]
    satisfied = input(f'Found eucentric height: {z_center}. Press ENTER to set the height, x to cancel setting.')
    if satisfied == 'x':
        ctrl.stage.set(a=a0, z=z0)
        if verbose:
            print('Did not find proper eucentric height...')
    else:
        if z_center > ctrl.stage.z:
            ctrl.stage.set(a=a0, z=z_center - 2000)
            ctrl.stage.set(a=a0, z=z_center)
        else:
            ctrl.stage.set(a=a0, z=z_center + 2000)
            ctrl.stage.set(a=a0, z=z_center)

        print('\033[k', 'Eucentric height set. Find the crystal again and start data collection!', end='\r')


def find_crystal_max(img, magnification, spread, offset):

    crystal_positions = find_crystals_timepix(img, magnification, spread=spread, offset=offset)
    crystal_area = [crystal.area_pixel for crystal in crystal_positions if crystal.isolated]
    maxind = crystal_area.index(max(crystal_area))

    crystal_inter = max(crystal_area)
    crystal_inter_pos = (crystal_positions[maxind].x, crystal_positions[maxind].y)

    return crystal_inter, crystal_inter_pos


def center_z_height_HYMethod(ctrl, increment=2000, rotation=15, spread=2, offset=10, verbose=False):
    """Hongyi's empirical method for centering z height on our JEOL LAB6.

    Rotate the stage positively. If the particle moves upwards, adjust
    height to be higher. Vice versa.
    """

    print('\033[k', 'Finding eucentric height...', end='\r')
    if ctrl.mode != 'mag1':
        ctrl.mode.set('mag1')

    ctrl.brightness.value = 65535
    ctrl.magnification.value = 2500
    magnification = ctrl.magnification.value

    x0, y0, z0, a0, b0 = ctrl.stage.get()
    img0, h = ctrl.get_image(exposure=0.01, comment='z height finding HY')
    try:
        crystal_inter, crystal_inter_pos = find_crystal_max(img0, magnification, spread=spread, offset=offset)
        if verbose:
            print(f'Feature Captured. Area: {crystal_inter} pixels')
    except BaseException:
        if verbose:
            print('No crystals found. Please find another area for z height adjustment.')

    rotation_dir = eliminate_backlash_in_tiltx(ctrl)
    if rotation_dir == 0:
        ctrl.stage.set(a=a0 + rotation, wait=False)
        endangle = a0 + rotation
    else:
        ctrl.stage.set(a=a0 - rotation, wait=False)
        endangle = a0 - rotation

    while True:
        if abs(ctrl.stage.a - a0) > 2:
            break

    while ctrl.stage.is_moving():
        img, h = ctrl.get_image(exposure=0.01, comment='z height finding HY')
        try:
            crystal_inter1, crystal_inter1_pos = find_crystal_max(img, magnification, spread=spread, offset=offset)

            if crystal_inter1 / crystal_inter < 2 and crystal_inter1 / crystal_inter > 0.5:
                # print(f"Feature Captured. Area: {crystal_inter1} pixels")
                shift = np.subtract(crystal_inter_pos, crystal_inter1_pos)
                # print(f"Shift: {shift}")
                ctrl.stage.stop()
                if shift[0] > 5:
                    ctrl.stage.z = z0 - (rotation_dir - 0.5) * increment
                    # print(f"Z height adjusted: - {rotation_dir - 0.5)*increment}.")
                    crystal_inter = crystal_inter1
                    crystal_inter_pos = crystal_inter1_pos
                elif shift[0] < -5:
                    ctrl.stage.z = z0 + (rotation_dir - 0.5) * increment
                    # print(f"Z height adjusted: + {rotation_dir - 0.5)*increment}.")
                    crystal_inter = crystal_inter1
                    crystal_inter_pos = crystal_inter1_pos

            else:
                # print(f"Feature lost. New feature captured: {crystal_inter1} pixels")
                if crystal_inter1:
                    crystal_inter = crystal_inter1
                    crystal_inter_pos = crystal_inter1_pos
                else:
                    ctrl.stage.stop()
                    return 999999, 999999
        except BaseException:
            if verbose:
                print('No crystal found. Finding another area for z height adjustment.')
            ctrl.stage.stop()
            return 999999, 999999

        z0 = ctrl.stage.z

        if abs(ctrl.stage.a - endangle) < 0.5:
            break
        ctrl.stage.set(a=endangle, wait=False)
        time.sleep(0.5)

    print('\033[k', f'Z height adjustment done and eucentric z height found at: {z0}', end='\r')
    x, y, z, a, b = ctrl.stage.get()
    return x, y
