# Instamatic

Program for automatic data collection of diffraction snapshots on electron microscopes. Included is a Python library with bindings for the JEOL microscope, and orius/timepix camera, and data collection routines for collecting serial electron diffraction (serial ED) and continuous rotation electrion diffraction (cRED) data.

## Usage

WIP

### serialED data collection

WIP

### cRED data collection

WIP

## Programs included

### instamatic

Start the main instamatic experimental window to start a continuous RED or serial ED experiment.

Usage:
    
    instamatic

### instamatic.serialed

Command line program to run the serial ED data collection routine.

Usage:
    
    instamatic.serialed

### instamatic.controller

Connect to the microscope and camera, and open an IPython terminal to interactively control the microscope. Useful for testing!

Usage:
    
    instamatic.controller

### instamatic.flatfield

Program to collect flatfield images.

Usage:
    
    instamatic.flatfield --collect

### instamatic.stretch_correction

Program to determine the stretch correction from a series of powder diffraction patterns.

Usage:
    
    instamatic.stretch_correction

### instamatic.browser

Visualize the data collected (both images and diffraction data) in a serial ED experiment. The `-s` flag attempts to stitch the images together.

Usage:
    
    instamatic.browser images/*.h5 [-s]

### instamatic.viewer

Open any image collected collected using instamatic.

Usage:
    
    instamatic.viewer image.tiff

## API

    from instamatic.TEMController import initialize
    ctrl = initialize(cam="timepix")
    
The `ctrl` object allows full control over the electron microscope. For example, to read out the position of the sample stage:
    
    xy = ctrl.stageposition.xy
    print xy

To move to a different position:
    
    ctrl.stageposition.xy = 10000, 20000

A convenient way to experiment with the options available is to run `instamatic.controller`. This will initialize a `ctrl` object that can be played with interactively.

## Requirements

- Python2.7
- numpy
- scipy
- scikit-image
- comptypes
- lmfit
- pyyaml
- h5py

## Installation

    pip install https://github.com/stefsmeets/instamatic/archive/master.zip

