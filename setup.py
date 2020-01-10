import os

from setuptools import find_packages
from setuptools import setup

packages = find_packages(exclude=['scripts'])

# grab __version__, __author__, etc.
exec(open('instamatic/version.py').read())


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


try:
    long_description = read('README.rst')
except OSError:
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
        'Programming Language :: Python :: 3.8',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Microsoft :: Windows',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces',
        'Topic :: Scientific/Engineering :: Chemistry',
        'Topic :: Software Development :: Libraries',
    ],

    packages=packages,

    install_requires=['numpy>=1.17.3',
                      'scipy>=1.3.2',
                      'pandas>=0.25.3',
                      'matplotlib>=3.1.2',
                      'scikit-image>=0.16.2',
                      'Pillow>=7.0.0',
                      'pywinauto>=0.6.8',
                      'comtypes>=1.1.7',
                      'lmfit>=1.0.0',
                      'PyYAML>=5.3',
                      'tifffile>=2019.7.26.2',
                      'h5py>=2.10.0',
                      'tqdm>=4.41.1',
                      'ipython>=7.11.1',
                      'mrcfile>=1.1.2',
                      'virtualbox>=2.0.0',
                      ],

    include_package_data=True,

    entry_points={
        'console_scripts': [
            # main
            'instamatic                               = instamatic.main:main',
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
            'instamatic.camserver                     = instamatic.server.cam_server:main',
            'instamatic.dialsserver                   = instamatic.server.dials_server:main',
            'instamatic.VMserver                      = instamatic.server.vm_ubuntu_server:main',
            'instamatic.xdsserver                     = instamatic.server.xds_server:main',
            'instamatic.temserver_fei                 = instamatic.server.TEMServer_FEI:main',
            'instamatic.goniotoolserver               = instamatic.server.goniotool_server:main',
            # setup
            'instamatic.autoconfig                    = instamatic.config.autoconfig:main',
        ],
    },
)
