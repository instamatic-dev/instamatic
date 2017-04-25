import numpy as np
import os, sys

def get_orientations(lauegr="-1"):
    drc = os.path.abspath(os.path.dirname(__file__))
    fn = os.path.join(drc, "orientations_{}.txt".format(lauegr.replace("/", "o")))
    return np.loadtxt(fn)
