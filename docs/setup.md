# Setting up Instamatic

Download the latest zip package from the [releases page](https://github.com/instamatic-dev/instamatic/releases). This installation is fully portable, and can be copied directly to the microscope computer.

## JEOL

If you are using a JEOL TEM, make sure `instamatic` is installed on a computer with the TEMCOM interface. This is usually already installed on the camera PC. It can also be installed on the microscope control PC.

## FEI

For FEI microscopes, `instamatic` must be installed on the microscope control PC. Alternatively, it can be installed on both the microscope PC and the camera PC, running `instamatic.temserver` on the microscope PC, and establishing a connection over the local network. If any server PC does not support modern software, [instamatic-dev/instamatic-tecnai-server](https://github.com/instamatic-dev/instamatic-tecnai-server) is a drop-in replacement that requires Python 3.4 only.

See the config documentation for how to set this up.

## Development version

The latest development version of `instamatic` is available from [here](https://github.com/instamatic-dev/instamatic/archive/main.zip).

If you want to install `instamatic` into your own python installation, just extract and run:

```bash
pip install -e .
```

## Setting up the config files

Normally `instamatic` is not very fussy about starting up, but it may complain if you try to run some commands where it is missing some information from the config.

In order of priority:

### __1. Initialize the config directory__  
   If you are running instamatic for the first time, it will set up the config directory. Simply run `instamatic`. It should say that it sets up the config directory and tell the path where the data are.

### __2. Set up the microscope interface__  
   Go to the config directory from the first step.

   In `config/settings.yaml` define the camera interface you want to use. You can use the autoconfig tool or one of the example files and modify those. You can name these files anything you want, as long as the name under `microscope` matches the filename in `config/microscope`.

### __3. Set up the magnifications and camera lengths__  
   In the config file, i.e `config/microscope/jeol.yaml`, set the correct camera lengths (`ranges/diff`) and magnifications for your microscopes (`ranges/lowmag` and `ranges/mag1`). Also make sure you set the wavelength. Again, the autoconfig tool is your best friend, otherwise, the way to get those numbers is to simply write them down as you turn the magnification knob on the microcope.

### __4. Set up the camera interface__  
   Specify the file you want to use for the camera interface, i.e. `camera: timepix` points to `config/camera/timepix.yaml`. In this file, make sure that the interface is set to your camera type and update the numbers as specified in the config documentation. If you do not want to set up the camera interface at this moment, you can use `camera: simulate` to fake the camera connection.

### __5. Make the calibration table__  
   For each of the magnifications defined in `config/microscope/jeol.yaml`, specify the pixel sizes in the file defined by `calibration: jeol`, corresponding to the file `calibration/jeol.yaml`. For starters, you can simply set the calibration values to 1.0.

### __6. Test if it works__  
   Run `instamatic.controller` to start a IPython shell that initializes the connection. It should run with no crashes or warnings.

### __7. Update `settings.yaml`__  
   There are a few more choices to make in `instamatic/settings.yaml`. If you use a TVIPS camera, make sure you put `use_cam_server: true`.


It is recommended to run the temserver in a different terminal window by running `instamatic.temserver` if you specified this in `settings.yaml`. This helps maintain the microscope connection in case you want to restart instamatic. In some cases it is also worth to do this for the camera (or necessary in case of TVIPS) using `instamatic.camserver`.

## Automatic config generation

The easiest way to get started is to run:

```bash
instamatic.autoconfig.exe
```

To help generate some of the input files (in particular templates for the microscope/calibration files). This should give you a working setup for the microscope.

## Installing the Gatan CCD plugin

To work with the gatan camera, instamatic needs a plugin for GMS.
For this, instamatic depends on the RED CCD Plugin. You can download it [here](https://zenodo.org/record/2545322).

The plugin can be found in the package `REDc.rar`, in `.\CCD_plugins\Gatan\Normal Gatan cameras\REDCCDPlugin`.

Place `REDCCDPlugin.dll` in your Gatan plugin directory, which can usually be found here: `C:\Program files\Gatan\DigitalMicrgraph\Plugins`. For more information, have a look at the RED installation instructions manual.
