from collections import namedtuple

import lmfit
import numpy as np


FitResult = namedtuple('FitResult', 'r t angle sx sy tx ty k1 k2 params'.split())


def fit_affine_transformation(a, b,
                              rotation: bool = True,
                              scaling: bool = True,
                              translation: bool = False,
                              shear: bool = False,
                              as_params: bool = False,
                              verbose: bool = False,
                              **x0,
                              ):
    """Fit an affine transformation matrix to transform `a` to `b` using linear
    least-squares.

    `a` and `b` must be Nx2 numpy arrays.

    Parameters
    ----------
    rotation : bool
        Fit the rotation component (angle).
    scaling : bool
        Fit the scaling component (sx, sy).
    translation : bool
        Fit a translation component (tx, ty).
    shear : bool
        Fit a shear component (k1, k2).
    x0 : int/float
        Any specified values are used to set the default parameters for
        the different components: angle/sx/sy/tx/ty/k1/k2

    Returns
    -------
    fit_result : namedtuple
        Returns a namedtuple containing the 2x2 (.r) rotation and a 2x1 (.t)
        translation matrices to transform `a` to `b`. The raw parameters can
        be accessed through the corresponding attributes.
    """
    params = lmfit.Parameters()
    params.add('angle', value=x0.get('angle', 0), vary=rotation, min=-np.pi, max=np.pi)
    params.add('sx', value=x0.get('sx', 1), vary=scaling)
    params.add('sy', value=x0.get('sy', 1), vary=scaling)
    params.add('tx', value=x0.get('tx', 0), vary=translation)
    params.add('ty', value=x0.get('ty', 0), vary=translation)
    params.add('k1', value=x0.get('k1', 1), vary=shear)
    params.add('k2', value=x0.get('k2', 1), vary=shear)

    def objective_func(params, arr1, arr2):
        angle = params['angle'].value
        sx = params['sx'].value
        sy = params['sy'].value
        tx = params['tx'].value
        ty = params['ty'].value
        k1 = params['k1'].value
        k2 = params['k2'].value

        sin = np.sin(angle)
        cos = np.cos(angle)

        r = np.array([
            [sx * cos, -sy * k1 * sin],
            [sx * k2 * sin, sy * cos]])
        t = np.array([tx, ty])

        fit = np.dot(arr1, r) + t
        return fit - arr2

    method = 'leastsq'
    args = (a, b)
    res = lmfit.minimize(objective_func, params, args=args, method=method)

    if res.success and not verbose:
        print(f'Minimization converged after {res.nfev} cycles with chisqr of {res.chisqr}')
    else:
        lmfit.report_fit(res)

    angle = res.params['angle'].value
    sx = res.params['sx'].value
    sy = res.params['sy'].value
    tx = res.params['tx'].value
    ty = res.params['ty'].value
    k1 = res.params['k1'].value
    k2 = res.params['k2'].value

    sin = np.sin(angle)
    cos = np.cos(angle)

    r = np.array([
        [sx * cos, -sy * k1 * sin],
        [sx * k2 * sin, sy * cos]])
    t = np.array([tx, ty])

    return FitResult(r, t, angle, sx, sy, tx, ty, k1, k2, params)
