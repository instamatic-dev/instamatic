from __future__ import annotations

import glob
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from tqdm.auto import tqdm

from instamatic.formats import adscimage
from instamatic.tools import find_beam_center, find_subranges


def insert_nan(arr, interval=10):
    repeat = interval - 1
    new = []
    for i, row in enumerate(arr):
        if not (i) % repeat:
            new.append(np.array([np.nan, np.nan]))
        new.append(row)
    return np.array(new)


def print_subranges(data, n=100, step=50):
    i = 0
    while True:
        j = min(i + n, len(xy))

        r = data[i:j]

        vect = np.nanmax(np.abs(r - np.nanmin(r, axis=0)), axis=0)
        pos = np.nanmean(r, axis=0).tolist()
        std = np.nanstd(r, axis=0).tolist()

        print(
            f'{i:4d} - {j:4d}    {pos[0]:8.2f}  {pos[1]:8.2f}   {std[0]:6.2f}  {std[1]:6.2f}   {vect[0]:6.2f}  {vect[1]:6.2f}'
        )

        if i + n >= len(data):
            break
        else:
            i += step


def get_drifts_per_scan_range(xy):
    i = np.nansum(xy, axis=1) == 0

    rng = np.arange(len(i))[i != True]  # noqa

    subranges = find_subranges(rng)
    normalized_xy = []

    drifts = []

    for sbr in subranges:
        r = np.arange(*sbr)
        sub_xy = xy[r]

        if len(sub_xy) == 0:
            continue

        o = sub_xy[0]

        drift = np.linalg.norm(sub_xy - o, axis=1)
        distance = drift.max() - drift.min()
        drifts.append(distance)

        normalized_xy.append(sub_xy - o)
        normalized_xy.append([np.nan, np.nan])

    normalized_xy = np.vstack(normalized_xy)
    drifts = np.array(drifts)

    # plt.plot(normalized_xy[:,0], label="X")
    # plt.plot(normalized_xy[:,1], label="Y")
    # plt.legend()
    # plt.show()

    return drifts


if __name__ == '__main__':
    filepat = sys.argv[1]

    try:
        interval = int(sys.argv[2])
    except IndexError:
        interval = None

    if Path(filepat).suffix == '.npy':
        xy = np.load(filepat)
    elif Path(filepat).suffix == '.txt':
        xy = np.loadtxt(filepat)
    elif Path(filepat).suffix == '.sc':
        with open(filepat) as f:
            first = np.array([float(val) for val in f.readline().split()])
            xy = np.loadtxt(f, usecols=(1, 2))
        xy = xy + first

    else:
        fns = glob.glob(filepat)
        print(len(fns))

        imgs = (adscimage.read_adsc(fn)[0] for fn in tqdm(fns))
        centers = (find_beam_center(img, 10, m=50, kind=3) for img in imgs)
        xy = np.array(list(centers))

        np.savetxt(Path(fns[0]).parents[0] / 'beam_centers.txt', xy, fmt='%10.4f')

    if interval:
        xy = insert_nan(xy, interval=10)

    i = np.sum(xy, axis=1) == 0
    xy[i] = np.nan

    print()
    print('                   mean            std dev             diff        ')
    print('      Range           X         Y        X       Y        X       Y')
    print_subranges(xy, n=len(xy))
    print('')
    print_subranges(xy, n=50, step=50)

    drifts = get_drifts_per_scan_range(xy)
    if len(drifts) > 1:
        print()
        print(f'Mean scan range beam drift: {drifts.mean():.4f} px')
        print(f'(std: {drifts.std():.4f} | min: {drifts.min():.4f} | max: {drifts.max():.4f})')

    median_x, median_y = np.nanmedian(xy, axis=0)
    std_x, std_y = np.nanstd(xy, axis=0)
    start = 0
    end = len(xy)

    f, (ax1, ax2) = plt.subplots(2, sharex=True, sharey=False)

    ax1.set_title('Frame number vs. Position of direct beam')

    ax1.plot(
        [start, end],
        [median_x, median_x],
        c='C0',
        ls=':',
        label=f'Median(X)={median_x:.2f}, Std(X)={std_x:.2f}',
    )
    ax2.plot(
        [start, end],
        [median_y, median_y],
        c='C1',
        ls=':',
        label=f'Median(Y)={median_y:.2f}, Std(X)={std_y:.2f}',
    )

    # plt.title("Frame number vs. Position of direct beam")
    ax2.set_xlabel('Frame number')

    ax1.set_ylabel('Pixel number')
    ax2.set_ylabel('Pixel number')

    ax1.plot(xy[:, 0], c='C0')
    ax2.plot(xy[:, 1], c='C1')

    m_x = median_x
    m_y = median_y
    d_x = 0.8
    d_y = 0.8
    ax1.set_ylim(m_x - d_x, m_x + d_x)
    ax2.set_ylim(m_y - d_y, m_y + d_y)

    ax1.legend()
    ax2.legend()
    plt.show()
