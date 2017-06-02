import os, sys

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import *
from instamatic.formats import *

import argparse, glob

from scipy import ndimage
from skimage import feature, morphology, measure

import numpy as np


__version__ = "2017-06-02"

# TODO
# Store regionprops:
#   x, y, xw, yw, pixels, intensity, orientation, eccentricity
# Shapiro-Wilk to filter bad images
# define go-routine to write list of useful images
# store corrected images for indexing, along with useful data, HDF5?

def process(img, callback):
    nmin = callback.minsize
    nmax = 500

    sigmin = callback.sigmin
    sigmax = callback.sigmax

    bgval = callback.bgval
    bgfootprint = 19
    
    # img_corr = np.maximum(img - ndimage.median_filter(img, 19), 0)
    img_corr = img - ndimage.median_filter(img, bgfootprint)
    bg = ndimage.gaussian_filter(img_corr, sigmin) - ndimage.gaussian_filter(img_corr, sigmax)
    
    labels, numlabels = ndimage.label(bg > bgval)
    labels = morphology.remove_small_objects(labels, nmin)
    
    props = measure.regionprops(labels, img_corr)
    
    numpeaks = len(props)

    img_corr = np.where(labels > 0, img_corr, np.zeros_like(img_corr))

    x,y = zip(*[prop.weighted_centroid for prop in props])

    return {
    "img":img,
    "img_corr":img_corr,
    "labels": labels,
    "x":x,
    "y":y
    }


def run(filepat="data/image_*.tiff"):
    fns = glob.glob(filepat)
    img, h = read_tiff(fns[0])

    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.25)

    ax.set_title("hitfinder")

    im = ax.imshow(img, cmap="gray")

    coords, = ax.plot([], [], marker="o", color="red", mew=2, lw=0, mfc="none")

    class Index(object):
        ind = 0
        sigmin = 4
        sigmax = 5
        bgval = 1
        minsize = 50
        show_peaks = False
        display_type = "img" # img
        vmax = 500
    
        def next(self, event):
            self.ind += 1
            self.update_img()

        def prev(self, event):
            self.ind -= 1
            self.update_img()

        def update_img(self):
            fn = fns[self.ind]
            self.img, h = read_tiff(fn)
    
            im.set_data(self.img)
            ax.set_title(fn)

            fig.canvas.draw()

            self.update()

        def set_sigmin(self, val):
            self.sigmin = val
            self.update()

        def set_sigmax(self, val):
            self.sigmax = val
            self.update()

        def set_bgval(self, val):
            self.bgval = val
            self.update()

        def set_minsize(self, val):
            self.minsize = val
            self.update()

        def update(self):
            d = process(self.img, self)

            disp = d[self.display_type]

            im.set_data(disp)

            if self.show_peaks:
                print len(d["x"])
                coords.set_xdata(d["y"])
                coords.set_ydata(d["x"])

            fig.canvas.draw()

        def set_show_peaks(self, val):
            self.show_peaks = val == "show"
            if not self.show_peaks:
                coords.set_xdata([])
                coords.set_ydata([])
                fig.canvas.draw()
            else:
                self.update()

        def set_display(self, val):
            self.display_type = val
            self.update()

        def set_vmax(self, val):
            self.vmax = val
            im.set_clim(vmax=val)
            fig.canvas.draw()

        def go(self):
            sys.exit()


    callback = Index()
    callback.img = img
    callback.update()

    axsigmin    = fig.add_axes([0.25, 0.15, 0.25, 0.03])
    axsigmax    = fig.add_axes([0.65, 0.15, 0.25, 0.03])
    axbgval     = fig.add_axes([0.25, 0.10, 0.65, 0.03])
    axminsize   = fig.add_axes([0.25, 0.05, 0.65, 0.03])

    slider_sig1 = Slider(axsigmin, 'Sigmin',    1, 20,    valinit=callback.sigmin, valfmt='%0.0f')
    slider_sig1.on_changed(callback.set_sigmin)

    slider_sig2 = Slider(axsigmax, 'Sigmax',    1, 30,    valinit=callback.sigmax, valfmt='%0.0f')
    slider_sig2.on_changed(callback.set_sigmax)

    slider2 = Slider(axbgval, 'BG',       1, 25,    valinit=callback.bgval, valfmt='%0.0f')
    slider2.on_changed(callback.set_bgval)

    slider3 = Slider(axminsize, 'Nmin',     1, 200,   valinit=callback.minsize, valfmt='%0.0f')
    slider3.on_changed(callback.set_minsize)

    axprev = fig.add_axes([0.025, 0.15, 0.1, 0.03])
    axnext = fig.add_axes([0.025, 0.10, 0.1, 0.03])
    axgo   = fig.add_axes([0.025, 0.05, 0.1, 0.03])
    bnext = Button(axnext, 'Next')
    bnext.on_clicked(callback.next)
    bprev = Button(axprev, 'Previous')
    bprev.on_clicked(callback.prev)
    bgo = Button(axgo, 'Go')
    bgo.on_clicked(callback.go)

    display_type_ax = fig.add_axes([0.025, 0.5, 0.15, 0.15])
    display_type = RadioButtons(display_type_ax, ('img', 'labels', 'img_corr'), active=0)
    display_type.on_clicked(callback.set_display)

    show_peaks_ax = fig.add_axes([0.025, 0.7, 0.15, 0.15])
    show_peaks = RadioButtons(show_peaks_ax, ('show', 'hide'), active=0)
    show_peaks.on_clicked(callback.set_show_peaks)

    axvmax = fig.add_axes([0.025, 0.4, 0.15, 0.05])
    slider_axvmax = Slider(axvmax, 'Vmax',    1, 500, valinit=callback.vmax, valfmt='%0.0f')
    slider_axvmax.on_changed(callback.set_vmax)

    plt.show()





def main():
    usage = """instamatic.hitfinder data/*.tiff"""

    description = """
Program for identifying useful serial electron diffraction images.

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

    parser.set_defaults()
    
    options = parser.parse_args()
    arg = options.args

    arg = "E:\instamatic\work_2017-05-23\experiment6\data\*.tiff"

    if not arg:
        if os.path.exists("images"):
            arg = "data/*.tiff"
        else:
            parser.print_help()
            sys.exit()

    run(filepat=arg)



if __name__ == '__main__':
    main()