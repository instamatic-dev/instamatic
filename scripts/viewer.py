from __future__ import annotations

import sys

import matplotlib.pyplot as plt

from instamatic.formats import read_image


def main():
    import argparse

    description = """
Simple image viewer to open any image collected collected using instamatic. Supported formats include `TIFF`, `MRC`, [`HDF5`](http://www.h5py.org/), and [`SMV`](https://strucbio.biologie.uni-konstanz.de/ccp4wiki/index.php/SMV_file_format).
"""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'args',
        type=str,
        nargs=1,
        metavar='IMG',
        help='Image to display (TIFF, HDF5, MRC, SMV).',
    )

    options = parser.parse_args()
    args = options.args

    fn = args[0]

    img, h = read_image(fn)

    print(f"""Loading data: {fn}
        size: {img.nbytes / 1024} kB
       shape: {img.shape}
       range: {img.min()}-{img.max()}
       dtype: {img.dtype}
""")

    max_len = max(len(s) for s in h.keys())

    fmt = f'{{:{max_len}s}} = {{}}'
    for key in sorted(h.keys()):
        print(fmt.format(key, h[key]))

    plt.imshow(img, cmap='gray')
    plt.title(fn)
    plt.show()


if __name__ == '__main__':
    main()
