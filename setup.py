#!/usr/bin/env python

from setuptools import setup, find_packages
import os

packages = find_packages(exclude=["scripts"])

exec(open('instamatic/version.py').read())  # grab __version__, __author__, etc.

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding = 'utf-8').read()

try:
    long_description = read('README.rst')
except IOError:
    long_description = read('README.md')

setup(
    name=__title__,
    version=__version__,
    description=__description__,
    long_description=long_description,

    author=__author__,
    author_email=__author_email__,
    license=__license__,
    url=__url__,

    classifiers=[
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Microsoft :: Windows',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces',
        'Topic :: Scientific/Engineering :: Chemistry',
        'Topic :: Software Development :: Libraries'
    ],

    packages=packages,

    install_requires=['comtypes', 
                      'lmfit', 
                      'matplotlib', 
                      'numpy', 
                      'pandas', 
                      'Pillow', 
                      'scipy', 
                      'scikit-image', 
                      'tqdm', 
                      'pyyaml', 
                      'h5py', 
                      'tifffile',
                      'IPython'],

    include_package_data=True,

    entry_points={
        'console_scripts': [
            # main
            'instamatic                               = instamatic.gui:main',
            'instamatic.gui                           = instamatic.gui:main',
            'instamatic.serialed                      = instamatic.experiments.serialed.experiment:main',
            # experiment
            'instamatic.camera                        = instamatic.camera.camera:main_entry',
            'instamatic.controller                    = instamatic.TEMController.TEMController:main_entry',
            # calibrate
            'instamatic.calibrate_stage_lowmag        = instamatic.calibrate.calibrate_stage_lowmag:main_entry',
            'instamatic.calibrate_stage_mag1          = instamatic.calibrate.calibrate_stage_mag1:main_entry',
            'instamatic.calibrate_beamshift           = instamatic.calibrate.calibrate_beamshift:main_entry',
            'instamatic.calibrate_directbeam          = instamatic.calibrate.calibrate_directbeam:main_entry',
            # processing
            'instamatic.flatfield                     = instamatic.processing.flatfield:main_entry',
            'instamatic.stretch_correction            = instamatic.processing.stretch_correction:main_entry',
            'instamatic.find_crystals                 = instamatic.processing.find_crystals:main_entry',
            'instamatic.learn                         = scripts.learn:main_entry',
            # explore
            'instamatic.browser                       = scripts.browser:main',
            'instamatic.viewer                        = scripts.viewer:main',
            # server
            'instamatic.watcher                       = instamatic.server.TEMbkgWatcher:main',
            'instamatic.temserver                     = instamatic.server.tem_server:main',
            'instamatic.dialsserver                   = instamatic.server.dials_server:main',
            'instamatic.xdsserver                     = instamatic.server.xds_server:main',
            'instamatic.temserver_fei                 = instamatic.server.TEMServer_FEI:main'
        ]
    }
)

