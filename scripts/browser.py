import matplotlib.pyplot as plt
from instamatic.formats import *
import os, sys, glob
import numpy as np

from IPython import embed
from instamatic.processing.indexer import Indexer, IndexerMulti, Projector, read_ycsv, get_indices

import argparse
import tqdm

__version__ = "2017-03-12"


def get_stage_coords(fns):
    coords = []
    has_crystals = []
    t = tqdm.tqdm(fns, desc="Parsing files")
    for fn in t:
        img, h = read_tiff(fn)
        dx, dy = h["exp_hole_offset"]
        cx, cy = h["exp_hole_center"]
        coords.append((cx + dx, cy + dy))

        has_crystals.append(len(h["exp_crystal_coords"]) > 0)
    # convert to um
    return np.array(coords) / 1000, np.array(has_crystals)


def run(filepat="images/image_*.tiff", results=None):
     # use relpath to normalizes path
    fns = map(os.path.relpath, glob.glob(filepat))

    if results:
        df, d = read_ycsv(results)
        df.index = df.index.map(os.path.relpath)
        if isinstance(d["cell"], (tuple, list)):
            pixelsize = d["experiment"]["pixelsize"]
            indexer = IndexerMulti.from_cells(d["cell"], pixelsize=pixelsize, **d["projections"])
        else:
            projector = Projector.from_parameters(thickness=d["projections"]["thickness"], **d["cell"])
            indexer = Indexer.from_projector(projector, pixelsize=d["experiment"]["pixelsize"])

    coords, has_crystals = get_stage_coords(fns)

    fn = fns[0]
    img, h = read_tiff(fn)

    fig = plt.figure()
    
    ax1 = plt.subplot(131, title="Stage map", aspect="equal")
    # plt_coords, = ax1.plot(coords[:,0], coords[:,1], marker="+", picker=8, c=has_crystals)
    
    ax1.scatter(coords[has_crystals==True, 0], coords[has_crystals==True, 1], marker="o", edgecolor="red", facecolor="red")
    ax1.scatter(coords[:, 0], coords[:, 1], marker=".", color="red", picker=8)
    highlight1, = ax1.plot([], [], marker="o", color="blue")

    ax1.set_xlabel("Stage X")
    ax1.set_ylabel("Stage Y")

    ax2 = plt.subplot(132, title=fn)
    im2 = ax2.imshow(img)
    plt_crystals, = ax2.plot([], [], marker="+", color="red",  mew=2, picker=8, lw=0)
    highlight2,   = ax2.plot([], [], marker="+", color="blue", mew=3)

    ax3 = plt.subplot(133, title="Diffraction pattern")
    im3 = ax3.imshow(np.zeros_like(img), vmax=250)
    plt_diff, = ax3.plot([], [], "r+", picker=8, lw=0)
    plt_diff_center, = ax3.plot([], [], "o", lw=0)

    def onclick(event):
        click = event.mouseevent.button
        axes = event.artist.axes
        ind = event.ind[0]

        if axes == ax1:
            fn = fns[ind]
            ax2.texts = []

            img, h = read_tiff(fn)
            im2.set_data(img)
            ax2.set_title(fn)
            crystal_coords = np.array(h["exp_crystal_coords"])

            if results:
                crystal_fns = [fn.replace("images", "data").replace(".tiff", "_{:04d}.tiff".format(i)) for i in range(len(crystal_coords))]
                df.ix[crystal_fns]

                for coord, crystal_fn in zip(crystal_coords, crystal_fns):
                    try:
                        text = " {}\n {:.0f}".format(df.ix[crystal_fn, "phase"], df.ix[crystal_fn, "score"])
                    except KeyError: # if crystal_fn not in df.index
                        pass
                    else:
                        ax2.text(coord[1], coord[0], text)

            if len(crystal_coords) > 0:
                plt_crystals.set_xdata(crystal_coords[:,1])
                plt_crystals.set_ydata(crystal_coords[:,0])
            else:
                plt_crystals.set_xdata([])
                plt_crystals.set_ydata([])

            highlight1.set_xdata(coords[ind, 0])
            highlight1.set_ydata(coords[ind, 1])

            highlight2.set_xdata([])
            highlight2.set_ydata([])

            # to preload next diffraction pattern
            axes = ax2
            ind = 0

        if axes == ax2:
            fn_diff = ax2.get_title().replace("images", "data").replace(".tiff", "_{:04d}.tiff".format(ind))

            img, h = read_tiff(fn_diff)
            im3.set_data(img)
            ax3.set_title(fn_diff)

            highlight2.set_xdata(plt_crystals.get_xdata()[ind])
            highlight2.set_ydata(plt_crystals.get_ydata()[ind])
            
            if results:
                try:
                    r = df.ix[fn_diff]
                except KeyError:
                    plt_diff_center.set_xdata([])
                    plt_diff_center.set_ydata([])

                    plt_diff.set_xdata([])
                    plt_diff.set_ydata([])
                else:
                    print
                    print r
                    proj = indexer.get_projection(r)
                    pks = proj[:,3:5]
                    i, j, hkl = get_indices(pks, r.scale, (r.center_x, r.center_y), img.shape, hkl=proj[:,0:3])
    
                    plt_diff_center.set_xdata(r.center_y)
                    plt_diff_center.set_ydata(r.center_x)
    
                    plt_diff.set_xdata(j)
                    plt_diff.set_ydata(i)

        if axes == ax3:
            pass
        
        fig.canvas.draw()

    fig.canvas.mpl_connect("pick_event", onclick)

    plt.show()


def main():
    usage = """instamatic.browser images/*.tiff -r results.csv"""

    description = """
Program for indexing electron diffraction images.

""" 
    
    epilog = 'Updated: {}'.format(__version__)
    
    parser = argparse.ArgumentParser(#usage=usage,
                                    description=description,
                                    epilog=epilog, 
                                    formatter_class=argparse.RawDescriptionHelpFormatter,
                                    version=__version__)
    
    parser.add_argument("args", 
                        type=str, metavar="FILE",
                        help="File pattern to image files")

    parser.add_argument("-r", "--results", metavar='RESULTS.csv',
                        action="store", type=str, dest="results",
                        help="Path to .csv with results from indexing")

    
    parser.set_defaults(results=None,
                        )
    
    options = parser.parse_args()
    arg = options.args

    if not arg:
        parser.print_help()
        sys.exit()

    run(filepat=arg, results=options.results)


if __name__ == '__main__':
    main()