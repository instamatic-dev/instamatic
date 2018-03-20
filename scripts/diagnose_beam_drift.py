from instamatic.formats import adscimage
from scipy import ndimage, signal
from scipy.interpolate import interp1d
import sys, glob
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from instamatic.tools import find_beam_center, find_subranges


def print_subranges(data, n=100, step=50):
    i = 0
    while True:
        j = min(i+n, len(xy))

        r = data[i:j]
        
        vect = np.nanmax(np.abs(r-np.nanmin(r, axis=0)), axis=0)
        pos = np.nanmean(r, axis=0).tolist()
        std = np.nanstd(r, axis=0).tolist()
    
        print(f"{i:4d} - {j:4d}    {pos[0]:8.2f}  {pos[1]:8.2f}   {std[0]:6.2f}  {std[1]:6.2f}   {vect[0]:6.2f}  {vect[1]:6.2f}")
    
        if i + n >= len(data):
            break
        else:
            i += step


def get_drifts_per_scan_range(xy)    :
    i = np.nansum(xy, axis=1) == 0

    rng = np.arange(len(i))[i != True]

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
    
        normalized_xy.append(sub_xy-o)
        normalized_xy.append([np.NaN, np.NaN])
    
    normalized_xy = np.vstack(normalized_xy)
    drifts = np.array(drifts)

    # plt.plot(normalized_xy[:,0], label="X")
    # plt.plot(normalized_xy[:,1], label="Y")
    # plt.legend()
    # plt.show()

    return drifts


if __name__ == '__main__':
    
    filepat = sys.argv[1]
    
    if Path(filepat).suffix == ".npy":
        xy = np.load(filepat)
    elif Path(filepat).suffix == ".txt":
        xy = np.loadtxt(filepat)
    else:
        fns = glob.glob(filepat)
        print(len(fns))
        
        imgs = (adscimage.read_adsc(fn)[0] for fn in fns)
        centers = (find_beam_center(img, 10, m=50, kind=3) for img in imgs)
        xy = np.array(list(centers))
        
        np.savetxt(Path(fns[0]).parents[0] / "beam_centers.txt", xy, fmt="%10.4f")

    i = np.sum(xy, axis=1) == 0
    xy[i] = np.NaN
    
    print()
    print("                   mean            std dev             diff        ")
    print("      Range           X         Y        X       Y        X       Y")
    print_subranges(xy, n=len(xy))
    print("")
    print_subranges(xy, n=50, step=50)

    drifts = get_drifts_per_scan_range(xy)
    if len(drifts) > 1:
        print()
        print(f"Mean scan range beam drift: {drifts.mean():.4f} px")
        print(f"(std: {drifts.std():.4f} | min: {drifts.min():.4f} | max: {drifts.max():.4f})")

    median_x, median_y = np.nanmedian(xy, axis=0)
    start = 0
    end = len(xy)

    plt.plot([start, end], [median_x, median_x], c="C0", ls=":", label="Median(X)")
    plt.plot([start, end], [median_y, median_y], c="C1", ls=":", label="Median(Y)")

    plt.title("Frame number vs. Position of direct beam")
    plt.xlabel("Frame number")
    plt.ylabel("Pixel number")
    plt.plot(xy[:,0], c="C0", label="X")
    plt.plot(xy[:,1], c="C1", label="Y")
    plt.legend()
    plt.show()
