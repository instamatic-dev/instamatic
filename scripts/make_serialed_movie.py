from __future__ import annotations

import glob
import os
import subprocess as sp

import matplotlib.pyplot as plt
import numpy as np
from tqdm.auto import tqdm

from instamatic.formats import read_image

plt.rcParams['figure.figsize'] = 10, 10
plt.rcParams['image.cmap'] = 'gray'


def get_files(file_pat: str) -> list:
    """Grab files from globbing pattern or stream file."""
    from instamatic.formats import read_ycsv

    if os.path.exists(file_pat):
        root, ext = os.path.splitext(file_pat)
        if ext.lower() == '.ycsv':
            df, d = read_ycsv(file_pat)
            fns = df.index.tolist()
        else:
            f = open(file_pat)
            fns = [line.split('#')[0].strip() for line in f if not line.startswith('#')]
    else:
        fns = glob.glob(file_pat)

    if len(fns) == 0:
        raise OSError(f"No files matching '{file_pat}' were found.")

    return fns


fns = get_files(r'images\image*.h5')

fontdict = {'fontsize': 30}
vmax_im = 500
vmax_diff = 1500
vmin_diff = 0

save = True

number = 0

if not os.path.isdir('movie'):
    os.mkdir('movie')

for i, fn in enumerate(tqdm(fns)):
    dps = glob.glob(fn.replace('images', 'data').replace('.h5', '_*.h5'))

    im, h_im = read_image(fn)

    crystal_coords = np.array(h_im['exp_crystal_coords'])

    for j, dp in enumerate(dps):
        try:
            diff, h_diff = read_image(dp)
        except BaseException:
            print('fail')
            continue

        x, y = crystal_coords[j]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(21.5, 10), sharex=True, sharey=True)

        ax1.imshow(im, vmax=np.percentile(im, 99.5))
        ax1.axis('off')
        ax1.scatter(crystal_coords[:, 1], crystal_coords[:, 0], marker='.', color='red', s=100)
        ax1.scatter(y, x, marker='o', color='red', s=200)
        ax1.set_title(fn, fontdict)
        ax2.imshow(diff, vmin=vmin_diff, vmax=vmax_diff)

        ax2.axis('off')
        ax2.set_title(dp, fontdict)

        plt.tight_layout()

        # out = dp.replace("h5", "png").replace("data\\","movie\\")
        out = f'movie\\image_{number:04d}.png'
        number += 1

        if save:
            plt.savefig(out)
        else:
            plt.show()
        plt.close()

print('Running ffmpeg...')

cmd = 'ffmpeg -r 5 -i movie/image_%04d.png -s:v 1280x720 -c:v libx264 -profile:v high -crf 20 -pix_fmt yuv420p -r 24 -y movie/compilation.mp4'.split()
sp.call(cmd)

print('Done')
