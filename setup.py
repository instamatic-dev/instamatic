#!/usr/bin/env python

from setuptools import setup, find_packages
from os import path

# www.pythonhosted.org/setuptools/setuptools.html

setup(
    name="instamatic",
    version="0.3.3",
    description="Program for automatic data collection of diffraction snapshots on electron microscopes",

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
              "instamatic.processing",
              "instamatic.formats",
              "instamatic.gui",
              "instamatic.serialed",
              "instamatic.cred"],

    install_requires=["numpy", "comtypes", "scipy", "scikit-image", "pyyaml", "lmfit", "h5py"],

    package_data={
        "": ["LICENCE",  "readme.md", "setup.py"],
    },

    entry_points={
        'console_scripts': [
            # main
            'instamatic                               = instamatic.gui:main',
            'instamatic.gui                           = instamatic.gui:main',
            'instamatic.serialed                      = instamatic.serialed.experiment:main',
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
            # explore
            'instamatic.browser                       = scripts.browser:main',
            'instamatic.viewer                        = scripts.viewer:main',
        ]
    }
)

