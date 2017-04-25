import numpy as np

def get_orientations(lauegr="-1"):
    fn = "orientations_{}.txt".format(lauegr.replace("/", "o"))
    return np.loadtxt(fn)
