# TEMController

The TEMController is at the heart of `instamatic`. Every routine depends on access to the `ctrl` object to interface with the microscope *and* the cameras. The TEMController provides a common object-oriented interface to the microscopes and the camera. One of the design philosophies of `instamatic` is that it should be fun to open a terminal and just play around with the microscope and test new ideas. The API was set up to be easy to work with when imported into an interactive IPython session.

## Getting started

In IPython:

```python
from instamatic import TEMController
ctrl = TEMController.initialize()
```
 
If no names for the camera/microscope are given, it reads the defaults from the config directory listed when TEMController is imported (`config/global.yaml`). The config directory is generated on the first run of `instamatic`. By default these are set to load simulation of the camera/microscope. The simulation is is a good test to see if it works at all (a shortcut to this is to type `instamatic.controller.exe` in the terminal).

The config files work as follows: The global configurations are defined in `config/global.yaml`. The values `cam_name` and `tem_name` correspond to the values given in `global.yaml`. The values given for calibration/camera/microscope in turn point to the files with the same name in the corresponding directories. For example, `camera: foo` corresponds to the file `config/camera/foo.yaml`, where you can customize the settings.

You can override the defaults here, so on the microscope computer you could try:

```python
ctrl = TEMController.initialize(tem_name='jeol', cam_name='timepix', stream=True)
```
 
`stream` indicates that the camera can be streamed (like the timepix camera). Other cameras, like the gatan (orius/ultrascan) cameras communicate through DigitalMicrograph, and can therefore not be streamed. Instead the live stream can be shown in DM, and therefore needs DM to be open.
 
Otherwise, to skip camera initialization:

```python
ctrl = TEMController.initialize(tem_name='jeol', cam_name=None)
```

Once a`ctrl` (control) object has been intialized, it becomes possible to play around with the lenses and stage interactively. Type `ctrl.` and hit `tab` to see the autocomplete options. Or write use `?` to request the doc string for a function (e.g. `TEMController.initialize?`).
 
Based on this you can write your own python scripts to control the microscope and/or camera. See in `instamatic/instamatic/experiments/cred/experiment.py` for an idea how this is used. All the microscope control interface can be found in `instamatic/TEMController/`

The `ctrl` object allows full control over the electron microscope. For example, to read out the position of the sample stage:
```python
xy = ctrl.stageposition.xy
print(xy)
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

All deflectors have two values (x and y), that can be accessed through the `.x` and `.y` properties.

All deflectors have the same API and behave in the same way, i.e.:
```python
ctrl.beamshift.x = 1234
ctrl.beamshift.y = 4321
ctrl.beamshift.xy = 1234, 4321

x = ctrl.beamshift.x
y = ctrl.beamshift.y
x, y = ctrl.beamshift.xy

ctrl.beamshift.get(x=1234, y=4321)
x, y = ctrl.beamshift.get()
```
Using the `.get` method returns a `namedtuple`, so that the `x` and `y` values can be accessed without unpacking:
```python
bs = ctrl.beamshift.get()
print(f"Beam X: {bs.x} | Beam Y: {bs.y}")
```
The values of the lenses can be set to the neutral values:
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
or rotation of the sample stage (in degrees), where `a` is the primary rotation axis, and `b` the secondary rotation axis (if available):
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
Using the `.get` method returns a `namedtuple`, so that individual values can be easily accessed without unpacking:
```python
stage = ctrl.stageposition.get()
print(f"The stage position coordinates are ({stage.x}, {stage.y})")
print(f"The height is {stage.z}")
print(f"The tilt angle is {stage.a}")
```
The stage position can be neutralized (all values reset to 0) using:
```python
ctrl.stageposition.neutral()
```

### Camera

Basic camera access is available on `TEMController`. It attempts to expose the lowest common denominator between the camera interfaces, which can vary significantly. For full access to the camera capabilities, use the camera objects directly.

To get the image from the camera, and a header containing the readout of the microscope parameters. The default binsize and exposure time as defined in the config can also be overriden:
```python
t = 0.5  # exposure time in seconds
b = 2 
comment = "This comment will be added to the header"
img, h = ctrl.getImage(exposure=t, binsize=b, comment=comment)
```
By default, the full header is included, but this can be suppressed with the `full_header` variable (saving some time).:
```python
img, h = ctrl.getImage(full_header=False)
```
To directly save the file, use the `out` command:
```python
img, h = ctrl.getImage(out="image.tiff")
```
To just get the image data, use:
```python
img = ctrl.getRawImage()
```
This is much faster than `ctrl.getImage`, because the microscope is not read out.

In case a streamable camera is used, `ctrl.show_stream()` will show a GUI window with the stream.

### Other functions

To blank the beam:
```python
ctrl.beamblank_on()
```
To unblank the beam:
```python
ctrl.beamblank_off()
```
To get the state of the beam blanker:
```python
ctrl.beamblank
```
The fluorescence screen can be controlled via:
```python
ctrl.screen_up()
ctrl.screen_down()
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

### Direct access

Direct access to the camera and tem interfaces is available through the `ctrl.tem` and `ctrl.cam` properties.

### Example experiment

An example rotation experiment could look something like this:

```python
from instamatic.formats import write_tiff
from instamatic import TEMController

ctrl = TEMController.initialize()

exposure_time = 1.0
angles = range(-40, 40, 1)
for i, angle in enumerate(angles):
    print(f"Angle = {angle}")
    ctrl.stageposition.a = angle
    img, h = ctrl.getImage(exposure_time)
    fn = "image_{:04d}.tiff".format(i)
    write_tiff(fn, img, header=h)
```