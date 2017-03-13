import matplotlib.pyplot as plt
from instamatic.formats import *
import os, sys, glob
import numpy as np

from IPython import embed


def get_stage_coords(fns):
    coords = []
    for fn in fns:
        img, h = read_tiff(fn)
        dx, dy = h["exp_hole_offset"]
        cx, cy = h["exp_hole_center"]
        coords.append((cx + dx, cy + dy))
    return np.array(coords)

def main():
    fns = glob.glob("images/image_*.tiff")

    coords = get_stage_coords(fns) / 1000 # convert to um

    fn = fns[0]
    img, h = read_tiff(fn)

    fig = plt.figure()
    
    ax1 = plt.subplot(131, title="Stage map", aspect="equal")
    plt_coords, = ax1.plot(coords[:,0], coords[:,1], "r+", picker=8)

    ax1.set_xlabel("Stage X")
    ax1.set_ylabel("Stage Y")

    ax2 = plt.subplot(132, title=fn)
    im2 = ax2.imshow(img)
    plt_crystals, = ax2.plot([], [], "r+", picker=8, lw=0)

    ax3 = plt.subplot(133, title="Diffraction pattern")
    im3 = ax3.imshow(np.zeros_like(img), vmax=250)
    plt_diff, = ax3.plot([], [], "r+", picker=8, lw=0)

    def onclick(event):
        click = event.mouseevent.button
        axes = event.artist.axes
        ind = event.ind[0]

        plt_coords
        plt_crystals
        plt_diff

        if axes == ax1:
            fn = fns[ind]

            img, h = read_tiff(fn)
            im2.set_data(img)
            ax2.set_title(fn)
            crystal_coords = np.array(h["exp_crystal_coords"])
            
            if len(crystal_coords) > 0:
                plt_crystals.set_xdata(crystal_coords[:,1])
                plt_crystals.set_ydata(crystal_coords[:,0])
            else:
                plt_crystals.set_xdata([])
                plt_crystals.set_ydata([])
        
        elif axes == ax2:
            fn_diff = ax2.get_title().replace("images", "data").replace(".tiff", "_{:04d}.tiff".format(event.ind[0]))

            img, h = read_tiff(fn_diff)
            im3.set_data(img)
            ax3.set_title(fn_diff)

        elif axes == ax3:
            pass
        
        fig.canvas.draw()

    fig.canvas.mpl_connect("pick_event", onclick)

    plt.show()


if __name__ == '__main__':
    main()