[![DOI](https://zenodo.org/badge/85934744.svg)](https://zenodo.org/badge/latestdoi/85934744)

# Instamatic

Python program to collect serial and rotation electron diffraction data. Included is a Python library with bindings for the JEOL microscope, and orius/timepix camera, and data collection routines for collecting serial electron diffraction (serial ED) and continuous rotation electron diffraction (cRED) data.

## Usage

Start the gui by typing `instamatic` in the command line.

![Main interface](docs/gui_main.png)

On the left side, a live view of the camera will be shown. On the top, there are some fields to change the output of the view. The exposure time for the live view, brightness, and display range can be changed here. Pressing the `Save Image` button will dump the current frame to a tiff file in the active directory.

On the right side, there is a pane for file i/o, and the available modules for data collection.

### Data i/o

This panel deals with input and output of the experimental data.

![Input and output](docs/gui_io.png)

* **Directory**: Root directory to work in. By default this is C:/instamatic/work_$date/

* **Sample name and number**: This determines the subdirectory where experimental data are stored. The number is automatically incremenbed when a new experiment is started. Data are never overwritten.

* **Flatfield**: Here the path to the flatfield image can be specified. This hardly needs to be changed.

* **Open work directory**: Open the current work directory, which is a combination of the root directory, sample name, and experiment number. In this case `C:/instamatic/work_2017-11-19/experiment_1`. All experimental data for the current experiment will be saved here.

* **Open config directory**: By default `%APPDATA%/instamatic/`. The configuration files for the microscope, camera, and calibration files go here.

* **Delete last experiment**: Sometimes, a data collection will go wrong... Pressing this button will mark the last experiment directy for deletion. It will not actually delete anything.

### serialED data collection

Serial electron diffraction (serialED) is a technique to collect diffraction data on a large number of crystals. One diffraction pattern per crystal is collected. These can then be combined for structure determination, or used for screening/phase analysis.

![serial electron diffraction pane](docs/gui_serialed.png)

Data collection can be started from the ‘serialED’ tab by pressing the ‘Start Collection’ button. Follow the instructions in the terminal to setup and calibrate the experiment.

* **Scan area**: radius for the area to scan area for crystals (in micrometer).
* **Exp. time image**: Exposure time for images.
* **Exp. time diff**: Exposure time for diffraction pattern.
* **Brightness**: Default value for the brightness of the focused beam.
* **Spot size**: Spot size to use.

### cRED data collection

Continuous RED (cRED) data collection can be started from the ‘cRED’ tab.

The data collection procedure can be initiated by pressing ‘Start Collection’. The program will then wait for the rotation to start. The moment the pedal is pressed to start the rotation, the program will start the data collection with the specified options. Do not release your foot until after you press ‘Stop Collection’. This will signal the program to stop data collection, and write the images. Images are written in TIFF, MRC, and SMV format. Input files for REDp (.ed3d) and XDS (XDS.INP) are also written.

![Continous rotation electron diffraction pane](docs/gui_cred.png)

* **Exposure time**: change the data collection time for each image.
* **Beam unblanker**: If this option is selected, the beam will be automatically unblanked when data collection starts, and blanked after data collection has finished (i.e. after ‘Stop Collection’ has been pressed)

### Image interval
With this feature, an image of the crystal will be shown every N frames. This is useful to control the position of the crystal in the beam for more reliable and reproducable data collections. This is achieved by applying a small defocus (diffraction focus) to every Nth image. a small defocus of the diffraction focus. If the defocus is large enough, this will show a view of the crystal in the aperture. 

* **Enable Image interval**: This option will enable the image interval.
* **Image interval**: Change the interval at which the image will be defocused. For example, if the value is 10, then every 10th image will be defocused.
* **Diff. defocus**: This is the defocus value to apply. It is better not to make this value too large, because the larger the difference with the proper diffraction focus, the longer the lenses need to recover. The microscope has to switch to the defocus value, take an image, and back within the time it takes to collect a single image (i.e. 0.5 s in this example). 
* **Toggle defocus**: This toggle applies the defocus value, which is used for checking. It does not affect the data collection.


## Programs included

### instamatic

Start the main instamatic experimental window to start a continuous RED or serial ED experiment.

Usage:
    
    instamatic

<!-- ### instamatic.serialed

Command line program to run the serial ED data collection routine.

Usage:
    
    instamatic.serialed -->

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
```python
from instamatic.TEMController import initialize
ctrl = initialize(cam="timepix")
```   
The `ctrl` object allows full control over the electron microscope. For example, to read out the position of the sample stage:
```python
xy = ctrl.stageposition.xy
print xy
```
To move to a different position:
```python
ctrl.stageposition.xy = 10000, 20000
```
A convenient way to experiment with the options available is to run `instamatic.controller`. This will initialize a `ctrl` object that can be played with interactively.

### Lenses

 * Brightness: `ctrl.brightness`
 * DiffFocus: `ctrl.difffocus` (only accessible in diffraction mode)
 * Magnification: `ctrl.magnification`

Lenses have one value, that can be accessed through the `.value` property.

All lens objects have the same API and behave in the same way, i.e.:
```python
ctrl.brightness.value = 1234
value = ctrl.brightness.value

ctrl.brightness.set(value=1234)
value = ctrl.brightness.get()
```
The Magnification lens has some extra features to increase/decrease the magnification:
```python
ctrl.magnification.increase()
ctrl.magnification.decrease()
```
as well as the index of magnification:
```python
index = ctrl.magnification.index
ctrl.magnfication.index = 0
```
### Deflectors

 * GunShift: `ctrl.gunshift`
 * GunTilt: `ctrl.guntilt`
 * BeamShift: `ctrl.beamshift`
 * BeamTilt: `ctrl.beamtilt`
 * DiffShift: `ctrl.diffshift`
 * ImageShift1: `ctrl.imageshift1`
 * ImageShift2: `ctrl.imageshift2`

Deflectors have two values (x and y), that can be accessed through the `.x` and `.y` properties

All deflectors have the same API and behave in the same way, i.e.:
```python
ctrl.beamshift.x = 1234
ctrl.beamshift.y = 4321
ctrl.beamshift.xy = 1234, 4321

x = ctrl.beamshift.x
y = ctrl.beamshift.y
xy = ctrl.beamshift.xy

ctrl.beamshift.get(x=1234, y=4321)
x, y = ctrl.beamshift.get()
```
Additionally, the values of the lenses can be set to the neutral values:
```python
ctrl.beamshift.neutral()
```
### Stage Position

The stageposition controls the translation of the samplestage (in nm):
```python
x = ctrl.stageposition.x
y = ctrl.stageposition.y
x, y = ctrl.stageposition.xy
ctrl.stageposition.xy = 0, 0
```
the height of the sample stage (in nm):
```python
z = ctrl.stageposition.z
ctrl.stageposition.z = 10
```
or rotation of the sample stage (in degrees), where `a` is the primary rotation axis, and `b` the secondary rotation axis:
```python
a = ctrl.stageposition.a
ctrl.stageposition.a = 25

b = ctrl.stageposition.b
ctrl.stageposition.b = -10
```
All stage parameters can be retrieved and applied using the get/set methods:
```python
x, y, z, a, b = ctrl.stageposition.get()
ctrl.stageposition.set(x=0, y=0)
ctrl.stageposition.set(a=25)
ctrl.stageposition.set(x=0, y=0, z=0, a=0, b=0)
```
The stage position can be neutralized (all values reset to 0) using:
```python
ctrl.stageposition.neutral()
```
### Camera

TODO

### Other functions

To blank the beam:
```python
ctrl.beamblank = True
```
To unblank the beam:
```python
ctrl.beamblank = False
```
To get the state of the beam blanker:
```python
ctrl.beamblank()
```
To switch modes:
```python
current_mode = ctrl.mode
ctrl.mode = "diff"  # choices: 'mag1', 'mag2', 'lowmag', 'samag', 'diff'
ctrl.mode_lowmag()
ctrl.mode_mag1()
ctrl.mode_samag()
ctrl.mode_diff()
```
To change spotsize:
```python
spot = ctrl.spotsize
ctrl.spotsize = 4  # 1, 2, 3, 4, 5
```
To retrieve all lens/deflector values in a dictionary:
```python
dct = ctrl.to_dict()
```
and to restore them:
```python
ctrl.from_dict(dct)
```
To store the current settings:
```python
ctrl.store(name="stash")
```
and to recall them:
```python
ctrl.restore(name="stash")
```
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

The simplest way is to download the portable installation with all libraries/dependencies included: https://github.com/stefsmeets/instamatic/releases. Extract the archive, and open a terminal by double-clicking `Cmder.exe`.

Download the latest release from https://github.com/stefsmeets/instamatic/releases/latest

    pip install -r requirements.txt
    python setup.py install

Alternatively, the latest development version can always be obtained via:
    
    https://github.com/stefsmeets/instamatic/archive/master.zip

## Citing instamatic

If you found this software useful, please consider citing the software:

Stef Smeets, Bin Wang, O. Magdalena Cichocka, Jonas Ångström, & Wei Wan. (2018, April 11). Instamatic (Version 0.6). Zenodo. https://doi.org/10.5281/zenodo.1090388
