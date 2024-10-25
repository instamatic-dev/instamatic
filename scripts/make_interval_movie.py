from __future__ import annotations

import glob
import os
import subprocess as sp
import sys

import matplotlib.pyplot as plt
import numpy as np

from instamatic.formats import read_tiff


def tiff2png(interval=10, drc='movie'):
    fns1 = glob.glob(r'tiff\*.tif?')
    fns2 = glob.glob(r'tiff_image\*.tif?')

    if not os.path.exists(drc):
        os.mkdir(drc)

    j = 0

    for i, fn1 in enumerate(fns1):
        if i % (interval - 1) == 0:
            try:
                fn2 = fns2[j]
            except IndexError:
                break
            im2, h2 = read_tiff(fn2)

            im2 = im2[150:320, 150:320]

            j += 1

        im1, h1 = read_tiff(fn1)

        fig, (ax1, ax2) = plt.subplots(1, 2)

        ax1.imshow(im1, vmax=np.percentile(im1, 99.0), cmap='gray')
        ax2.imshow(im2, vmax=np.percentile(im1, 99.5), cmap='gray')

        ax1.axis('off')
        ax2.axis('off')

        plt.tight_layout()

        plt.savefig(f'{drc}/{i:05d}.png', bbox_inches='tight', pad_inches=0, dpi=200)
        plt.close()

        print(fn1, fn2)

    return drc


def main():
    drc = tiff2png()

    out = 'movie.mp4'

    cmd = f'ffmpeg -r 20 -i {drc}/%05d.png -s:v 516x516 -c:v libx264 -profile:v high -crf 20 -pix_fmt yuv420p -r 24 -y movie.mp4'.split()

    print()
    print(' '.join(cmd))
    print()

    sp.call(cmd)
    try:
        os.startfile(out)  # windows
    except AttributeError:
        sp.call(['open', out])  # macos
        # subprocess.call(['xdg-open', out]) # linux


if __name__ == '__main__':
    main()
