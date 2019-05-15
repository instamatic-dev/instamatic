# Useful programs and scripts

There are several programs coming with `instamatic`. Some of the more commonly used ones are defined here.

### instamatic

Start the instamatic GUI. The GUI is modular and can be defined using the config system. The GUI can be used to control the microscope and run the experiments. The GUI itself is further described on the GUI page.

Usage:
    
    instamatic

<!-- ### instamatic.serialed

Command line program to run the serial ED data collection routine.

Usage:
    
    instamatic.serialed -->

### instamatic.controller

Connect to the microscope and camera, and open an IPython terminal to interactively control the microscope. Useful for testing! It initializes the TEMController (accessible through the `ctrl` variable) using the parameters given in the `config`.

Usage:
    
    instamatic.controller

### instamatic.flatfield

This is a program that can collect and apply flatfield/darkfield corrections [link](https://en.wikipedia.org/wiki/Flat-field_correction). To do so, use a spread, bright beam on a hole in the carbon, or a clear piece of carbon film, and run:
    
    instamatic.flatfield --collect

This will collect 100 images and average them to determine the flatfield image. A darkfield image is also collected by applying the same routine with the beam blanked. Dead pixels are identified as pixels with 0 intensities. To apply these corrections:

    instamatic.flatfield image.tiff [image.tiff ..] -f flatfield.tiff [-d darkfield.tiff] [-o drc]
   
This will apply the flatfield correction (`-f`) and optionally the darkfield correction (`-d`) to images given as argument, and place the corrected files in directory `corrected` or as specified using `-o`.

### instamatic.stretch_correction

Program to determine the stretch correction from a series of powder diffraction patterns (collected on a gold or aluminium powder). It will open a GUI to interactively identify the powder rings, and calculate the orientation (azimuth) and extent (amplitude) of the long axis compared to the short axis. These can be used in the `config` under `camera.stretch_azimuth` and `camera.stretch_percentage`.

Usage:
    
    instamatic.stretch_correction powder_pattern.tiff

### instamatic.browser

Visualize the data collected (both images and diffraction data) in a serialED experiment. The `-s` flag attempts to stitch the images together.

Usage:
    
    instamatic.browser images/*.h5 [-s]

### instamatic.viewer

Simple image viewer to open any image collected collected using instamatic. Supported formats include [`hdf5`](http://www.h5py.org/), `TIFF`, and [`SMV`](https://strucbio.biologie.uni-konstanz.de/ccp4wiki/index.php/SMV_file_format).

Usage:
    
    instamatic.viewer image.tiff


### instamatic.temserver

This program initializes a connection to the TEM as defined in the config. On some setups it must be run in admin mode in order to establish a connection (on JEOL TEMs, wait for the beep!). The purpose of this program is to isolate the microscope connection in a separate process for improved stability of the interface in case `instamatic` crashes or is started and stopped frequently. For running the GUI, the temserver is required. Another reason is that it allows for remote connections from different PCs. The connection goes over a TCP socket.

The host and port are defined in `config/global.yaml`

Usage:

    instamatic.temserver


### instamatic.camserver

As with the temserver, the camserver controls the connection to the camera. It has been developed for usage with TVIPS cameras, because EMMENU allows scripting over the COM interface, which is otherwise difficult to integrate in the GUI. Sending data over the socket connection has considerable overhead (up to 100 ms for a 2k image), but it works well for small messages.

The host and port are defined in `config/global.yaml`

Usage:

    instamatic.camserver


### instamatic.install

This script sets up the paths for `instamatic`. It is necessary to run it at after first installation, and sometimes when the program is updated, or when the instamatic directory has moved.

Usage:

    instamatic.install
