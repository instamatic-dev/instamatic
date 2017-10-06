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

This is a program that can collect and apply flatfield/darkfield corrections [link](https://en.wikipedia.org/wiki/Flat-field_correction). To do so, use a spread, bright beam on a hole in the carbon, or a clear piece of carbon film, and run:
    
    instamatic.flatfield --collect

This will collect 100 images and average them to determine the flatfield image. A darkfield image is also collected by applying the same routine with the beam blanked. Dead pixels are identified as pixels with 0 intensities. To apply these corrections:

    instamatic.flatfield image.tiff [image.tiff ..] -f flatfield.tiff [-d darkfield.tiff] [-o drc]
   
This will apply the flatfield correction (`-f`) and optionally the darkfield correction (`-d`) to images given as argument, and place the corrected files in directory `corrected` or as specified using `-o`.

### instamatic.stretch_correction

Program to determine the stretch correction from a series of powder diffraction patterns. It will open a GUI to interactively identify the powder rings, and calculate the orientation (azimuth) and extent (amplitude) of the long axis compared to the short axis.

Usage:
    
    instamatic.stretch_correction powder_pattern.tiff

### instamatic.browser

Visualize the data collected (both images and diffraction data) in a serial ED experiment. The `-s` flag attempts to stitch the images together.

Usage:
    
    instamatic.browser images/*.h5 [-s]

### instamatic.viewer

Open any image collected collected using instamatic. Supported formats include [`hdf5`](http://www.h5py.org/), `TIFF`, and [`SMV`](https://strucbio.biologie.uni-konstanz.de/ccp4wiki/index.php/SMV_file_format).

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
- IPython (optional)
- matplotlib (optional)

## Installation

    pip install https://github.com/stefsmeets/instamatic/archive/master.zip

