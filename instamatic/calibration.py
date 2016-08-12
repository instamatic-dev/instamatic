from scipy.optimize import leastsq
from cross_correlate import cross_correlate
import numpy as np
import matplotlib.pyplot as plt
import os,sys
import json
from functools import partial
from camera import save_image_and_header

def load_img(fn):
    arr = np.load(fn)

    root, ext = os.path.splitext(fn)
    fnh = root + ".json"

    d = json.load(open(fnh, "r"))
    
    return arr, d


class CalibResult(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results"""
    def __init__(self, transform, reference_position):
        super(CalibResult, self).__init__()
        self.transform = transform
        self.reference_position = reference_position
   
    def __repr__(self):
        return "CalibResult(transform=\n{},\n   reference_position=\n{})".format(self.transform, self.reference_position)

    def _reference_setting_to_pixelcoord(self, px_ref, image_pos, r, reference_pos):
        """
        Function to transform stage position to pixel coordinates
        
        px_ref: `list`
            stage position (x,y) to transform to pixel coordinates on 
            current image
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)
        px_ref = np.array(px_ref)
        
        # do the inverse transoformation here
        r_i = np.linalg.inv(r)
        
        # get stagepos vector from reference image (center) to current image
        vect = image_pos - reference_pos
        
        # stagepos -> pixel coords, and add offset for pixel position
        px = stagepos - np.dot(vect, r_i)
    
        return px
     
    def _pixelcoord_to_reference_setting(self, px, image_pos, r, reference_pos):
        """
        Function to transform pixel coordinates to pixel coordinates in reference setting
        
        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)
        px = np.array(px)
        
        # do the inverse transoformation here
        r_i = np.linalg.inv(r)
        
        # get stagepos vector from reference image (center) to current image
        vect = image_pos - reference_pos
        
        # stagepos -> pixel coords, and add offset for pixel position
        px_ref = np.dot(vect, r_i) + np.array(px)
    
        return px_ref

    def _pixelcoord_to_stagepos(self, px, image_pos, r, reference_pos):
        """
        Function to transform pixel coordinates to stage position
        
        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        reference_pos = np.array(reference_pos)
        
        px_ref = self._pixelcoord_to_reference_setting(px, image_pos, r, reference_pos)
    
        stagepos = np.dot(px_ref - 1024, r) + reference_pos
        
        return stagepos

    def _stagepos_to_pixelcoord(self, stagepos, imagepos, transform, reference_position):
        """
        Function to transform pixel coordinates to stage position
        
        px: `list`
            image pixel coordinates to transform to stage position
        r: `2d ndarray`, shape (2,2)
            transformation matrix from calibration
        image_pos: `list`
            stage position that the image was captured at
        reference_pos: `list`
            stage position of the reference (center) image
        """
        raise NotImplementedError

    def reference_setting_to_pixelcoord(self, px_ref, image_pos):
        """
        Function to transform pixel coordinates in reference setting to current frame
        """
        return self._reference_setting_to_pixelcoord(px_ref, image_pos, self.transform, self.reference_position)

    def pixelcoord_to_reference_setting(self, px, image_pos):
        """
        Function to transform pixel coordinates in current frame to reference setting
        """
        return self._pixelcoord_to_reference_setting(px, image_pos, self.transform, self.reference_position)

    def pixelcoord_to_stagepos(self, px, image_pos):
        """
        Function to transform pixel coordinates to stage position coordinates
        """
        return self._pixelcoord_to_stagepos(px, image_pos, self.transform, self.reference_position)

    def stagepos_to_pixelcoord(self, stagepos, imagepos):
        """
        Function to stage position coordinates to pixel coordinates on current frame
        """
        return self._stagepos_to_pixelcoord(stagepos, imagepos, self.transform, self.reference_position)


def lsq_rotation_scaling_matrix(shifts, stagepos):
    """
    Find pixel->stageposition matrix via least squares routine

    shifts: 2D ndarray, shape (-1,2)
        pixel shifts from cross correlation
    stagepos: 2D Ndarray, shape (-1,2)
        observed stage positions

    stagepos = np.dot(shifts, r)
    shifts = np.dot(stagepos, r_i)
    """
    def objective_func(x0, arr1, arr2):
        r = x0.reshape(2,2)
        fit = np.dot(arr1, r)
        return (fit-arr2).reshape(-1,)
    
    # x0 = np.array([ 1.,  0.,  0.,  1.])
    # better first guess from experiments, seems to be somewhat consistent between experiments
    x0 = np.array([-6.0e-08, 3.7e-07, -3.7e-07, -6.0e-08]) 

    args = (shifts, stagepos)

    x, _ = leastsq(objective_func, x0, args=args)

    r = x.reshape(2,2)

    shifts_ = np.dot(shifts, r)
    r_i = np.linalg.inv(r)
    stagepos_ = np.dot(stagepos, r_i)

    plt.scatter(shifts[:,0], shifts[:,1], color="red", label="Observed pixel shifts")
    plt.scatter(stagepos_[:,0], stagepos_[:,1], color="blue", label="Stageposition in pixel coords")
    plt.legend()

    plt.xlim(stagepos_.min()*1.2, stagepos_.max()*1.2)
    plt.ylim(stagepos_.min()*1.2, stagepos_.max()*1.2)
    plt.axis('equal')
    plt.show()
    
    return r


def calibrate_lowmag(ctrl, gridsize=5, stepsize=10e-05, exposure=0.1, binsize=1, save_images=False):
    """
    Calibrate pixel->stageposition coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """

    print
    print ctrl.stageposition
    img_cent, h = ctrl.getImage(exposure=exposure, comment="Center image")
    x_cent, y_cent = h["StagePosition"]["x"], h["StagePosition"]["y"]
    
    if save_images:
        outfile = "calib_center.npy"
        save_image_and_header(outfile, img=img_cent, header=h)

    stagepos = []
    shifts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    
    i = 0
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.stageposition.goto(x=x_cent+dx, y=y_cent+dy)
           
        print
        print ctrl.stageposition
        
        img, h = ctrl.getImage(exposure=exposure, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        xy = h["StagePosition"]["x"], h["StagePosition"]["y"]
        stagepos.append(xy)
        shifts.append(shift)

        if save_images:
            outfile = "calib_{:04d}.npy".format(i)
            save_image_and_header(outfile, img=img, header=h)
        
        i += 1
            
    print " >> Reset to center"
    ctrl.stageposition.goto(x=x_cent, y=y_cent)
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))
    
    r = lsq_rotation_scaling_matrix(shifts, stagepos)

    c = CalibResult(transform=r, reference_position=np.array([x_cent, y_cent]))

    return c


def calibrate_lowmag_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->stageposition coordinates from a set of images

    center_fn: `str`
        Reference image at the center of the grid (with the clover in the middle)
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    img_cent, header_cent = load_img(center_fn)
    x_cent, y_cent = np.array((header_cent["StagePosition"]["x"], header_cent["StagePosition"]["y"]))
    print
    print "Center:", center_fn
    print "Stageposition: x={} | y={}".format(x_cent, y_cent)

    shifts = []
    stagepos = []
    
    for fn in other_fn:
        img, h = load_img(fn)
        
        xy = h["StagePosition"]["x"], h["StagePosition"]["y"]
        print
        print "Image:", fn
        print "Stageposition: x={} | y={}".format(*xy)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        stagepos.append(xy)
        shifts.append(shift)
        
    shifts = np.array(shifts)
    stagepos = np.array(stagepos) - np.array((x_cent, y_cent))
        
    r = lsq_rotation_scaling_matrix(shifts, stagepos)
    
    c = CalibResult(transform=r, reference_position=np.array([x_cent, y_cent]))

    return c


def calibrate_highmag(ctrl, gridsize=5, stepsize=0e-05, exposure=0.1, binsize=1, save_images=False):
    """
    Calibrate pixel->beamshift coordinates live on the microscope

    ctrl: instance of `TEMController`
        contains tem + cam interface
    gridsize: `int`
        Number of grid points to take, gridsize=5 results in 25 points
    stepsize: `float`
        Size of steps for stage position along x and y
    exposure: `float`
        exposure time
    binsize: `int`

    return:
        instance of Calibration class with conversion methods
    """

    if not raw_input("""\n >> Go too 2500x mag, and move the beam by beamshift
    so that it is approximately in the middle of the image 
    (type 'go' to start): """) == "go":
        exit()

    print
    print ctrl.beamshift
    img_cent, h = ctrl.getImage(exposure=exposure, comment="Beam in center of image")
    x_cent, y_cent = ctrl.beamshift.x, ctrl.beamshift.y
    
    if save_images:
        outfile = "calib_beamcenter.npy"
        save_image_and_header(outfile, img=img_cent, header=h)

    beampos = []
    shifts = []
    
    n = (gridsize - 1) / 2 # number of points = n*(n+1)
    x_grid, y_grid = np.meshgrid(np.arange(-n, n+1) * stepsize, np.arange(-n, n+1) * stepsize)
    
    i = 0
    for dx,dy in np.stack([x_grid, y_grid]).reshape(2,-1).T:
        ctrl.beamshift.goto(x=x_cent+dx, y=y_cent+dy)
           
        print
        print ctrl.beamshift
        
        img, h = ctrl.getImage(exposure=exposure, comment="Calib image {}: dx={} - dy={}".format(i, dx, dy))
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        xy = h["StagePosition"]["x"], h["StagePosition"]["y"]
        beampos.append(xy)
        shifts.append(shift)

        if save_images:
            outfile = "calib_beamshift_{:04d}.npy".format(i)
            save_image_and_header(outfile, img=img,  header=h)
        
        i += 1
            
    print " >> Reset to center"
    ctrl.beamshift.goto(x=x_cent, y=y_cent)
    shifts = np.array(shifts)
    beampos = np.array(beampos) - np.array((x_cent, y_cent))
    
    r = lsq_rotation_scaling_matrix(shifts, beampos)

    c = CalibResult(transform=r, reference_position=np.array([x_cent, y_cent]))

    return c


def calibrate_highmag_from_image_fn(center_fn, other_fn):
    """
    Calibrate pixel->beamshift coordinates from a set of images

    center_fn: `str`
        Reference image with the beam at the center of the image
    other_fn: `tuple` of `str`
        Set of images to cross correlate to the first reference image

    return:
        instance of Calibration class with conversion methods
    """
    img_cent, h_cent = load_img(center_fn)
    print h_cent["BeamShift"]
    x_cent, y_cent = np.array((h_cent["BeamShift"]["x"], h_cent["BeamShift"]["y"]))
    print
    print "Center:", center_fn
    print "Beamshift: x={} | y={}".format(x_cent, y_cent)

    shifts = []
    beampos = []
    
    for fn in other_fn:
        img, h = load_img(fn)
        
        xy = h["BeamShift"]["x"], h["BeamShift"]["y"]
        print
        print "Image:", fn
        print "Beamshift: x={} | y={}".format(*xy)
        
        shift = cross_correlate(img_cent, img, upsample_factor=10, verbose=False)
        
        beampos.append(xy)
        shifts.append(shift)
        
    shifts = np.array(shifts)
    beampos = np.array(beampos) - np.array((x_cent, y_cent))
        
    r = lsq_rotation_scaling_matrix(shifts, beampos)
    
    c = CalibResult(transform=r, reference_position=np.array([x_cent, y_cent]))

    return c


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
