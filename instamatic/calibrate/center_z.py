import numpy as np
import time
from instamatic.processing.cross_correlate import cross_correlate

def reject_outlier(data, m=2):
    """Reject outliers if they are outside of m standard deviations from
    the mean value"""
    m = 2
    u = np.mean(data)
    s = np.std(data)
    filtered = [e for e in data if (u - m*s < e < u + m*s)]
    return filtered

def eliminate_backlash_in_tiltx(ctrl):
    a_i = ctrl.stageposition.a
    if a_i < 0:
        ctrl.stageposition.set(a = a_i + 0.5 , wait = True)
        return 0
    else:
        ctrl.stageposition.set(a = a_i - 0.5 , wait = True)
        return 1


def center_z_height(ctrl):
    """Automated routine to find the z-height

    Koster, A. J., et al. "Automated microscopy for electron tomography." 
    Ultramicroscopy 46.1-4 (1992): 207-227.
    http://www.msg.ucsf.edu/agard/Publications/52-Koster.pdf
    """


    print("Finding eucentric height...")
    if ctrl.mode != 'mag1':
        ctrl.mode = 'mag1'

    ctrl.brightness.value = 65535
    ctrl.magnification.value = 2500

    z0 = ctrl.stageposition.z
    ctrl.stageposition.set(a = -5)
    a0 = ctrl.stageposition.a
    z = []
    d = []
    ctrl.stageposition.z = z0 - 2000
    ctrl.stageposition.z = z0 - 1000
    ctrl.stageposition.z = z0
    
    for i in range(0,10):
        z1 = ctrl.stageposition.z
        ctrl.stageposition.set(a = a0)
        img0, h = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        z.append(z0 + i * 1000)
        ctrl.stageposition.set(a = a0 + 10)
        img1, h = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        shift = cross_correlate(img0, img1, upsample_factor=10, verbose=False)
        d1 = np.linalg.norm(shift) 
        if shift[0] < 0:
            d1 = -d1
        d.append(d1)
        print("Step {}: z = {}, d = {}".format(i, z1, np.linalg.norm(shift)))
        ctrl.stageposition.set(z = z1 + 1000)
        time.sleep(1)
        
    d_f = reject_outlier(d)
    z_f = []
    for e in d_f:
        z_f.append(z[d.index(e)])
    p = np.polyfit(z, d, 1)
    z_center = -p[1]/p[0]
    satisfied = input("Found eucentric height: {}. Press ENTER to set the height, x to cancel setting.".format(z_center))
    if satisfied == "x":
        ctrl.stageposition.set(a = a0, z = z0)
        print("Did not find proper eucentric height...")
    else:
        if z_center > ctrl.stageposition.z:
            ctrl.stageposition.set(a = a0, z = z_center-2000)
            ctrl.stageposition.set(a = a0, z = z_center)
        else:
            ctrl.stageposition.set(a = a0, z = z_center+2000)
            ctrl.stageposition.set(a = a0, z = z_center)
        print("Eucentric height set. Find the crystal again and start data collection!")
        
def center_z_height_HYMethod(ctrl, increment = 2000):
    """Hongyi's empirical method for centering z height on our JEOL LAB6.
    Rotate the stage positively. If the particle moves upwards, adjust height to be higher.
    Vice versa."""
    
    print("Finding eucentric height...")
    if ctrl.mode != 'mag1':
        ctrl.mode = 'mag1'

    ctrl.brightness.value = 65535
    ctrl.magnification.value = 2500
    x0,y0,z0,a0,b0 = ctrl.stageposition.get()
    img0, h = ctrl.getImage(exposure = 0.01, comment = "z height finding HY")
    rotation_dir = eliminate_backlash_in_tiltx(ctrl)
    if rotation_dir == 0:
        ctrl.stageposition.set(a = a0 + 30, wait = False)
        endangle = a0 + 30
    else:
        ctrl.stageposition.set(a = a0 - 30, wait = False)
        endangle = a0 - 30
    
    while True:
        if abs(ctrl.stageposition.a - a0) > 2:
            break
        
    while ctrl.stageposition.is_moving():
        img, h = ctrl.getImage(exposure = 0.01, comment = "z height finding HY")
        shift = cross_correlate(img0, img, upsample_factor=10, verbose=False)
        print("shift: {}".format(shift))
        ctrl.stageposition.stop()
        if shift[0] > 5:
            ctrl.stageposition.z = z0 - (rotation_dir - 0.5)*increment
            print("Z height adjusted: - {}.".format((rotation_dir - 0.5)*increment))
            img0 = img
        elif shift[0] < -5:
            ctrl.stageposition.z = z0 + (rotation_dir - 0.5)*increment
            print("Z height adjusted: + {}.".format((rotation_dir - 0.5)*increment))
            img0 = img
        z0 = ctrl.stageposition.z

        if abs(ctrl.stageposition.a - endangle) < 0.5:
            break
        ctrl.stageposition.set(a = endangle, wait = False)
        time.sleep(1)
        
    print("Z height adjustment done and eucentric z height found at: {}".format(z0))
    x, y, z, a, b = ctrl.stageposition.get()
    return x, y