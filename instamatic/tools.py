from scipy import ndimage
import fabio
import json
import sys, os
import numpy as np

def load_img(fn):
    root, ext = os.path.splitext(fn)
    ext = ext.lower()
    if ext != ".npy":
        arr = fabio.openimage.openimage(fn)
        # workaround to fix headers
        if ext == ".edf":
            for key in ("BeamShift", "BeamTilt", "GunShift", "GunTilt", "ImageShift", "StagePosition"):
                if arr.header.has_key(key):
                    arr.header[key] = eval("{" + arr.header[key] + "}")
        return arr.data, arr.header
    else:
        arr = np.load(fn)
    
        root, ext = os.path.splitext(fn)
        fnh = root + ".json"
    
        d = json.load(open(fnh, "r"))
        return arr, d

def autoscale(img, maxdim=512):
    if maxdim:
        scale = float(maxdim) / max(img.shape)

    return ndimage.zoom(img, scale, order=3), scale

def imgscale(img, scale):
    return ndimage.zoom(img, scale)