import matplotlib
import matplotlib.pyplot as plt
from instamatic.formats import *
import os, sys, glob
import numpy as np

from scipy import ndimage

import argparse
import tqdm

__version__ = "2017-03-12"

CMAP = None # "viridis", "gray"

ANGLE = -0.88 + np.pi/2
R = np.array([
            [ np.cos(ANGLE), -np.sin(ANGLE)],
            [ np.sin(ANGLE),  np.cos(ANGLE)]])

def get_stage_coords(fns, return_ims=False):
    coords = []
    has_crystals = []
    t = tqdm.tqdm(fns, desc="Parsing files")

    imgs = []

    for fn in t:
        img, h = read_image(fn)
        dx, dy = h["exp_hole_offset"]
        cx, cy = h["exp_hole_center"]
        coords.append((cx + dx, cy + dy))

        has_crystals.append(len(h["exp_crystal_coords"]) > 0)
        if return_ims:
            img = ndimage.zoom(img, 0.0969)
            imgs.append(img)
    # convert to um

    return np.array(coords) / 1000, np.array(has_crystals), imgs


def lst2colormap(lst):
    """Turn list of values into matplotlib colormap
    http://stackoverflow.com/a/26552429"""
    n = matplotlib.colors.Normalize(vmin=min(lst), vmax=max(lst))
    m = matplotlib.cm.ScalarMappable(norm=n)
    colormap = m.to_rgba(lst)
    return colormap


def run(filepat="images/image_*.tiff", results=None, stitch=False):
     # use relpath to normalizes path
    fns = map(os.path.relpath, glob.glob(filepat))

    coord_color = "red"
    picked_color = "blue"

    if results:
        df, d = read_ycsv(results)
        df.index = df.index.map(os.path.relpath)
        if isinstance(d["cell"], (tuple, list)):
            pixelsize = d["experiment"]["pixelsize"]
            indexer = IndexerMulti.from_cells(d["cell"], pixelsize=pixelsize, **d["projections"])
        else:
            projector = Projector.from_parameters(thickness=d["projections"]["thickness"], **d["cell"])
            indexer = Indexer.from_projector(projector, pixelsize=d["experiment"]["pixelsize"])

    coords, has_crystals, imgs = get_stage_coords(fns, return_ims=stitch)

    if len(fns) == 0:
        sys.exit()

    fn = fns[0]
    img, h = read_image(fn)
    imdim_x, imdim_y = np.array(h["ImageDimensions"]) / 2

    fig = plt.figure()
    fig.canvas.set_window_title('instamatic.browser')
    
    ax1 = plt.subplot(131, title="Stage map", aspect="equal")
    # plt_coords, = ax1.plot(coords[:,0], coords[:,1], marker="+", picker=8, c=has_crystals)
    
    coords = np.dot(coords, R)

    if stitch:
        for mini_img, coord in zip(imgs, coords):
            sx, sy = coord
            ax1.imshow(mini_img, interpolation='bilinear', extent=[sx-imdim_x, sx+imdim_x, sy-imdim_y, sy+imdim_y], cmap=CMAP)
    
    ax1.scatter(coords[has_crystals==True, 0], coords[has_crystals==True, 1], marker="o", facecolor=coord_color)
    ax1.scatter(coords[:, 0], coords[:, 1], marker=".", color=coord_color, picker=8)
    highlight1, = ax1.plot([], [], marker="o", color=picked_color)

    ax1.set_xlabel("Stage X")
    ax1.set_ylabel("Stage Y")

    ax2 = plt.subplot(132, title=fn)
    im2 = ax2.imshow(img, cmap=CMAP)
    plt_crystals, = ax2.plot([], [], marker="o", color="red",  mew=2, picker=8, lw=0)
    highlight2,   = ax2.plot([], [], marker="o", color="blue", mew=2)

    ax3 = plt.subplot(133, title="Diffraction pattern")
    im3 = ax3.imshow(np.zeros_like(img), vmax=250, cmap=CMAP)
    
    class plt_diff:
        center, = ax3.plot([], [], "o", color="red", lw=0)
        data = None

    def onclick(event):
        click = event.mouseevent.button
        axes = event.artist.axes
        ind = event.ind[0]

        if axes == ax1:
            fn = fns[ind]
            ax2.texts = []

            img, h = read_image(fn)
            im2.set_data(img)
            ax2.set_title(fn)
            crystal_coords = np.array(h["exp_crystal_coords"])

            if results:
                root, ext = os.path.splitext(fn)
                crystal_fns = [fn.replace("images", "data").replace(ext, "_{:04d}{}".format(i, ext)) for i in range(len(crystal_coords))]
                df.ix[crystal_fns]

                for coord, crystal_fn in zip(crystal_coords, crystal_fns):
                    try:
                        phase, score = df.ix[crystal_fn, "phase"], df.ix[crystal_fn, "score"]
                        
                    except KeyError: # if crystal_fn not in df.index
                        pass
                    else:
                        if score > 10:
                            text = " {}\n {:.0f}".format(phase, score)
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

            if len(crystal_coords) > 0:
                # to preload next diffraction pattern
                axes = ax2
                ind = 0

        if axes == ax2:
            fn = ax2.get_title()
            root, ext = os.path.splitext(fn)
            fn_diff = fn.replace("images", "data").replace(ext, "_{:04d}{}".format(ind, ext))

            img, h = read_image(fn_diff)
            im3.set_data(img)
            ax3.set_title(fn_diff)

            highlight2.set_xdata(plt_crystals.get_xdata()[ind])
            highlight2.set_ydata(plt_crystals.get_ydata()[ind])

            if results:
                if plt_diff.data:
                    plt_diff.data.remove()
                    plt_diff.data = None

                try:
                    r = df.ix[fn_diff]
                except KeyError:
                    plt_diff.center.set_xdata([])
                    plt_diff.center.set_ydata([])
                else:
                    print
                    print r
                    proj = indexer.get_projection(r)
                    pks = proj[:,3:5]

                    i, j, proj = get_indices(pks, r.scale, (r.center_x, r.center_y), img.shape, hkl=proj)
                    shape_vector = proj[:,5]

                    plt_diff.center.set_xdata(r.center_y)
                    plt_diff.center.set_ydata(r.center_x)

                    plt_diff.data = ax3.scatter(j, i, c=shape_vector, marker="+")

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
                        type=str, metavar="FILE", nargs="?",
                        help="File pattern to image files")

    parser.add_argument("-s", "--stitch",
                        action="store_true", dest="stitch",
                        help="Stitch images together.")
    
    parser.set_defaults(results=None,
                        stitch=False
                        )
    
    options = parser.parse_args()
    arg = options.args

    if not arg:
        if os.path.exists("images"):
            arg = "images/*.h5"
        else:
            parser.print_help()
            sys.exit()

    run(filepat=arg, results=options.results, stitch=options.stitch)


if __name__ == '__main__':
    main()