[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.2026774.svg)](https://doi.org/10.5281/zenodo.2026774)

# Instamatic

Instamatic is a Python program that is being developed with the aim to automate the collection of electron diffraction data. At the core is a Python library for transmission electron microscope experimental control with bindings for the JEOL/FEI microscopes and interfaces to the gatan/timepix/tvips cameras. Routines have been implemented for collecting serial electron diffraction (serialED), continuous rotation electron diffraction (cRED), and stepwise rotation electron diffraction (RED) data.

Instamatic is distributed as a portable stand-alone installation that includes all the needed libraries from: https://github.com/stefsmeets/instamatic/releases. However, the most up-to-date version of the code (including bugs!) is available from this repository.

Electron microscopes supported: 

- JEOL microscopes with the TEMCOM library
- FEI microscopes via the scripting interface

Cameras supported:

- ASI Timepix (including live-view GUI)
- Gatan cameras through DM plugin
- TVIPS cameras through EMMENU4 API

Instamatic has been extensively tested on a JEOL-2100 with a Timepix camera, and is currently being developed on a JEOL-1400 and JEOL-3200 with TVIPS cameras.

A DigitalMicrograph script for collecting cRED data on a OneView camera (or any Gatan camera) can be found in the [dmscript](https://github.com/stefsmeets/instamatic/tree/master/dmscript) directory.

## Reference

If you find this software useful, please consider citing one of the references below and/or refer to the source code in your publications:

- S. Smeets, B. Wang, M.O. Cichocka, J. Ångström, and W. Wan, (2018, December 7). Instamatic (Version 1.0.0). Zenodo. http://doi.org/10.5281/zenodo.2026774

Some of the methods implemented in Instamatic are described in: 

- M.O. Cichocka, J. Ångström, B. Wang, X. Zou, and S. Smeets, [High-throughput continuous rotation electron diffraction data acquisition via software automation](http://dx.doi.org/10.1107/S1600576718015145), J. Appl. Cryst. (2018). 51, 1652–1661, 

- S. Smeets, X. Zou, and W. Wan, [Serial electron crystallography for structure determination and phase analysis of nanocrystalline materials](http://dx.doi.org/10.1107/S1600576718009500), J. Appl. Cryst. (2018). 51, 1262–1273

## Documentation

See [the documentation](docs) for how to set up and use Instamatic.

- [TEMController](docs/tem_api.md)
- [Config](docs/config.md)
- [Reading and writing image data](docs/formats.md)
- [Setting up instamatic](docs/setup.md)
- [Programs included](docs/programs.md)
- [GUI and Module system](docs/gui.md)

Use `pydoc` to access the full API reference: `pydoc -b instamatic`

## Requirements

 - Python3.6
 - comtypes
 - lmfit
 - matplotlib
 - numpy
 - pandas
 - Pillow
 - scipy
 - scikit-image
 - tqdm
 - pyyaml
 - h5py
 - IPython

Requirements can be installed via:

    pip install -r requirements.txt

## Installation

The simplest way is to download the portable installation with all libraries/dependencies included: https://github.com/stefsmeets/instamatic/releases/latest. Extract the archive, and open a terminal by double-clicking `start_Cmder.exe`.

Alternatively, the latest development version can always be obtained via:
    
    https://github.com/stefsmeets/instamatic/archive/master.zip

To install:

    pip install -r requirements.txt
    python setup.py install
