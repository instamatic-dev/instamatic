# Configuration

Instamatic can be configured through a series of yaml files. `settings.yaml` and `defaults.yaml` at the root of the config directory, and three subdirectories (`microscope`, `calibration`, `camera`) that hold the specific configuration for the microscope set up.

```bash
$ENV:Instamatic
+-- config  
    +-- settings.yaml  
    +-- defaults.yaml  
    +-- microscope  
    |   +-- jeol-2100.yaml  
    |   +-- simulated.yaml  
    +-- camera  
    |   +-- timepix.yaml  
    |   +-- simulated.yaml  
    +-- calibration  
        +-- calibration-1.yaml  
        +-- calibration-2.yaml
```

By default, instamatic looks for the `config` directory in `%APPDATA%/instamatic`. This directory is created automatically with the default config files on first use. The config directory is printed when the program is started. The default location can be overriden using the `Instamatic` environment variable, i.e. in Powershell: `$ENV:Instamatic = "C:/Instamatic"`. In the portable installation, the config directory is in the root directory as defined by the `Instamatic` environment variable.

You can run:
```bash
instamatic.autoconfig.exe
```
To help generate some of the input files (in particular templates for the microscope/calibration files).

Examples of configuration files can be found [here](https://github.com/instamatic-dev/instamatic/tree/master/instamatic/config).

## settings.yaml

This is the global configuration file for `instamatic`. It defines which microscope / camera setup to use through the `microscope`, `camera`, and `calibration` settings.

**microscope**  
Name of the microscope calibration file use. For example, if this is set to `jeol-2100`, instamatic will look for the config file `jeol-2100.yaml` in the `config/microscope` directory.

**camera**  
Name of the camera file to use. Instamatic will look for the corresponding `.yaml` in the `config/camera` directory.

**calibration**  
Name of the calibration file to use. Instamatic will look for the corresponding `.yaml` file in the `config/calibration` directory.

**simulate**
Run instamatic in simulation mode. This simulates the connection to the microscope and the camera.

**data_directory**  
Default path to where data should be stored, i.e. `C:/instamatic`.

**flatfield**  
Path to tiff file containing flatfield, i.e. `C:/instamatic/flatfield.tiff`. Leave blank if no flatfield should be applied.

**use_tem_server**  
Use the tem server with the given host/port below. If instamatic cannot find the tem server, it will start a new temserver in a subprocess. The tem server can be started using `instamatic.temserver.exe`. This helps to isolate the microscope communication. Instamatic will connect to the server via sockets. The main advantage is that a socket client can be run in a thread, whereas a COM connection makes problems if it is not in main thread.

**tem_server_host**  
Set this to `localhost` if the TEM server is run locally. To make a remote connection over the network, use `'0.0.0.0'` on the server (start using `instamatic.temserver.exe`, and the ip address of the server on the client.

**tem_server_port**  
The server port, default: `8088`.

**tem_require_admin**
Some microscopes require admin rights to access their API, set `tem_require_admin: True` to enable some checks for admin rights and request UAC elevation before enabling the connection. Default: `False`.

**use_cam_server**  
Use the cam server with the given host/port below. If instamatic cannot find the cam server, it will start a new camserver in a subprocess. The cam server can be started using `instamatic.camserver.exe`. This helps to isolate the camera communication from the main program. Instamatic will connect to the server via sockets. The main advantage is that a socket client can be run in a thread, whereas a COM connection makes problems if it is not in main thread.

**cam_server_host**  
Set this to `localhost` if the cam server is run locally. To make a remote connection over the network, use `'0.0.0.0'` on the server (start using `instamatic.camserver.exe`), and the ip address of the server on the client.

**cam_server_port**  
The server port, default: `8087`.

**cam_use_shared_memory**  
Use [shared memory interface](https://docs.python.org/3/library/multiprocessing.shared_memory.html) for fast IPC of image data if the camera interface runs on the same computer as `instamatic` (Python 3.8+ only).

**indexing_server_exe**  
After data are collected, the path where the data are saved can be sent to this program via a socket connection for automated data processing. Available are the dials indexing server (`instamatic.dialsserver.exe`) and the XDS indexing server (`instamatic.xdsserver.exe`).

**indexing_server_host**  
IP to use for the indexing server, similar to above.

**indexing_server_port**  
Port to use for the indexing server, default: `8089`.

**dials_script**  
The script that is run when the dials indexing server is used..

**cred_relax_beam_before_experiment**  
Relax the beam before a CRED experiment (for testing only), default: `false`.

**cred_track_stage_positions**  
Track the stage position during a CRED experiment (for testing only), default: `false`.

**modules**  
List of modules to load for the GUI, must be one of {`cred`, `cred_tvips`, `cred_fei`, `sed`, `autocred`, `red`, `machine_learning`, `ctrl`, `debug`, `about`, `io`}.

**Goniotool settings**  
For JEOL only, automatically set the rotation speed via Goniotool (`instamatic.goniotool.exe`). These variables set up the remote connection.

```yaml
`use_goniotool: False
`goniotool_server_host: 'localhost'
`goniotool_server_port: 8090
```

**FEI server settings**  
Define here the host/port for InsteaDMatic to control the rotation speed on a FEI/TFS system. `InsteaDMatic` connects to an instance of `instamatic.temserver_fei.exe` running on this address,, which in turn connects to the microscope.

```yaml
fei_server_host: '192.168.12.1'
fei_server_port: 8091
```

**VM indexing server (XDS)**  
Automatically submit the data to an indexing server running in a VM (VirtualBox).

```yaml
use_VM_server_exe: False
VM_server_exe: 'instamatic.VMserver.exe'
VM_server_host: 'localhost'
VM_server_port: 8092
VM_ID: "Ubuntu 14.04.3"
VM_USERNAME: "lab6"
VM_PWD: "testtest"
VM_STARTUP_DELAY: 50
VM_DESKTOP_DELAY: 20
VM_SHARED_FOLDER: F:\SharedWithVM
```

## defaults.yaml

This file contains the default parameters for some functions.

## calibration.yaml

In this file the calibration of the pixelsizes can be specified, both in diffraction and imaging modes. This file is must be located the `config/calibration` directory, and can have any name as defined in `settings.yaml`. To begin with, the values can be safely set to 1.0, as their importance depends on the experiment you are running. The dictionary tree is defined below:

```bash
+-- calibration.yaml  
    +-- name: str
    +-- diff
        +-- pixelsize: dict
    +-- mag
        +-- flipud: bool
        +-- fliplr: bool
        +-- rot90: dict
        +-- pixelsize: dict
        +-- stagematrix: dict
```

Here, `mag` can be any of the mag modes, i.e. `mag1`, `lowmag`, `samag`. Each child item contains some info about the orientation and size of the camera.

**name**  
Name of the corresponding camera interface. This variable is not used currently in the code.

**diff/pixelsize**  
Give here a list of camera lengths (as reported by the TEM) and the corresponding pixel dimensions in reciprocal angstrom (px/Å), separated by a `:`, for example:

```yaml
diff:
  pixelsize:
    150: 0.02942304
    200: 0.02206728
    250: 0.017653824
```

**mag/flipud**
Flip the images around the horizontal axes. This is used to globally modify all images taken by the camera using `ctrl.get_image()` or `ctrl.get_rotated_image()` to make them in line with the fluorescence screen or otherwise. Default: False.

**mag/fliplr**
Similar to above, except that the images are flipped around the vertical axis. Default: False.

**mag/rot90**
Similar to above, this defines a rotation to be applied to every image. This was implemented to circumvent an issue on our TEM where images where the lenses incurred a -90 degrees rotation from lowmag 250x to 1000x. If not defined, the default is 0.

```yaml
lowmag:
  rot90:
    150: 0
    200: 0
    250: 3
```

**mag/pixelsize**  
Give here the magnification and pixel size for images taken in lowmag/mag1 mode in nanometer (nm), for example:

```yaml
lowmag:
  pixelsize:
    150: 77.71
    200: 59.31
    250: 45.36
```

**mag/stagematrix**  
This is a mapping of the pixel coordinates to the stage coordinates. These are used to convert from detected shifts in pixel coordinates (i.e. using cross correlation) to the corresponding translation of the stage. They can be calibrated using `instamatic.calibrate_stagematrix.exe`.

The stagematrix is the *inverse* of the one defined using SerialEM (`StageToCameraMatrix` in `SerialEMCalibration.txt`) via _Calibration_ > _Image & Stage Shift_ > _Stage Shift_ ([link](http://bio3d.colorado.edu/SerialEM/betaHlp/html/menu_calibration.htm#hid_calibration_stageshift)). Note that the stagematrix is dependent on the orientation of the images.

```yaml
mag:
  stagematrix:
    250: [ 0.276258, -21.935572, 22.306572, 0.565116 ]
    300: [ 0.331509, -26.322686, 26.767886, 0.678139 ]
    400: [ 0.442012, -35.096915, 35.690515, 0.904185 ]
```

## camera.yaml:

This file holds the specifications of the camera. This file is must be located the `config/camera` directory, and can have any name as defined in `settings.yaml`.

**interface**  
Give the interface of the camera interface to connect to, for example: `timepix`/`emmenu`/`simulate`/`gatan`. Leave blank to load the camera specs, but do not load the camera module (this also turns off the videostream gui).

**default_binsize**  
Set the default binsize, default: `1`.

**default_exposure**  
Set the default exposure in seconds, i.e. `0.02`.

**dimensions**  
Give the dimensions of the camera at binning 1, for example: `[516, 516]`.

**dynamic_range**  
Give the maximum counts of the camera, for example: `11800`. This is used for the contrast in the liveview and the flatfield collection.

**physical_pixelsize**  
The physical size of a pixel in millimeter, for example: `0.055`.

**possible_binsizes**  
Give here a list of possible binnings, for example: `[1]` or `[1, 2, 4]`.

**camera_rotation_vs_stage_xy**  
In radians, give here the rotation of the position of the rotation axis with respect to the horizontal. Used for diffraction only. Corresponds to the rotation axis in RED and PETS, for example: `-2.24`. You can find the rotation axis for your setup using the script `edtools.find_rotation_axis` available from [here](https://github.com/instamatic-dev/edtools#find_rotation_axispy).

**stretch_amplitude**  
Use `instamatic.stretch_correction` to characterize the lens distortion. The numbers here are used to calculate the XCORR/YCORR maps. The amplitude is the percentage difference between the maximum and minimum eigenvectors of the ellipsoid, i.e. if the amplitude is `2.43`, eig(max)/eig(min) = 1.0243. You can use the program `instamatic.stretch_correction` available [here](https://github.com/instamatic-dev/instamatic/blob/master/docs/programs.md#instamaticstretch_correction) on some powder patterns to define these numbers.

**stretch_azimuth**  
The azimuth is gives the direction of the maximum eigenvector with respect to the horizontal X-axis (pointing right) in degrees, for example: `83.37`.

**correction_ratio**  
Set the correction ratio for the cross pixels in the Timepix detector, default: 3.

**calib_beamshift**  
Set up the grid and stepsize for the calibration of the beam shift in SerialED. The calibration will run a grid of `stepsize` by `stepsize` points, with steps of `stepsize`. The stepsize must be given corresponding to 2500x, and instamatic will then adjust the stepsize depending on the actual magnification, if needed. For example:

```yaml
{gridsize: 5, stepsize: 500}
```

**calib_directbeam**  
Set up the grid and stepsize for the calibration of the direct beam in diffraction mode, for example:

```yaml
  BeamShift: {gridsize: 5, stepsize: 300}
  DiffShift: {gridsize: 5, stepsize: 300}
```

## microscope.yaml

This file holds all the specifications of the microscope as necessary. It is important to set up the camera lengths, magnifications, and magnification modes. This file is must be located the `microscope/camera` directory, and can have any name as defined in `settings.yaml`.

```bash
+-- microscope.yaml  
    +-- interface: str
    +-- wavelength: float
    +-- ranges
        +-- diff: list
        +-- mag: list
```

**interface**  
Defines the the microscope interface to use, i.e. 'jeol', 'fei', 'simulate'.

**wavelength**  
The wavelength of the microscope in Ansgtroms. This is used to generate some of the output files after data collection, i.e. for 120kV: `0.033492`, 200kV: `0.025079`, or 300 kV: `0.019687`. A useful website to calculate the de Broglie wavelength can be found [here](https://www.ou.edu/research/electron/bmz5364/calc-kv.html).

**ranges**
In the child items, all the magnification ranges must be defined. They can be obtained through the API using: `ctrl.magnification.get_ranges()`. This will step through all the magnifications and return them as a dictionary.

**range/diff**  
List here the available camera lengths available on the microscope in ascending order:

```yaml
ranges:
  diff: [150, 200, 250, 300, 400, 500, 600, 800, 1000,
    1200, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
```

**ranges/mag**  
Here, mag must be one of the known mag ranges, i.e. `lowmag`, `mag1`, `samag`. What follows is a list of all available magnifications on the microscope in ascending order, for example:
```yaml
ranges:
  mag1: [2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000,
    12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000,
    80000, 100000, 120000, 150000, 200000, 250000, 300000,
    400000, 500000, 600000, 800000, 1000000, 1200000,
    1500000, 2000000]
```
