# JEOL Goniotool

!!! warning

    GonioTool is a JEOL internal engineering tool. It can set all sorts of internal microscope settings if you are not careful with it.

One of the issues with the JEOL internal API is that it does not offer access to setting the rotation speed. `GonioTool.exe` (`C:\JEOL\TOOL\GonioTool.exe`) is an engineering tool that can update the rotation speed of the sample stage directly. It can be used to manually override the rotation speed of the goniometer.

Instamatic contains code that interfaces with `GonioTool.exe` to automate setting the rotation speed on a
JEOL microscope by adjusting the stepping frequency of the motor. The key value here is in `f1/rate` -> `TX`. The value can be set from 1 to 12, where 12 is maximum speed and 1 is the
slowest. The speed is linear up the maximum speed, where 1 is approximately
50 degrees/minute. We believe this to be contant, but your mileage may vary.

On the computer with `GonioTool.exe`, run `instamatic.goniotoolserver`. This will start a process that will start goniotool. It waits for you to enter the password (`gonio`). The process monitors the GonioTool window and simulates mouse clicks using an internal Windows API.

It tries to find the `f1/rate` controls tab and the entry box for `TX`. The program can read and set this value (nothing else).

Finally, `instamatic.goniotoolserver` sets up a server over the given port, which can be accessed from instamatic over the [network](./network.md).

On the main PC running instamatic, in `settings.yaml`:

```yaml
use_goniotool: True
goniotool_server_host: 'localhost'
goniotool_server_port: 8090
```

The controls are then available in the [`python API`][instamatic.controller] via [`ctrl.stage`][instamatic.microscope.components.Stage] in your own script/notebook:


```python
ctrl.stage.set_rotation_speed(1)  # super slow
ctrl.stage.set_rotation_speed(12) # super fast
```

Or to rotate to the given angle at the given speed (set `wait=False` for non-blocking call):

```python
ctrl.set_a_with_speed(a=20, speed=6, wait=True)
```

Code using this is available for the Gatan and TVIPS experiments:

- [`src/instamatic/experiments/cred_gatan/experiment.py`](https://github.com/instamatic-dev/instamatic/blob/main/src/instamatic/experiments/cred_gatan/experiment.py#L191)
- [`src/instamatic/experiments/cred_tvips/experiment.py`](https://github.com/instamatic-dev/instamatic/blob/main/src/instamatic/experiments/cred_tvips/experiment.py#L332 )

Code for the server:

- [`src/instamatic/server/goniotool_server.py`](https://github.com/instamatic-dev/instamatic/blob/main/src/instamatic/server/goniotool_server.py)

And for the client:

- [`src/instamatic/goniotool.py`](https://github.com/instamatic-dev/instamatic/blob/main/src/instamatic/goniotool.py)
