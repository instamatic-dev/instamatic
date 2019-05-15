# Configuration

Instamatic can be configured through a series of yaml files. `global.yaml` at the root of the config directory, and three subdirectories (`microscope`, `calibration`, `camera`) that hold the specific configuration for the microscope set up.

By default, instamatic looks for the `config` directory in `%APPDATA%/Instamatic`. This directory is created automatically with the default config files on first use. The config directory is printed when the program is started. The default location can be overriden using the `Instamatic` environment variable, i.e. in Powershell: `$ENV:Instamatic = "C:/Instamatic"`. In the portable installation, the config directory is in the root directory as defined by the `Instamatic` environment variable.

Examples of configuration files can be found [here](https://github.com/stefsmeets/tree/master/instamatic/config).

## global.yaml

This is the global configuration file for `instamatic`. It defines which microscope / camera setup to use through the `microscope`, `camera`, and `calibration` settings. 

**microscope**  
name of the microscope calibration file use. For example, if this is set to `jeol-2100`, instamatic will look for the config file `jeol-2100.yaml` in the `config/microscope` directory.

**camera**  
name of the camera file to use. Instamatic will look for the corresponding `.yaml` in the `config/camera` directory.

**calibration**  
name of the calibration file to use. Instamatic will look for the corresponding `.yaml` file in the `config/calibration` directory.

**data_directory**  
Default path to where data should be stored, i.e. `C:/instamatic`

**flatfield**  
Path to tiff file containing flatfield, i.e. `C:/instamatic/flatfield.tiff`. Leave blank if  no flatfield should be applied.

**use_tem_server**  
use the tem server with the given host/port below. If instamatic cannot find the tem server, it will start a new temserver in a subprocess. The tem server can be started using `instamatic.temserver.exe`. This helps to isolate the microscope communication. Instamatic will connect to the server via sockets. The main advantage is that a socket client can be run in a thread, whereas a COM connection makes problems if it is not in main thread. 

**tem_server_host**  
Set this to `localhost` if the TEM server is run locally. To make a remote connection over the network, use '0.0.0.0' on the server, and the ip address of the server on the client.

**tem_server_port**  
the server port, default: 8088

**indexing_server_exe**  
After data are collected, the path where the data are saved can be sent to this program via a socket connection for automated data processing. Available are the dials indexing server (`instamatic.dialsserver.exe`) and the XDS indexing server (`instamatic.xdsserver.exe`)

**indexing_server_host**  
IP to use for the indexing server, similar to above.

**indexing_server_port**  
Port to use for the indexing server, default: 8089

**dials_script**  
The script that is run when the dials indexing server is used.

**cred_relax_beam_before_experiment**  
Relax the beam before a CRED experiment (for testing only), default: false

**cred_track_stage_positions**  
Track the stage position during a CRED experiment (for testing only), default: false

**modules**  
List of modules to load for the GUI, must be one of {`cred`, `cred_tvips`, `cred_fei`, `sed`, `autocred`, `red`, `machine_learning`, `ctrl`, `debug`, `about`, `io`}

## calibration.yaml

In this file the calibration of the pixel size can be given, both in diffraction and imaging modes. This file is must be located the `config/calibration` directory, and can have any name as defined in `global.yaml`.

**name**  
Name of the corresponding camera interface. This variable is not used currently in the code at present.

**diffraction_pixeldimensions**  
Give here a list of camera lengths (as reported by the TEM) and the corresponding pixel dimensions in reciprocal angstrom, separated by a `:`, for example:
```
250: 0.0040
300: 0.0050
...
```

**lowmag_pixeldimensions**  
Give here the magnification and pixel dimensions (x and y) for the lowmag mode in micrometer, for example:
```
1000: [0.044779, 0.044779]
1200: [0.037316, 0.037316]
 ...
```

**mag1_camera_dimensions**  
Give here the magnification and pixel dimensions of the entire camera in micrometer, for exmaple:
```
 8000: [9.86148864, 9.86148864]
10000: [7.99162368, 7.99162368]
  ...
```

## camera.yaml:

This file holds the specifications of the camera. This file is must be located the `config/camera` directory, and can have any name as defined in `global.yaml`.

**name**  
Give the name of the camera interface to connect to, for example: `timepix`/`emmenu`/`simulate`/`gatan`. Leave blank to load the camera specs, but do not load the camera module (this also turns off the videostream gui).

**default_binsize**  
Set the default binsize, default: 1

**default_exposure**  
Set the default exposure in seconds, i.e. 0.02

**dimensions**  
Give the dimensions of the camera at binning 1, for example: [516, 516]

**dynamic_range**  
Give the maximum counts of the camera, for example: 11800

**physical_pixelsize**  
The physical size of a pixel in micrometer, for example: 0.055

**possible_binsizes**  
Give here a list of possible binnings, for example: `[1]` or `[1, 2, 4]`

**camera_rotation_vs_stage_xy**  
In radians, give here the rotation of the position of the rotation axis with respect to the 
horizontal. Corresponds to the rotation axis in RED and PETS, for example: -2.24

**stretch_amplitude**  
Use `instamatic.stretch_correction` to characterize the lens distortion. The numbers here are used to calculate the XCORR/YCORR maps. The amplitude is the percentage difference between the maximum and minimum eigenvectors of the ellipsoid, i.e. if the amplitude is 2.43, eig(max)/eig(min) = 1.0243

**stretch_azimuth**  
The azimuth is gives the direction of the maximum eigenvector with respect to the horizontal X-axis (pointing right) in degrees, for example: 83.37

**correction_ratio**  
Set the correction ratio for the cross pixels in the Timepix detector, default: 3

**calib_beamshift**  
Set up the grid and stepsize for the calibration of the beam shift in SerialED, for example:
```
{gridsize: 5, stepsize: 500}
```

**calib_directbeam**  
Set up the grid and stepsize for the calibration of the direct beam in diffraction mode, for example:
```
  BeamShift: {gridsize: 5, stepsize: 300}
  DiffShift: {gridsize: 5, stepsize: 300}
```

## microscope.yaml

This file holds all the specifications of the microscope as necessary. It is important to set up the camera lengths, magnifications, and magnification modes. This file is must be located the `microscope/camera` directory, and can have any name as defined in `global.yaml`.

**name**  
name of the microscope interface to use

**wavelength**  
The wavelength of the microscope in Ansgtroms. This is used to generate some of the output files after data collection, i.e. for 120kV: 0.033492, 200kV: 0.025079, or 300 kV: 0.019687. A useful website to calculate the de Broglie wavelength is [here](https://www.ou.edu/research/electron/bmz5364/calc-kv.html).

**cameras**  
The cameras that area accessible on this microscope (obsolete)

**cameralengths**  
List here the available camera lengts available on the microscope in ascending order
```
[150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200,
1500, 2000, 2500, 3000, 3500, 4000, 4500]
```
  
**magnifications**  
List here the available magnifications available on the microscope in ascending order
```
[50, 60, 80, 100, 150, 200, 250, 300, 400, 500, 600,
800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000,
15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000,
200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000,
2000000]
```

**magnification_modes**  
Magnification modes tells instamatic when to switch between mag1 and lowmag modes, i.e. where lowmag starts and where mag1 starts.
```
{
  lowmag: 50, 
  mag1: 2500
}
```

**rotation_speeds**  
Here the rotation speeds can be calibrated. This is only used to correct the rotation speeds collected during cRED if necessary. Only used in one place, and probably redundant at this stage.

```
{
  fine: [ 0.114, 0.45, 1.126 ], 
  coarse: [ 0.45, 1.8, 4.5 ]
}
```