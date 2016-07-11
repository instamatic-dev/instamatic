from scipy.optimize import leastsq
from cross_correlate import cross_correlate
import numpy as np
import matplotlib.pyplot as plt
import os,sys
import json


def load_img(fn):
    arr = np.load(fn)

    root, ext = os.path.splitext(fn)
    fnh = root + ".json"

    if os.path.exists(fnh):
        d = json.load(open(fnh, "r"))
    
    return arr, d


def lsq_rotation_scaling_matrix(shifts, stagepos):
    """
    Find pixel->stageposition matrix via least squares routine

    shifts: 2D ndarray, shape (-1,2)
        pixel shifts from cross correlation
    stagepos: 2D Ndarray, shape (-1,2)
        observed stage positions

    stagepos = np.dot(shifts, r) + t
    shifts = np.dot(stagepos - t, r_i)
    """
    def objective_func(x0, arr1, arr2):
        r = x0[0:4].reshape(2,2)
        t = np.array(x0[4:6])
        fit = np.dot(arr1, r) + t
        return (fit-arr2).reshape(-1,)
    
    x0 = np.array([ 1.,  0.,  0.,  1., 0., 0.])
    args = (shifts, stagepos)

    x, _ = leastsq(objective_func, x0, args=args)

    r = x[0:4].reshape(2,2)
    t = np.array(x[4:6])

    shifts_ = np.dot(shifts, r) + t
    r_i = np.linalg.inv(r)
    stagepos_ = np.dot(stagepos - t, r_i)

    plt.scatter(shifts[:,0], shifts[:,1], color="red", label="Observed pixel shifts")
    plt.scatter(stagepos_[:,0], stagepos_[:,1], color="blue", label="Stageposition in pixel coords")
    plt.legend()

    plt.xlim(stagepos_.min()*1.2, stagepos_.max()*1.2)
    plt.ylim(stagepos_.min()*1.2, stagepos_.max()*1.2)
    plt.show()
    
    return r,t


def calibrate_lowmag(ctrl, cam, gridsize=5, stepsize=10e-05, exposure=0.1):
    """
    Calibrate pixel->stageposition coordinates live on the microscope

    ctrl: instance of `TEMController`
    cam: instance of `gatanOrius`
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    exposure: `float`
        exposure time
    """

    if not raw_input("""\n >> Go too 100x mag, and move the sample stage
    so that the grid center (clover) is in the 
    middle of the image (type 'go'): """) == "go":
        exit()
    
    print
    print ctrl.stageposition
    img_cent = cam.getImage(t=exposure)
    x_cent, y_cent = ctrl.stageposition.x, ctrl.stageposition.y
    
    stagepos = []
    shifts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.stageposition.goto(x=x_cent+dx, y=y_cent+dy)
           
        print
        print ctrl.stageposition
        
        img = cam.getImage(t=exposure)
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        xy = ctrl.stageposition.x, ctrl.stageposition.y
        stagepos.append(xy)
        shifts.append(shift)
            
    print " >> Reset to center"
    ctrl.stageposition.goto(x=x_cent, y=y_cent)
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))
    
    r,t = lsq_rotation_scaling_matrix(shifts, stagepos)

    return r,t


def calibrate_lowmag_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->stageposition coordinates from a set of images

    center_fn: `str`
        Reference image at the center of the grid (with the clover in the middle)
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image
    """
    img_cent, header_cent = load_img(center_fn)
    x_cent, y_cent = np.array((header_cent["StagePosition"]["x"], header_cent["StagePosition"]["y"]))
    print
    print "Center:", center_fn
    print "Stageposition: x={} | y={}".format(x_cent, y_cent)

    shifts = []
    stagepos = []
    
    for fn in other_fn:
        img, header = load_img(fn)
        
        xy = header["StagePosition"]["x"], header["StagePosition"]["y"]
        print
        print "Image:", fn
        print "Stageposition: x={} | y={}".format(*xy)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        stagepos.append(xy)
        shifts.append(shift)
        
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))
        
    r,t = lsq_rotation_scaling_matrix(shifts, stagepos)
    
    return r,t

# lowmag
# pixel dimensions from calibration in Digital Micrograph
# x,y dimensions of 1 pixel in micrometer
lowmag_dimensions = {
50:      (0,         0),
80:      (0.559748,  0.559748),
100:     (0.447799,  0.447799),
150:     (0,         0),
200:     (0.223899,  0.223899),
250:     (0,         0),
300:     (0,         0),
400:     (0,         0),
500:     (0,         0),
600:     (0.0746331, 0.0746331),
800:     (0,         0),
1000:    (0,         0),
1200:    (0,         0),
1500:    (0,         0),
2000:    (0.0207997, 0.0207997),
2500:    (0,         0),
3000:    (0,         0),
5000:    (0,         0),
6000:    (0,         0),
8000:    (0,         0),
10000:   (0,         0),
12000:   (0,         0),
15000:   (0,         0)
}

lowmag_om_standard_focus = {
50:      24722,
80:      32582,
100:     32582,
150:     42134,
200:     41622,
250:     41338,
300:     40858,
400:     40300,
500:     39914,
600:     39808,
800:     39642,
1000:    39234,
1200:    38362,
1500:    37930,
2000:    37718,
2500:    37293,
3000:    49025,
5000:    49010,
6000:    49000,
8000:    48983,
10000:   48960,
12000:   48931,
15000:   48931
}


lowmag_neutral_beamtilt = {
50:      (33201,     24555),
80:      (33201,     24555),
100:     (33201,     24555),
150:     (33201,     24555),
200:     (33201,     24555),
250:     (33201,     24555),
300:     (33201,     24555),
400:     (33201,     24555),
500:     (33201,     24555),
600:     (33201,     24555),
800:     (33201,     24555),
1000:    (33201,     24555),
1200:    (33201,     24555),
1500:    (33201,     24555),
2000:    (33201,     24555),
2500:    (33201,     24555),
3000:    (33201,     24555),
5000:    (33201,     24555),
6000:    (33201,     24555),
8000:    (33201,     24555),
10000:   (33201,     24555),
12000:   (33201,     24555),
15000:   (33201,     24555)
}

lowmag_neutral_imageshift = {
50:      (33152,     32576),
50:      (33152,     32576),
50:      (33152,     32576),
80:      (33152,     32576),
100:     (33152,     32576),
150:     (32384,     33280),
200:     (32384,     33280),
250:     (32384,     33280),
300:     (32384,     33280),
400:     (32384,     33280),
500:     (32384,     33280),
600:     (32384,     33280),
800:     (32384,     33280),
1000:    (32384,     33280),
1200:    (32384,     33280),
1500:    (32384,     33280),
2000:    (32384,     33280),
2500:    (32384,     33280),
3000:    (31104,     31296),
5000:    (31104,     31296),
6000:    (31104,     31296),
8000:    (31104,     31296),
10000:   (31104,     31296),
12000:   (31104,     31296),
15000:   (31104,     31296),
}

lowmag_neutral_beamshift = {
50:      (30450,     29456),
80:      (30450,     29456),
100:     (30450,     29456),
150:     (30450,     29456),
200:     (30450,     29456),
250:     (30450,     29456),
300:     (30450,     29456),
400:     (30450,     29456),
500:     (30450,     29456),
600:     (30450,     29456),
800:     (30450,     29456),
1000:    (30450,     29456),
1200:    (30450,     29456),
1500:    (30450,     29456),
2000:    (30450,     29456),
2500:    (30450,     29456),
3000:    (30450,     29456),
5000:    (30450,     29456),
6000:    (30450,     29456),
8000:    (30450,     29456),
10000:   (30450,     29456),
12000:   (30450,     29456),
15000:   (30450,     29456),
}

# mag1
# pixel dimensions from calibration in Digital Micrograph
# x,y dimensions of 1 pixel in micrometer
mag1_dimensions = {
2500:    (0,         0),
3000:    (0,         0),
4000:    (0,         0),
5000:    (0,         0),
6000:    (0,         0),
8000:    (0,         0),
10000:   (0,         0),
12000:   (0,         0),
15000:   (0,         0),
20000:   (0,         0),
25000:   (0,         0),
30000:   (0,         0),
40000:   (0,         0),
50000:   (0,         0),
60000:   (0,         0),
80000:   (0,         0),
100000:  (0,         0),
120000:  (0,         0),
150000:  (0,         0),
200000:  (0,         0),
250000:  (0,         0),
300000:  (0,         0),
400000:  (0,         0),
500000:  (0,         0),
600000:  (0,         0),
800000:  (0,         0),
1000000: (0,         0),
2000000: (0,         0),
2000000: (0,         0)
}

mag1_neutral_beamtilt = {
2500:    (43393,     34122),
3000:    (43393,     34122),
4000:    (43393,     34122),
5000:    (43393,     34122),
6000:    (43393,     34122),
8000:    (43393,     34122),
10000:   (43393,     34122),
12000:   (43393,     34122),
15000:   (43393,     34122),
20000:   (43393,     34122),
25000:   (43393,     34122),
30000:   (43393,     34122),
40000:   (43393,     34122),
50000:   (43393,     34122),
60000:   (43393,     34122),
80000:   (43393,     34122),
100000:  (43393,     34122),
120000:  (43393,     34122),
150000:  (43393,     34122),
200000:  (43393,     34122),
250000:  (43393,     34122),
300000:  (43393,     34122),
400000:  (43393,     34122),
500000:  (43393,     34122),
600000:  (43393,     34122),
800000:  (43393,     34122),
1000000: (43393,     34122),
2000000: (43393,     34122)
}

mag1_neutral_imageshift = {
2500:    (33088,     33216),
3000:    (33088,     33216),
4000:    (33088,     33216),
5000:    (33088,     33216),
6000:    (33088,     33216),
8000:    (33088,     33216),
10000:   (33088,     33216),
12000:   (31808,     31296),
15000:   (31808,     31296),
20000:   (31808,     31296),
25000:   (31808,     31296),
30000:   (31808,     31296),
40000:   (32768,     32768),
50000:   (32768,     32768),
60000:   (32768,     32768),
80000:   (32768,     32768),
100000:  (32768,     32768),
120000:  (32768,     32768),
150000:  (32768,     32768),
200000:  (32768,     32768),
250000:  (32768,     32768),
300000:  (32768,     32768),
400000:  (32768,     32768),
500000:  (32768,     32768),
600000:  (32768,     32768),
800000:  (32768,     32768),
1000000: (32768,     32768),
2000000: (32768,     32768)
}

mag1_ol_standard_focus = {
2500:    1510565,
3000:    1510565,
4000:    1510565,
5000:    1510565,
6000:    1510565,
8000:    1510565,
10000:   1510565,
12000:   1513093,
15000:   1513093,
20000:   1513093,
25000:   1513093,
30000:   1513093,
40000:   1513093,
50000:   1513093,
60000:   1513093,
80000:   1513093,
100000:  1513093,
120000:  1513093,
150000:  1513093,
200000:  1513093,
250000:  1513093,
300000:  1513093,
400000:  1513093,
500000:  1513093,
600000:  1513093,
800000:  1513093,
1000000: 1511258,
2000000: 1511258
}

mag1_neutral_beamshift = {
2500:    (33872,     33360),
3000:    (33872,     33360),
4000:    (33872,     33360),
5000:    (33872,     33360),
6000:    (33872,     33360),
8000:    (33872,     33360),
10000:   (33872,     33360),
12000:   (33872,     33360),
15000:   (33872,     33360),
20000:   (33872,     33360),
25000:   (33872,     33360),
30000:   (33872,     33360),
40000:   (33872,     33360),
50000:   (33872,     33360),
60000:   (33872,     33360),
80000:   (33872,     33360),
100000:  (33872,     33360),
120000:  (33872,     33360),
150000:  (33872,     33360),
200000:  (33872,     33360),
250000:  (33872,     33360),
300000:  (33872,     33360),
400000:  (33872,     33360),
500000:  (33872,     33360),
600000:  (33872,     33360),
800000:  (33872,     33360),
1000000: (33872,     33360),
2000000: (33872,     33360)
}
