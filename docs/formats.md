# Formats

This package includes some functions to read and write data.

To import:
```
from instamatic.formats import *
```

The following readers are available:

- `read_image(fname)`
- `read_tiff(fname)`
- `read_mrc(fname)`
- `read_hdf5(fname)`
- `read_adsc(fname)`
- `read_cbf(fname)`

These functions return a tuple containing the data and header as a dictionary.

The following writers are available:

- `write_image(fname, data, header=None)`  
  This function figures out the data type from the filename.

- `write_tiff(fname, data, header=None)`  
  Writes tiff files using the [tifffile](https://pypi.org/project/tifffile/) library, which has support for TVIPS headers. If a header is specified, it is stored in the `description` tag in yaml format.

- `write_mrc(fname, data, header=None)`  
  Uses the mrc implementation from the [arachnid](https://github.com/ezralanglois/arachnid) project.

- `write_hdf5(fname, data, header=None)`  
  HDF5 files are written using h5py.

- `write_adsc(fname, data, header=None)`  
  SMV files (adsc) are written using the implementation in [fabio](https://github.com/silx-kit/fabio).

- `write_cbf(fname, data, header=None)`  
  Not implemented yet.

Where fname should be a string or a `pathlib.Path` instance. Data is a numpy array, and the header is a python dictionary.

Example usage:

```python
from instamatic.formats import read_tiff, write_tiff
import numpy as np

fn = "important_data.tiff"
img = (np.random.random((512, 512)) * 1000).astype(np.uint16)

header = {}
header['xres'] = img.shape[0]
header['yres'] = img.shape[1]
header['comment'] = "This is a tiff file"

# save the data
write_tiff(fn, img, header=header)

# read the data
arr, h = read_tiff(fn)

# make sure they are equal
print(arr.shape)
print("allclose:", np.allclose(img, arr))
```