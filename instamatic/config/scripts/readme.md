This directory contains some example scripts for `instamatic`. They can be called via the interface , in the `Advanced` tab. Additionally, the `Search mode` and `Focus mode` buttons are linked to buttons in the `Tvips` tab, and `Close down` is linked to the `close_down.py` script.

These scripts can also be called via the command line:

`instamatic -s hello_world.py`

Or via the API:

`ctrl.run_script("hello_world.py")`

Instamatic will always look first check if the path exists, and if it cannot find it, it will run it from the scripts directory (in the config directory listed when `instamatic` is launched).