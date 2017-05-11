import numpy as np
cimport numpy as np
cimport cython

INT = np.int
ctypedef np.int_t INT_t

DOUBLE = np.int
ctypedef np.double_t DOUBLE_t

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cpdef float get_score(np.ndarray[INT_t, ndim=2] img, np.ndarray[DOUBLE_t, ndim=2] pks, float scale, float center_x, float center_y):
    """Score the projection based on the image given

    img: ndarray, dtype=INT
        Image array
    pks: ndarray, dtype=float
        2-column array containing the positions of the reflections on the image
    scale: float
        Convert the pk positions given in pks to pixel dimensions
    center_x, center_y: float
        Position of the incident beam, origin of the reciprocal lattice

    returns score: float
        Sum of the intensity at all pixel positions in the projection
    """
    cdef int xmax = img.shape[0]
    cdef int ymax = img.shape[1]
    cdef int xmin = 0
    cdef int ymin = 0

    cdef int nrows = pks.shape[0]

    cdef int i,j
    cdef float score = 0

    for n in range(nrows):
        i = int(pks[n, 0] * scale + center_x)
        j = int(pks[n, 1] * scale + center_y)
        
        if j < ymin:
            continue
        if j > ymax:
            continue
        if i < xmin:
            continue
        if i > xmax:
            continue

        score = score + img[i, j]

    return score

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cpdef float get_score_mod(np.ndarray[INT_t, ndim=2] img, np.ndarray[DOUBLE_t, ndim=2] pks, float scale, float center_x, float center_y):
    """Score the projection based on the image given

    img: ndarray, dtype=INT
        Image array
    pks: ndarray, dtype=float
        2-column array containing the positions of the reflections on the image
    scale: float
        Convert the pk positions given in pks to pixel dimensions
    center_x, center_y: float
        Position of the incident beam, origin of the reciprocal lattice

    returns score: float
        Sum of the intensity at all pixel positions in the projection
    """
    cdef int xmax = img.shape[0]
    cdef int ymax = img.shape[1]
    cdef int xmin = 0
    cdef int ymin = 0

    cdef int nrows = pks.shape[0]

    cdef int i,j
    cdef float score = 0

    cdef int nfail = 0
    cdef int nfit = 0

    cdef float item = 0.0
    cdef float thresh = 0.0

    for n in range(nrows):
        i = int(pks[n, 0] * scale + center_x)
        j = int(pks[n, 1] * scale + center_y)
        
        if j < ymin:
            nfail += 1
            continue
        if j > ymax:
            nfail += 1
            continue
        if i < xmin:
            nfail += 1
            continue
        if i > xmax:
            nfail += 1
            continue

        item = img[i, j]
        if item > thresh:
            score = score + item
            nfit += 1

    return score * nfit / (nrows - nfail)


@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cpdef float get_score_shape(np.ndarray[INT_t, ndim=2] img, np.ndarray[DOUBLE_t, ndim=2] pks, np.ndarray[DOUBLE_t] shape_factor, float scale, float center_x, float center_y):
    """Score the projection based on the image given

    img: ndarray, dtype=INT
        Image array
    pks: ndarray, dtype=float
        2-column array containing the positions of the reflections on the image
    scale: float
        Convert the pk positions given in pks to pixel dimensions
    center_x, center_y: float
        Position of the incident beam, origin of the reciprocal lattice

    returns score: float
        Sum of the intensity at all pixel positions in the projection
    """
    cdef int xmax = img.shape[0]
    cdef int ymax = img.shape[1]
    cdef int xmin = 0
    cdef int ymin = 0

    cdef int nrows = pks.shape[0]

    cdef int i,j
    cdef float score = 0

    cdef int nfail = 0
    cdef int nfit = 0

    cdef float item = 0.0
    cdef float thresh = 0.0

    for n in range(nrows):
        i = int(pks[n, 0] * scale + center_x)
        j = int(pks[n, 1] * scale + center_y)
        
        if j < ymin:
            nfail += 1
            continue
        if j > ymax:
            nfail += 1
            continue
        if i < xmin:
            nfail += 1
            continue
        if i > xmax:
            nfail += 1
            continue

        item = img[i, j]
        if item > thresh:
            score = score + item * shape_factor[n]
            nfit += 1

    return score * nfit / (nrows - nfail)
