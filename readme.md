![build](https://github.com/stefsmeets/instamatic/workflows/build/badge.svg)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/instamatic)
![PyPI](https://img.shields.io/pypi/v/instamatic.svg?style=flat)
![PyPI - Downloads](https://img.shields.io/pypi/dm/instamatic)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1090388.svg)](https://doi.org/10.5281/zenodo.1090388)

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

Instamatic has been extensively tested on a JEOL-2100 with a Timepix camera, and is currently being developed on a JEOL-1400 and JEOL-3200 with TVIPS cameras (XF416/F416).

A DigitalMicrograph script for collecting cRED data on a OneView camera (or any other Gatan camera) can be found at [dmscript](https://github.com/stefsmeets/InsteaDMatic).

## Installation

    pip install instamatic

Alternatively, download the portable installation with all libraries/dependencies included: https://github.com/stefsmeets/instamatic/releases/latest. Extract the archive, and open a terminal by double-clicking `start_Cmder.exe`.

## Documentation

See [the documentation](docs) for how to set up and use Instamatic.

- [TEMController](docs/tem_api.md)
- [Config](docs/config.md)
- [Reading and writing image data](docs/formats.md)
- [Setting up instamatic](docs/setup.md)
- [Programs included](docs/programs.md)
- [GUI and Module system](docs/gui.md)

Use `pydoc` to access the full API reference: `pydoc -b instamatic`

## Reference

If you found `Instamatic` useful, please consider citing it or one of the references below.

Each software release is archived on [Zenodo](https://zenodo.org), which provides a DOI for the project and each release. The project DOI [10.5281/zenodo.1090388](https://doi.org/10.5281/zenodo.1090388) will always resolve to the latest archive, which contains all the information needed to cite the release.

Alternatively, some of the methods implemented in `Instamatic` are described in:

- B. Wang, X. Zou, and S. Smeets, [Automated serial rotation electron diffraction combined with cluster analysis: an efficient multi-crystal workflow for structure determination](https://doi.org/10.1107/S2052252519007681), IUCrJ (2019). 6, 1-14

- B. Wang, [Development of rotation electron diffraction as a fully automated and accurate method for structure determination](http://www.diva-portal.org/smash/record.jsf?pid=diva2:1306254). PhD thesis (2019), Dept. of Materials and Environmental Chemistry (MMK), Stockholm University

- M.O. Cichocka, J. Ångström, B. Wang, X. Zou, and S. Smeets, [High-throughput continuous rotation electron diffraction data acquisition via software automation](http://dx.doi.org/10.1107/S1600576718015145), J. Appl. Cryst. (2018). 51, 1652–1661

- S. Smeets, X. Zou, and W. Wan, [Serial electron crystallography for structure determination and phase analysis of nanocrystalline materials](http://dx.doi.org/10.1107/S1600576718009500), J. Appl. Cryst. (2018). 51, 1262–1273
