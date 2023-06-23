This directory contains some example scripts for `instamatic`. They can be called via the interface , in the `Advanced` tab. Additionally, the `Search mode` and `Focus mode` buttons are linked to buttons in the `TVIPS` tab, and `Close down` is linked to the `close_down.py` script.

These scripts can also be called via the command line:

```bash
instamatic -s hello_world.py
```

Or via the API:

```python
ctrl.run_script("hello_world.py")
```

Instamatic will always look first check if the path exists locally. If it cannot find it, it will run it from the scripts directory (`instamatic -l scripts`).
