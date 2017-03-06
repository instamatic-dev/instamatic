try:
    from setuptools import setup
    from setuptools import Extension
except ImportError:
    from distutils.core import setup
    from distutils.extension import Extension

import sys

from Cython.Build import cythonize
import numpy as np

if sys.platform == "win32":
    extensions = [
        Extension(
            'get_score_cy', ['get_score_cy.pyx'], include_dirs=[np.get_include()]),
    ]
else:
    extensions = [
        Extension('get_score_cy', ['get_score_cy.pyx'],
                  include_dirs=[np.get_include()]),
    ]


setup(
    ext_modules=cythonize(extensions)
)
