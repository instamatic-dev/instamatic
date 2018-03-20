import numpy as np
import time

def reject_outlier(data):
    m = 2
    u = np.mean(data)
    s = np.std(data)
    filtered = [e for e in data if (u - m*s < e < u + m*s)]
    return filtered

def center_z_height(ctrl):
    """http://www.msg.ucsf.edu/agard/Publications/52-Koster.pdf"""
    from instamatic.processing.cross_correlate import cross_correlate

    print "Finding eucentric height..."
    if ctrl.mode == 'diff':
        ctrl.mode = 'samag'

    z0 = ctrl.stageposition.z
    a0 = ctrl.stageposition.a
    z = []
    d = []
    z2 = z0
    ctrl.stageposition.z = z0 - 2000
    ctrl.stageposition.z = z0 - 1000
    ctrl.stageposition.z = z0
    
    for i in range(0,10):
        z1 = ctrl.stageposition.z
        print z1 - z2
        img0, h = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        z.append(z0 + i * 1000)
        a = ctrl.stageposition.a
        ctrl.stageposition.set(a = a + 1)
        img1, h = ctrl.getImage(exposure = 0.01, comment = "z height finding")
        shift = cross_correlate(img0, img1, upsample_factor=10, verbose=False)
        d1 = np.linalg.norm(shift) 
        if shift[0] < 0:
            d1 = -d1
        d.append(d1)
        print "Step {}: z = {}, d = {}".format(i, z1, np.linalg.norm(shift))
        z2 = ctrl.stageposition.z
        ctrl.stageposition.set(z = z1 + 1000)
        time.sleep(1)
        
    d_f = reject_outlier(d)
    print d_f
    z_f = []
    for e in d_f:
        z_f.append(z[d.index(e)])
    print z_f
    p = np.polyfit(z, d, 1)
    z_center = -p[1]/p[0]
    satisfied = raw_input("Found eucentric height: {}. Press ENTER to set the height, x to cancel setting.".format(z_center))
    if satisfied == "x":
        ctrl.stageposition.set(a = a0, z = z0)
        print "Did not find proper eucentric height..."
    else:
        if z_center > ctrl.stageposition.z:
            ctrl.stageposition.set(a = a0, z = z_center-2000)
            ctrl.stageposition.set(a = a0, z = z_center)
        else:
            ctrl.stageposition.set(a = a0, z = z_center+2000)
            ctrl.stageposition.set(a = a0, z = z_center)
        print "Eucentric height set. Find the crystal again and start data collection!"

    ctrl.mode = 'diff'