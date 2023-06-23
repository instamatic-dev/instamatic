# Merlin

The [MerlinEM detector](https://quantumdetectors.com/products/merlinem/) by Quantum Detectors is a fast pixelated detector capable of collecting electron diffraction data with virtually no noise and a high dynamic range (log scale 10^6).

Instamatic communicates with the Merlin control software via TCP/IP connection. This means that there is a fast connection with little overhead when collecting data.

In continous read/write mode, instamatic can achieve gapless data acquisition `MerlinCamera.get_movie()`. When continuously collecting single images using `MerlinCamera.get_image()`, there is a ~3 ms overhead per frame.

## Setup

Enable `merlin` in `settings.yaml`:

```yaml
camera: merlin
```

You can set up the parameters for the Merlin camera through `camera/merlin.yaml` in your config directory.

For an example config file, see: [`camera/merlin.yaml`](https://github.com/instamatic-dev/instamatic/blob/main/src/instamatic/config/camera/merlin.yaml). [Click here](/config.md#camerayaml) to go to the page with all common camera configuration parameters.

In addition, the Merlin camera has the following parameters to configure:

**host**
: Set this to `localhost` or `127.0.0.1` if the Merlin control software runs on the same PC as instamatic. To make a remote connection over the network, pujt the IP of the PC where Merlin is running. For example:
```yaml
host: '10.0.0.123'
```

**commandport**
: This is the port that instamatic uses to communicate with Merlin. Defaults to `6341`.

**dataport**
: This is the port that Merlin sends data. Defaults to `6342`.

**detector_config**
: The parameters under `detector_config` are directly sent to the Merlin software when instamatic starts.
These can be used to put the Merlin in the desired state for data acquisition. Any command with a `SET` type can be adjusted. Check the Merlin EM documention for more information.

: The default sets continuous read-write mode and 12-bit mode to minimize the gap between frames. It also disables automatic file writing (`FILEENABLE`) and image processing by Merlin, and enables headless `RUNHEADLESS` mode for faster throughput. If you don't want this, you can delete these lines or modify them.

```yaml
detector_config:
  CONTINUOUSRW: 1
  COUNTERDEPTH: 12
  FILEENABLE: 0
  RUNHEADLESS: 1
```

: You could for example also set the thresholds and bias in the instamatic config by adding these lines:
```yaml
detector_config:
  THRESHOLD0: 120
  THRESHOLD1: 40
  HVBIAS: 511
```

## Notes on using instamatic with Merlin

- Make sure the Merlin software is running *before* starting instamatic
- When instamatic is running, it's advised not to change acquisition settings in the Merlin control software.
- Changing exposure on the fly (for example, in the gui) incurs a small overhead (~300 ms).
