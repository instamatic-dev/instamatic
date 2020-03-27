# Useful programs and scripts

There are several programs coming with `instamatic`. The documented ones are indicated marked with ✓.

- **Main**
  + [instamatic](#instamatic) (`instamatic.main:main`)
  + [instamatic.controller](#instamatic.controller) (`instamatic.TEMController.TEMController:main_entry`)
- **Experiments**
  + [instamatic.serialed](#instamatic.serialed) (`instamatic.experiments.serialed.experiment:main`)
  + [instamatic.camera](#instamatic.camera) (`instamatic.camera.camera:main_entry`)
- **Calibrate**
  + [instamatic.calibrate_stage_lowmag](#instamatic.calibrate_stage_lowmag) (`instamatic.calibrate.calibrate_stage_lowmag:main_entry`)
  + [instamatic.calibrate_stage_mag1](#instamatic.calibrate_stage_mag1) (`instamatic.calibrate.calibrate_stage_mag1:main_entry`)
  + [instamatic.calibrate_beamshift](#instamatic.calibrate_beamshift) (`instamatic.calibrate.calibrate_beamshift:main_entry`)
  + [instamatic.calibrate_directbeam](#instamatic.calibrate_directbeam) (`instamatic.calibrate.calibrate_directbeam:main_entry`)
  + [instamatic.flatfield](#instamatic.flatfield) (`instamatic.processing.flatfield:main_entry`)
  + [instamatic.stretch_correction](#instamatic.stretch_correction) (`instamatic.processing.stretch_correction:main_entry`)
- **Tools**
  + [instamatic.browser](#instamatic.browser) (`scripts.browser:main`)
  + [instamatic.viewer](#instamatic.viewer) (`scripts.viewer:main`)
  + [instamatic.defocus_helper](#instamatic.defocus_helper) (`instamatic.gui.defocus_button:main`)
  + [instamatic.find_crystals](#instamatic.find_crystals) (`instamatic.processing.find_crystals:main_entry`)
  + [instamatic.learn](#instamatic.learn) (`scripts.learn:main_entry`)
- **Server**
  + [instamatic.temserver](#instamatic.temserver) (`instamatic.server.tem_server:main`)
  + [instamatic.camserver](#instamatic.camserver) (`instamatic.server.cam_server:main`)
  + [instamatic.dialsserver](#instamatic.dialsserver) (`instamatic.server.dials_server:main`)
  + [instamatic.VMserver](#instamatic.VMserver) (`instamatic.server.vm_ubuntu_server:main`)
  + [instamatic.xdsserver](#instamatic.xdsserver) (`instamatic.server.xds_server:main`)
  + [instamatic.temserver_fei](#instamatic.temserver_fei) (`instamatic.server.TEMServer_FEI:main`)
  + [instamatic.goniotoolserver](#instamatic.goniotoolserver) (`instamatic.server.goniotool_server:main`)
- **Setup**
  + [instamatic.autoconfig](#instamatic.autoconfig) (`instamatic.config.autoconfig:main`)
  + [instamatic.install](#instamaticinstall) (Cmder)

## instamatic

Start instamatic with various functions (see below). If no arguments are given, start the instamatic GUI. The GUI is modular and can be defined using the config system. The GUI can be used to control the microscope and run the experiments. The GUI itself is further described on the GUI page.

**Usage:**  
```bash
instamatic [-h] [-s SCRIPT] [-n NAV_FILE] [-a] [-l LOCATE] [-o SHOW]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-s SCRIPT, --script SCRIPT`:  
 Run the script given  
`-n NAV_FILE, --nav NAV_FILE`:  
 Load the given .nav file  
`-a, --acquire_at_items`:  
 Run the script file `--script` at every point marked with `Acquire` in the nav file `--nav`.  
`-o SHOW, --open SHOW`:  
Open the requested directory and exit, see `--locate`.  


## instamatic.controller

Connect to the microscope and camera, and open an IPython terminal to interactively control the microscope. Useful for testing! It initializes the TEMController (accessible through the `ctrl` variable) using the parameters given in the `config`.

**Usage:**  
```bash
instamatic.controller [-h] [-u] [-c TEM_NAME] [-t CAM_NAME]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-u, --simulate`:  
Simulate microscope connection (default: False)  
`-c TEM_NAME, --camera TEM_NAME`:  
 Camera configuration to load.  


## instamatic.serialed

Command line program to run the serial ED data collection routine.

**Usage:**  
```bash
instamatic.serialed [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.camera

Simple program to acquire image data from the camera.

**Usage:**  
```bash
instamatic.camera [-h] [-b N] [-e N] [-o image.png] [-d] [-s]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-b N, --binsize N`:  
Binsize to use. Must be one of 1, 2, or 4 (default 1)  
`-e N, --exposure N`:  
Exposure time (default 0.5)  
`-d, --display`:  
Show the image (default True)  
`-s, --series`:  
Enable mode to take a series of images (default False)  


## instamatic.calibrate_stage_lowmag

Program to calibrate the lowmag mode (100x) of the microscope (Deprecated).

**Usage:**  
```bash
instamatic.calibrate_stage_lowmag [-h] [IMG [IMG ...]]
```
**Positional arguments:**  
`IMG`:  
Perform calibration using pre-collected images. The first image  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.calibrate_stage_mag1

Program to calibrate the mag1 mode of the microscope (Deprecated).

**Usage:**  
```bash
instamatic.calibrate_stage_mag1 [-h] [IMG [IMG ...]]
```
**Positional arguments:**  
`IMG`:  
Perform calibration using pre-collected images. The first image  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.calibrate_beamshift

Program to calibrate the beamshift of the microscope (Deprecated).

**Usage:**  
```bash
instamatic.calibrate_beamshift [-h] [IMG [IMG ...]]
```
**Positional arguments:**  
`IMG`:  
Perform calibration using pre-collected images. The first image  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.calibrate_directbeam

Program to calibrate the diffraction shift (PLA) to correct for beamshift movements (Deprecated).

**Usage:**  
```bash
instamatic.calibrate_directbeam [-h] [IMG [IMG ...]]
```
**Positional arguments:**  
`IMG`:  
Perform calibration using pre-collected images. They must be  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.flatfield

This is a program that can collect and apply flatfield/darkfield corrections [link](https://en.wikipedia.org/wiki/Flat-field_correction). To do so, use a spread, bright beam on a hole in the carbon, or a clear piece of carbon film, and run:

    instamatic.flatfield --collect

This will collect 100 images and average them to determine the flatfield image. A darkfield image is also collected by applying the same routine with the beam blanked. Dead pixels are identified as pixels with 0 intensities. To apply these corrections:

    instamatic.flatfield image.tiff [image.tiff ..] -f flatfield.tiff [-d darkfield.tiff] [-o drc]

This will apply the flatfield correction (`-f`) and optionally the darkfield correction (`-d`) to images given as argument, and place the corrected files in directory `corrected` or as specified using `-o`.

**Usage:**  
```bash
instamatic.flatfield [-h] [-f flatfield.tiff] [-d darkfield.tiff]
                     [-o DRC] [-c]
                     [image.tiff [image.tiff ...]]
```
**Positional arguments:**  
`image.tiff`:  
Image file paths/pattern  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-f flatfield.tiff, --flatfield flatfield.tiff`:  
 Path to flatfield file  
`-o DRC, --output DRC`:  
Output directory for image files  
`-c, --collect`:  
Collect flatfield/darkfield images on microscope  


## instamatic.stretch_correction

Program to determine the stretch correction from a series of powder diffraction patterns (collected on a gold or aluminium powder). It will open a GUI to interactively identify the powder rings, and calculate the orientation (azimuth) and extent (amplitude) of the long axis compared to the short axis. These can be used in the `config` under `camera.stretch_azimuth` and `camera.stretch_percentage`.

**Usage:**  
```bash
instamatic.stretch_correction [-h] powder_pattern.tiff
```
**Positional arguments:**  
`powder_pattern.tiff`:  
Diffraction pattern (TIFF) from a nanocrystalline  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.browser

Program for indexing electron diffraction images.

Example:

    instamatic.browser images/*.tiff -r results.csv

**Usage:**  
```bash
instamatic.browser [-h] [-s] [FILE]
```
**Positional arguments:**  
`FILE`:  
File pattern to image files  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-s, --stitch`:  
Stitch images together.  


## instamatic.viewer

Simple image viewer to open any image collected collected using instamatic. Supported formats include `TIFF`, `MRC`, [`HDF5`](http://www.h5py.org/), and [`SMV`](https://strucbio.biologie.uni-konstanz.de/ccp4wiki/index.php/SMV_file_format).

**Usage:**  
```bash
instamatic.viewer [-h] IMG
```
**Positional arguments:**  
`IMG`:  
Image to display (TIFF, HDF5, MRC, SMV).  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.defocus_helper

Tiny button to focus and defocus the diffraction pattern.

**Usage:**  
```bash
instamatic.defocus_helper [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.find_crystals

Find crystals in images.

**Usage:**  
```bash
instamatic.find_crystals [-h] [IMG [IMG ...]]
```
**Positional arguments:**  
`IMG`:  
Images to find crystals in.  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.learn

Predict whether a crystal is of good or bad quality by its diffraction pattern.

**Usage:**  
```bash
instamatic.learn [-h] PAT
```
**Positional arguments:**  
`PAT`:  
File pattern to glob for images (HDF5), i.e. `images/*.h5`.  

**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.temserver

Connects to the TEM and starts a server for microscope communication. Opens a socket on port localhost:8088.

This program initializes a connection to the TEM as defined in the config. On some setups it must be run in admin mode in order to establish a connection (on JEOL TEMs, wait for the beep!). The purpose of this program is to isolate the microscope connection in a separate process for improved stability of the interface in case instamatic crashes or is started and stopped frequently. For running the GUI, the temserver is required. Another reason is that it allows for remote connections from different PCs. The connection goes over a TCP socket.

The host and port are defined in `config/settings.yaml`.

The data sent over the socket is a pickled dictionary with the following elements:

- `func_name`: Name of the function to call (str)
- `args`: (Optional) List of arguments for the function (list)
- `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

The response is returned as a pickle object.

**Usage:**  
```bash
instamatic.temserver [-h] [-t MICROSCOPE]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.camserver

Connects to the camera and starts a server for camera communication. Opens a socket on port localhost:8087.

This program initializes a connection to the camera as defined in the config. This separates the communication from the main process and allows for remote connections from different PCs. The connection goes over a TCP socket.

The host and port are defined in `config/settings.yaml`.

The data sent over the socket is a pickled dictionary with the following elements:

- `attr_name`: Name of the function to call or attribute to return (str)
- `args`: (Optional) List of arguments for the function (list)
- `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

The response is returned as a pickle object.

**Usage:**  
```bash
instamatic.camserver [-h] [-c CAMERA]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.dialsserver

Starts a simple server to send indexing jobs to. Runs `-h` for every job sent to it. Opens a socket on port localhost:8089.

The data sent to the server is a dict containing the following elements:

- `path`: Path to the data directory (str)
- `rotrange`: Total rotation range in degrees (float)
- `nframes`: Number of data frames (int)
- `osc`: Oscillation range in degrees (float)

**Usage:**  
```bash
instamatic.dialsserver [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.VMserver

The script sets up socket connection between `instamatic` and `VirtualBox` software via `virtualbox` python API. Therefore, `VirtualBox` and the corresponding SDK need to be installed before running this command. This script is developed particularly for the possibility of running `XDS` under windows 7 or newer, a system which a lot of TEM computers may be using.

After installation of VirtualBox and the corresponding SDK, `XDS` needs to be installed correctly in the guest Ubuntu system. In addition, a shared folder between `VirtualBox` and windows system needs to be set up properly in order for the server to work.

The host and port are defined in `config/settings.yaml`.

**Usage:**  
```bash
instamatic.VMserver [-h] [-shelxt] [-c a b c al be ga] [-s SPGR]
                    [-m Xn [Ym ...]]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  
`-shelxt`:  
Run SHELXT when xds ASCII HKL file is generated.  
`-s SPGR, --spgr SPGR`:  
Space group.  


## instamatic.xdsserver

Starts a simple XDS server to send indexing jobs to. Runs XDS for every job sent to it. Opens a socket on port localhost:8089.

The data sent to the server as a bytes string containing the data path (must contain `cRED_log.txt`).

**Usage:**  
```bash
instamatic.xdsserver [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.temserver_fei

Utility script to enable rotation control from a dmscript. See [https://github.com/stefsmeets/instamatic/tree/master/dmscript] for usage.

**Usage:**  
```bash
instamatic.temserver_fei [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.goniotoolserver

Connects to `Goniotool.exe` and starts a server for network communication. Opens a socket on port localhost:8090.

The host and port are defined in `config/settings.yaml`.

The data sent over the socket is a pickled dictionary with the following elements:

- `func_name`: Name of the function to call (str)
- `args`: (Optional) List of arguments for the function (list)
- `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

The response is returned as a pickle object.

**Usage:**  
```bash
instamatic.goniotoolserver [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  


## instamatic.autoconfig

This tool will help to set up the configuration files for `instamatic`.
It establishes a connection to the microscope and reads out the camera lengths and magnification ranges.

**Usage:**  
```bash
instamatic.autoconfig [-h]
```
**Optional arguments:**  
`-h, --help`:  
show this help message and exit  

## instamatic.install

This script sets up the paths for `instamatic`. It is necessary to run it at after first installation, and sometimes when the program is updated, or when the instamatic directory has moved.

Usage:

    instamatic.install
