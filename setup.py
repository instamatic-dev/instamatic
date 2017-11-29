#!/usr/bin/env python

from setuptools import setup, find_packages
import os

# www.pythonhosted.org/setuptools/setuptools.html

execfile('instamatic/version.py')  # grab __version__

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

try:
    long_description = read('README.rst')
except IOError:
    long_description = read('README.md')

setup(
    name="instamatic",
    version=__version__,
    description="Python program to collect serial and rotation electron diffraction data",
    long_description=long_description,

    author="Stef Smeets",
    author_email="stef.smeets@mmk.su.se",
    license="GPL",
    url="https://github.com/stefsmeets/instamatic",

    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],

    packages=["instamatic", 
              "instamatic.calibrate",
              "instamatic.camera",
              "instamatic.config",
              "instamatic.experiments",
              "instamatic.formats",
              "instamatic.gui",
              "instamatic.processing",
              "instamatic.TEMController"],

    install_requires=["numpy", "comtypes", "scipy", "scikit-image", "pyyaml", "lmfit", "h5py", "tqdm"],

    package_data={
        "": ["LICENCE",  "readme.md", "setup.py"],
    },

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
            'instamatic.learn                         = scripts.learn:main_entry',
            # explore
            'instamatic.browser                       = scripts.browser:main',
            'instamatic.viewer                        = scripts.viewer:main',
        ]
    }
)

