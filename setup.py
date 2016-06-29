#!/usr/bin/env python

from setuptools import setup, find_packages
from os import path

# www.pythonhosted.org/setuptools/setuptools.html

setup(
    name="instamatic",
    version="0.0.2",
    description="Program for automatic data collection of diffraction snapshots on electron microscopes",

    author="Stef Smeets",
    author_email="stef.smeets@mmk.su.se",
    license="GPL",
    url="https://github.com/stefsmeets/instamatic",

    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],

    packages=["instamatic", "instamatic.camera", "instamatic.pyami", "instamatic.pyscope"],

    install_requires=["numpy"],

    package_data={
        "": ["LICENCE",  "readme.md", "setup.py"],
    },

    entry_points={
        'console_scripts': [
            'instamatic = instamatic.app:main',
            'find_crystals = instamatic.find_crystals:find_crystals_entry',
            'find_holes = instamatic.find_crystals:find_holes_entry',
            'instamatic.camera = instamatic.camera.camera:main_entry',
            'instamatic.controller = instamatic.TEMController:main_entry',
            'mrc2npy = instamatic.mrc2npy:main_entry',
        ]
    }

)
