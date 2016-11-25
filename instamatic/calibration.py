from scipy.optimize import leastsq
import numpy as np
import matplotlib.pyplot as plt
import lmfit
from tools import *

from scipy.stats import linregress

import pickle

CALIB_STAGE_LOWMAG = "calib_stage_lowmag.pickle"
CALIB_BEAMSHIFT = "calib_beamshift.pickle"
CALIB_BRIGHTNESS = "calib_brightness.pickle"
CALIB_DIFFSHIFT = "calib_diffshift.pickle"
CALIB_DIRECTBEAM = "calib_directbeam.pickle"


class CalibDirectBeam(object):
    """docstring for CalibDirectBeam"""
    def __init__(self, dct={}):
        super(CalibDirectBeam, self).__init__()
        self._dct = dct
    
    def __repr__(self):
        ret = "CalibDirectBeam("
        for key in self._dct.keys():
            r = self._dct[key]["r"]
            t = self._dct[key]["t"]

            ret += "\n {}(rotation=\n{},\n  translation={})".format(key, r, t)
        ret += ")"
        return ret

    @classmethod
    def combine(cls, lst):
        return cls({k: v for c in lst for k, v in c._dct.items()})

    def any2pixelshift(self, shift, key):
        r = self._dct[key]["r"]
        t = self._dct[key]["t"]

        shift = np.array(shift)
        r_i = np.linalg.inv(r)
        pixelshift = np.dot(shift - t, r_i)
        return pixelshift

    def pixelshift2any(self, pixelshift, key):
        r = self._dct[key]["r"]
        t = self._dct[key]["t"]

        pixelshift = np.array(pixelshift)
        shift = np.dot(shift, r) + t
        return shift

    def beamshift2pixelshift(self, beamshift):
        return self.anyshift(shift=beamshift, key="BeamShift")

    def diffshift2pixelshift(self, diffshift):
        return self.anyshift(shift=beamshift, key="DiffShift")

    def imageshift2pixelshift(self, imageshift):
        return self.anyshift(shift=beamshift, key="ImageShift")

    def imagetilt2pixelshift(self, imagetilt):
        return self.anyshift(shift=beamshift, key="ImageTilt")

    def pixelshift2beamshift(self, pixelshift):
        return self.anyshift(shift=beamshift, key="BeamShift")

    def pixelshift2diffshift(self, pixelshift):
        return self.anyshift(shift=beamshift, key="DiffShift")

    def pixelshift2imageshift(self, pixelshift):
        return self.anyshift(shift=beamshift, key="ImageShift")

    def pixelshift2imagetilt(self, pixelshift):
        return self.anyshift(shift=beamshift, key="ImageTilt")

    @classmethod
    def from_data(cls, shifts, readout, key, **dct):
        r, t = fit_affine_transformation(shifts, readout, **dct)

        d = {
            "data_shifts": shifts,
            "data_readout": readout,
            "r": r,
            "t": t
        }

        return cls({key:d})

    @classmethod
    def from_file(cls, fn=CALIB_DIRECTBEAM):
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_directbeam"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_DIRECTBEAM):
        pickle.dump(self, open(fn, "w"))

    def add(self, key, dct):
        """Add calibrations to self._dct
        Must contain keys: 'r', 't'
        optional: 'data_shifts', 'data_readout'
        """
        self._dct[key] = dct

    def plot(self, key):
        data_shifts = self._dct[key]["data_shifts"]   # pixelshifts
        data_readout = self._dct[key]["data_readout"] # microscope readout

        shifts_ = self.any2pixelshift(shift=data_readout, key=key)

        plt.scatter(*data_shifts.T, label="Observed pixelshifts shift")
        plt.scatter(*shifts_.T, label="Calculated shift from readout from BeamShift")
        plt.title(key + "vs. Direct beam position")
        plt.legend()
        plt.show()


class CalibDiffShift(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results

    NOTE: The TEM stores different values for diffshift depending on the mode used
        i.e. mag1 vs sa-diff"""
    def __init__(self, rotation, translation, neutral_beamshift=None):
        super(CalibDiffShift, self).__init__()
        self.rotation = rotation
        self.translation = translation
        if not neutral_beamshift:
            neutral_beamshift = (32576, 31149)
        self.neutral_beamshift = neutral_beamshift
        self.has_data = False

    def __repr__(self):
        return "CalibDiffShift(rotation=\n{},\n translation=\n{})".format(
            self.rotation, self.translation)

    def diffshift2beamshift(self, diffshift):
        diffshift = np.array(diffshift)
        r = self.rotation
        t = self.translation

        return (np.dot(diffshift, r) + t).astype(int)

    def beamshift2diffshift(self, beamshift):
        beamshift = np.array(beamshift)
        r_i = np.linalg.inv(self.rotation)
        t = self.translation

        return np.dot(beamshift - t, r_i).astype(int)

    def compensate_beamshift(self, ctrl):
        if not ctrl.mode == "diff":
            print " >> Switching to diffraction mode"
            ctrl.mode_diffraction()
        beamshift = ctrl.beamshift.get()
        diffshift = self.beamshift2diffshift(beamshift)
        ctrl.diffshift.set(*diffshift)

    def compensate_diffshift(self, ctrl):
        if not ctrl.mode == "diff":
            print " >> Switching to diffraction mode"
            ctrl.mode_diffraction()
        diffshift = ctrl.diffshift.get()
        beamshift = self.diffshift2beamshift(diffshift)
        ctrl.beamshift.set(*beamshift)

    def reset(self, ctrl):
        ctrl.beamshift.set(*self.neutral_beamshift)
        self.compensate_diffshift()

    @classmethod
    def from_data(cls, diffshift, beamshift, neutral_beamshift):
        r, t = fit_affine_transformation(diffshift, beamshift, translation=True, shear=True)

        c = cls(rotation=r, translation=t, neutral_beamshift=neutral_beamshift)
        c.data_diffshift = diffshift
        c.data_beamshift = beamshift
        c.has_data = True
        return c

    @classmethod
    def from_file(cls, fn=CALIB_DIFFSHIFT):
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_diffshift"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_DIFFSHIFT):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            return
    
        diffshift = self.data_diffshift

        r_i = np.linalg.inv(self.rotation)
        beamshift_ = np.dot(self.data_beamshift - self.translation, r_i)
    
        plt.scatter(*diffshift.T, label="Observed Diffraction shift")
        plt.scatter(*beamshift_.T, label="Calculated DiffShift from BeamShift")
        plt.legend()
        plt.show()


class CalibBeamShift(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results"""
    def __init__(self, transform, reference_shift, reference_pixel):
        super(CalibBeamShift, self).__init__()
        self.transform = transform
        self.reference_shift = reference_shift
        self.reference_pixel = reference_pixel
        self.has_data = False
   
    def __repr__(self):
        return "CalibBeamShift(transform=\n{},\n   reference_shift=\n{},\n   reference_pixel=\n{})".format(
            self.transform, self.reference_shift, self.reference_pixel)

    def beamshift_to_pixelcoord(self, beamshift):
        """Converts from beamshift x,y to pixel coordinates"""
        r_i = np.linalg.inv(self.transform)
        pixelcoord = np.dot(self.reference_shift - beamshift, r_i) + self.reference_pixel
        return pixelcoord
        
    def pixelcoord_to_beamshift(self, pixelcoord):
        """Converts from pixel coordinates to beamshift x,y"""
        r = self.transform
        beamshift = self.reference_shift - np.dot(pixelcoord - self.reference_pixel, r)
        return beamshift.astype(int)

    @classmethod
    def from_data(cls, shifts, beampos, reference_shift, reference_pixel):
        r, t = fit_affine_transformation(shifts, beampos)

        c = cls(transform=r, reference_shift=reference_shift, reference_pixel=reference_pixel)
        c.data_shifts = shifts
        c.data_beampos = beampos
        c.has_data = True
        return c

    @classmethod
    def from_file(cls, fn=CALIB_BEAMSHIFT):
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_beamshift"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_BEAMSHIFT):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            return

        beampos = self.data_beampos
        shifts = self.data_shifts

        r_i = np.linalg.inv(self.transform)
        beampos_ = np.dot(beampos, r_i)

        plt.scatter(*shifts.T, label="Observed pixel shifts")
        plt.scatter(*beampos_.T, label="Positions in pixel coords")
        plt.legend()
        plt.show()

    def center(self):
        return self.pixelcoord_to_beamshift((1024, 1024))


class CalibBrightness(object):
    """docstring for calib_brightness"""
    def __init__(self, slope, intercept):
        self.slope = slope
        self.intercept = intercept
        self.has_data = False

    def __repr__(self):
        return "CalibBrightness(slope={}, intercept={})".format(self.slope, self.intercept)

    def brightness_to_pixelsize(self, val):
        return self.slope*val + self.intercept

    def pixelsize_to_brightness(self, val):
        return int((val - self.intercept) / self.slope)

    @classmethod
    def from_data(cls, brightness, pixeldiameter):
        slope, intercept, r_value, p_value, std_err = linregress(brightness, pixeldiameter)
        print
        print "r_value: {:.4f}".format(r_value)
        print "p_value: {:.4f}".format(p_value)

        c = cls(slope=slope, intercept=intercept)
        c.data_brightness = brightness
        c.data_pixeldiameter = pixeldiameter
        c.has_data = True
        return c

    @classmethod
    def from_file(cls, fn=CALIB_BRIGHTNESS):
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_brightness"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_BRIGHTNESS):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            pass

        mn = self.data_brightness.min()
        mx = self.data_brightness.max()
        extend = abs(mx - mn)*0.1
        x = np.linspace(mn - extend, mx + extend)
        y = self.brightness_to_pixelsize(x)
    
        plt.plot(x, y, "r-", label="linear regression")
        plt.scatter(self.data_brightness, self.data_pixeldiameter)
        plt.title("Fit brightness")
        plt.legend()
        plt.show()


class CalibStage(object):
    """Simple class to hold the methods to perform transformations from one setting to another
    based on calibration results"""
    def __init__(self, rotation, translation=np.array([0, 0]), reference_position=np.array([0, 0])):
        super(CalibStage, self).__init__()
        self.has_data = False
        self.rotation = rotation
        self.translation = translation
        self.reference_position = reference_position
   
    def __repr__(self):
        return "CalibStage(rotation=\n{},\n translation=\n{},\n reference_position=\n{})".format(self.rotation, self.translation, self.reference_position)

    def _reference_setting_to_pixelcoord(self, px_ref, image_pos, r, t, reference_pos):
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
        
        # px_ref -> pixel coords, and add offset for pixel position
        px = px_ref - np.dot(vect - t, r_i)
    
        return px
     
    def _pixelcoord_to_reference_setting(self, px, image_pos, r, t, reference_pos):
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
        px_ref = np.dot(vect - t, r_i) + np.array(px)
    
        return px_ref

    def _pixelcoord_to_stagepos(self, px, image_pos, r, t, reference_pos):
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
        
        px_ref = self._pixelcoord_to_reference_setting(px, image_pos, r, t, reference_pos)
    
        stagepos = np.dot(px_ref - 1024, r) + t + reference_pos
        
        return stagepos

    def _stagepos_to_pixelcoord(self, stagepos, image_pos, r, t, reference_pos):
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
        stagepos = np.array(stagepos)
        image_pos = np.array(image_pos)
        reference_pos = np.array(reference_pos)
        
        # do the inverse transoformation here
        r_i = np.linalg.inv(r)

        px_ref = np.dot(stagepos - t - reference_pos, r_i) + 1024

        px = self._reference_setting_to_pixelcoord(px_ref, image_pos, r, t, reference_pos)

        return px

    def reference_setting_to_pixelcoord(self, px_ref, image_pos):
        """
        Function to transform pixel coordinates in reference setting to current frame
        """
        return self._reference_setting_to_pixelcoord(px_ref, image_pos, self.rotation, self.translation, self.reference_position)

    def pixelcoord_to_reference_setting(self, px, image_pos):
        """
        Function to transform pixel coordinates in current frame to reference setting
        """
        return self._pixelcoord_to_reference_setting(px, image_pos, self.rotation, self.translation, self.reference_position)

    def pixelcoord_to_stagepos(self, px, image_pos):
        """
        Function to transform pixel coordinates to stage position coordinates
        """
        return self._pixelcoord_to_stagepos(px, image_pos, self.rotation, self.translation, self.reference_position)

    def stagepos_to_pixelcoord(self, stagepos, image_pos):
        """
        Function to stage position coordinates to pixel coordinates on current frame
        """
        return self._stagepos_to_pixelcoord(stagepos, image_pos, self.rotation, self.translation, self.reference_position)

    @classmethod
    def from_data(cls, shifts, stagepos, reference_position):
        r, t = fit_affine_transformation(shifts, stagepos)

        c = cls(rotation=r, translation=t, reference_position=reference_position)
        c.data_shifts = shifts
        c.data_stagepos = stagepos
        c.has_data = True
        return c

    @classmethod
    def from_file(cls, fn=CALIB_STAGE_LOWMAG):
        try:
            return pickle.load(open(fn, "r"))
        except IOError as e:
            prog = "instamatic.calibrate_stage_lowmag"
            raise IOError("{}: {}. Please run {} first.".format(e.strerror, fn, prog))

    def to_file(self, fn=CALIB_STAGE_LOWMAG):
        pickle.dump(self, open(fn, "w"))

    def plot(self):
        if not self.has_data:
            return

        stagepos = self.data_stagepos
        shifts = self.data_shifts

        r_i = np.linalg.inv(self.rotation)

        stagepos_ = np.dot(stagepos - self.translation, r_i)

        plt.scatter(*shifts.T, label="Observed pixel shifts")
        plt.scatter(*stagepos_.T, label="Positions in pixel coords")
        
        for i, (x,y) in enumerate(shifts):
            plt.text(x+5, y+5, str(i), size=14)

        plt.legend()
        plt.show()


def fit_affine_transformation(a, b, rotation=True, scaling=True, translation=False, shear=False, as_params=False, **x0):
    params = lmfit.Parameters()
    params.add("angle", value=x0.get("angle", 0), vary=rotation, min=-np.pi, max=np.pi)
    params.add("sx"   , value=x0.get("sx"   , 1), vary=scaling)
    params.add("sy"   , value=x0.get("sy"   , 1), vary=scaling)
    params.add("tx"   , value=x0.get("tx"   , 0), vary=translation)
    params.add("ty"   , value=x0.get("ty"   , 0), vary=translation)
    params.add("k1"   , value=x0.get("k1"   , 1), vary=shear)
    params.add("k2"   , value=x0.get("k2"   , 1), vary=shear)
    
    def objective_func(params, arr1, arr2):
        angle = params["angle"].value
        sx    = params["sx"].value
        sy    = params["sy"].value 
        tx    = params["tx"].value
        ty    = params["ty"].value
        k1    = params["k1"].value
        k2    = params["k2"].value
        
        sin = np.sin(angle)
        cos = np.cos(angle)

        r = np.array([
            [ sx*cos, -sy*k1*sin],
            [ sx*k2*sin,  sy*cos]])
        t = np.array([tx, ty])

        fit = np.dot(arr1, r) + t
        return fit-arr2
    
    method = "leastsq"
    args = (a, b)
    res = lmfit.minimize(objective_func, params, args=args, method=method)
    
    lmfit.report_fit(res)
    
    angle = res.params["angle"].value
    sx    = res.params["sx"].value
    sy    = res.params["sy"].value 
    tx    = res.params["tx"].value
    ty    = res.params["ty"].value
    k1    = res.params["k1"].value
    k2    = res.params["k2"].value
    
    sin = np.sin(angle)
    cos = np.cos(angle)
    
    r = np.array([
        [ sx*cos, -sy*k1*sin],
        [ sx*k2*sin,  sy*cos]])
    t = np.array([tx, ty])
    
    if as_params:
        return res.params
    else:
        return r, t


# lowmag
# pixel dimensions from calibration in Digital Micrograph
# x,y dimensions of 1 pixel in micrometer
lowmag_pixeldimensions = {
50:      (0.895597,  0.895597),
80:      (0.559748,  0.559748),
100:     (0.447799,  0.447799),
150:     (0.298532,  0.298532),
200:     (0.223899,  0.223899),
250:     (0.179119,  0.179119),
300:     (0.149266,  0.149266),
400:     (0.111949,  0.111949),
500:     (0.089559,  0.089559),
600:     (0.074633,  0.074633),
800:     (0.055974,  0.055974),
1000:    (0.044779,  0.044779),
1200:    (0.037316,  0.037316),
1500:    (0.029853,  0.029853),
2000:    (0.020800,  0.020800),
2500:    (0.016640,  0.016640),
3000:    (0.013866,  0.013866),
5000:    (0.008320,  0.008320),
6000:    (0.006933,  0.006933),
8000:    (0.005200,  0.005200),
10000:   (0.004160,  0.004160),
12000:   (0.003466,  0.003466),
15000:   (0.002773,  0.002773)
}

# mag1
# pixel dimensions from calibration in Digital Micrograph LaB6
# x,y dimensions of 1 pixel in micrometer
mag1_dimensions = {
2500:    (0.01629260*2048, 0.01629260*2048),
3000:    (0.01339090*2048, 0.01339090*2048),
4000:    (0.00987389*2048, 0.00987389*2048),
5000:    (0.00782001*2048, 0.00782001*2048),
6000:    (0.00647346*2048, 0.00647346*2048),
8000:    (0.00481518*2048, 0.00481518*2048),
10000:   (0.00390216*2048, 0.00390216*2048),
12000:   (0.00328019*2048, 0.00328019*2048),
15000:   (0.00264726*2048, 0.00264726*2048),
20000:   (0.00200309*2048, 0.00200309*2048),
25000:   (0.00161106*2048, 0.00161106*2048),
30000:   (0.00136212*2048, 0.00136212*2048),
40000:   (0.00102159*2048, 0.00102159*2048),
50000:   (0.00081727*2048, 0.00081727*2048),
60000:   (0.00068106*2048, 0.00068106*2048),
80000:   (0.00051080*2048, 0.00051080*2048),
100000:  (0.00040864*2048, 0.00040864*2048),
120000:  (0.00034053*2048, 0.00034053*2048),
150000:  (0.00027242*2048, 0.00027242*2048),
200000:  (0.00020432*2048, 0.00020432*2048),
250000:  (0.00016345*2048, 0.00016345*2048),
300000:  (0.00013621*2048, 0.00013621*2048),
400000:  (0.00010216*2048, 0.00010216*2048),
500000:  (0.00008173*2048, 0.00008173*2048),
600000:  (0.00006811*2048, 0.00006811*2048),
800000:  (0.00005109*2048, 0.00005109*2048),
1000000: (0.00004086*2048, 0.00004086*2048),
1500000: (0.00002724*2048, 0.00002724*2048),
2000000: (0.00002043*2048, 0.00002043*2048)
}
