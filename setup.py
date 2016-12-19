#!/usr/bin/env python

from setuptools import setup, find_packages
from os import path

# www.pythonhosted.org/setuptools/setuptools.html

setup(
    name="instamatic",
    version="0.2.1",
    description="Program for automatic data collection of diffraction snapshots on electron microscopes",

    author="Stef Smeets",
    author_email="stef.smeets@mmk.su.se",
    license="GPL",
    url="https://github.com/stefsmeets/instamatic",

    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],

    packages=["instamatic", "instamatic.camera"],

    install_requires=["numpy", "comtypes", "scikit-image", "pyyaml", "lmfit"],

    package_data={
        "": ["LICENCE",  "readme.md", "setup.py"],
    },

    entry_points={
        'console_scripts': [
            'instamatic                               = instamatic.experiment:main',
            'instamatic.gui                           = instamatic.experiment:main_gui',
            'instamatic.find_crystals                 = instamatic.find_crystals:find_crystals_entry',
            'instamatic.find_holes                    = instamatic.find_holes:find_holes_entry',
            'instamatic.camera                        = instamatic.camera.camera:main_entry',
            'instamatic.controller                    = instamatic.TEMController.TEMController:main_entry',
            'instamatic.viewer                        = instamatic.viewer:main',
            'instamatic.calibrate_stage_lowmag        = instamatic.calibrate.calibrate_stage_lowmag:main_entry',
            'instamatic.calibrate_stage_mag1          = instamatic.calibrate.calibrate_stage_mag1:main_entry',
            'instamatic.calibrate_beamshift           = instamatic.calibrate.calibrate_beamshift:main_entry',
            'instamatic.calibrate_directbeam          = instamatic.calibrate.calibrate_directbeam:main_entry',
            'instamatic.map_holes                     = instamatic.app:map_holes_on_grid_entry',
            'instamatic.goto_hole                     = instamatic.app:goto_hole_entry',
            'instamatic.prepare_experiment            = instamatic.app:prepare_experiment_entry',
            'instamatic.plot_experiment               = instamatic.app:plot_experiment_entry',
            'instamatic.update_experiment_with_coords = instamatic.app:update_experiment_with_hole_coords_entry',
        ]
    }
)

