import os, sys

from instamatic.formats import *
from instamatic.tools import find_beam_center
from instamatic.processing.extensions import radial_profile

import argparse, glob

from scipy import ndimage
from skimage import feature, morphology, measure

import numpy as np
import wx

import datetime

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2Wx as NavigationToolbar

from IPython import embed

__version__ = "2017-06-02"

class Handler(object):
    """docstring for Handler"""
    def __init__(self, arg):
        super(Handler, self).__init__()
        self.arg = arg


class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title=title, size=(1000,820))
        
        self.sp = wx.SplitterWindow(self)

        # self.handler = Handler()
        
        self.right = MatplotPanel(self.sp)
        self.left = MatControls(self.sp, self.right)
        self.sp.SplitVertically(self.left, self.right, 300)

        self.status = self.CreateStatusBar() # A StatusBar in the bottom of the window

        # Setting up the menu.
        filemenu = wx.Menu()

        # wx.ID_ABOUT and wx.ID_EXIT are standard ids provided by wxWidgets.
        menuAbout = filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program")
        menuExit = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")

        # Creating the menubar.
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.

        # Set events.
        self.Bind(wx.EVT_MENU, self.OnAbout, menuAbout)
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)

        self.Show(True)

    def OnAbout(self,e):
        # A message dialog box with an OK button. wx.OK is a standard ID in wxWidgets.
        dlg = wx.MessageDialog( self, "Hitfinder", "About", wx.OK)
        dlg.ShowModal() # Show it
        dlg.Destroy() # finally destroy it when finished.

    def OnExit(self,e):
        self.Close(True)  # Close the frame.

    def set_filelist(self, filelist):
        self.right.filelist = filelist
        self.right.update_image()

class MatControls(wx.Panel):
    def __init__(self, parent, mpp):     
        wx.Panel.__init__(self, parent, -1, size=(50,50), style=wx.SUNKEN_BORDER)

        self.mpp = mpp

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        self.init_sliders(self.sizer)

    def init_sliders(self, add_to):

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        row3 = wx.BoxSizer(wx.HORIZONTAL)
        row4 = wx.BoxSizer(wx.HORIZONTAL)
        row5 = wx.BoxSizer(wx.HORIZONTAL)
        row6 = wx.BoxSizer(wx.HORIZONTAL)

        lsigmin = wx.StaticText(self, label='Sigma min')
        lsigmax = wx.StaticText(self, label='Sigma max')
        lthresh = wx.StaticText(self, label='Threshold')
        lnmin   = wx.StaticText(self, label='Nmin')
        lnmax   = wx.StaticText(self, label='Nmax')

        ssigmin = wx.Slider(self, wx.ID_ANY, value=self.mpp.sigmin, minValue=1, maxValue=20, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        ssigmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.sigmax, minValue=1, maxValue=20, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        sthresh = wx.Slider(self, wx.ID_ANY, value=self.mpp.threshold, minValue=1, maxValue=100, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        snmin = wx.Slider(self, wx.ID_ANY, value=self.mpp.nmin,  minValue=1, maxValue=200, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        snmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.nmax, minValue=10, maxValue=1000, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        lvmax = wx.StaticText(self, label='Vmax')
        svmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.vmax, minValue=0, maxValue=1000, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        row1.Add(lsigmin, 0, wx.ALL|wx.CENTER, 5)
        row1.Add(ssigmin, 1, wx.ALL|wx.EXPAND, 5)
        row2.Add(lsigmax, 0, wx.ALL|wx.CENTER, 5)
        row2.Add(ssigmax, 1, wx.ALL|wx.EXPAND, 5)
        row3.Add(lthresh, 0, wx.ALL|wx.CENTER, 5)
        row3.Add(sthresh, 1, wx.ALL|wx.EXPAND, 5)
        row4.Add(lnmin, 0, wx.ALL|wx.CENTER, 5)
        row4.Add(snmin, 1, wx.ALL|wx.EXPAND, 5)
        row5.Add(lnmax, 0, wx.ALL|wx.CENTER, 5)
        row5.Add(snmax, 1, wx.ALL|wx.EXPAND, 5)
        row6.Add(lvmax, 0, wx.ALL|wx.CENTER, 5)
        row6.Add(svmax, 1, wx.ALL|wx.EXPAND, 5)

        ssigmin.Bind(wx.EVT_SLIDER, self.on_sigmin)
        ssigmax.Bind(wx.EVT_SLIDER, self.on_sigmax) 
        sthresh.Bind(wx.EVT_SLIDER, self.on_thresh) 
        snmin.Bind(wx.EVT_SLIDER, self.on_nmin) 
        snmax.Bind(wx.EVT_SLIDER, self.on_nmax)
        svmax.Bind(wx.EVT_SLIDER, self.on_vmax)

        add_to.Add(row1, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row2, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row3, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row4, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row5, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(wx.StaticLine(self,), 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row6, 0, wx.ALL|wx.EXPAND, 5)

    def on_sigmin(self, event):
        self.mpp.sigmin = event.GetEventObject().GetValue()
        self.mpp.process_image()

    def on_sigmax(self, event):
        self.mpp.sigmax = event.GetEventObject().GetValue()
        self.mpp.process_image()

    def on_thresh(self, event):
        self.mpp.threshold = event.GetEventObject().GetValue()
        self.mpp.process_image()

    def on_nmin(self, event):
        self.mpp.nmin = event.GetEventObject().GetValue()
        self.mpp.process_image()

    def on_nmax(self, event):
        self.mpp.nmax = event.GetEventObject().GetValue()
        self.mpp.process_image()

    def on_vmax(self, event):
        self.mpp.vmax = event.GetEventObject().GetValue()
        self.mpp.im.set_clim(vmax=self.mpp.vmax)
        self.mpp.canvas.draw()


class MatplotPanel(wx.Panel):
    def __init__(self, parent):     
        wx.Panel.__init__(self, parent, -1, size=(50,50))

        self.parent = parent

        self.filelist = None
        self._index = 0

        self.sigmin = 4
        self.sigmax = 5
        self.threshold = 1
        self.nmin = 50
        self.nmax = 5000

        self.display_type = "img"
        self.show_peaks = True
        self.vmax = 500
        self.vmin = 0

        self.bg_footprint = 19
        self.beam_center_sigma = 10

        self.xy = []
        self.numpeaks = 0
        self.beam_center = []

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        self.fig = plt.figure()
        self.ax = self.fig.add_axes([0,0,1,1])
        self.ax.axis('off')

        self.canvas = FigureCanvas(self, -1, self.fig)
        self.toolbar = NavigationToolbar(self.canvas)

        self.button_next = wx.Button(self, -1, "Next")
        self.button_next.Bind(wx.EVT_BUTTON, self.next_image)

        self.button_previous = wx.Button(self, -1, "Previous")
        self.button_previous.Bind(wx.EVT_BUTTON, self.previous_image)

        self.button_go = wx.Button(self, -1, "Go")
        self.button_go.Bind(wx.EVT_BUTTON, self.go)

        self.nav_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.sizer.Add(self.toolbar, 0, wx.GROW)
        self.nav_sizer.Add(self.button_previous, 0)
        self.nav_sizer.Add(self.button_next, 0)
        self.nav_sizer.Add(self.button_go, 0)
        
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW | wx.EXPAND)
        self.sizer.Add(self.nav_sizer, 0, wx.GROW)

        self.im = self.ax.imshow(np.random.random((512,512)), cmap="gray", vmax=500)
        self.coords, = self.ax.plot([], [], marker="o", color="red", mew=1, lw=0, mfc="none")
        self.center, = self.ax.plot([], [], marker="o", color="red", lw=0)

    @property
    def index(self):
        return self._index % len(self.filelist)

    @index.setter
    def index(self, value):
        self._index = value

    def next_image(self, event):
        self.index += 1
        self.update_image()

    def previous_image(self, event):
        self.index -= 1
        self.update_image()

    def update_image(self):
        fn = self.filelist[self.index]

        self.img, h = read_tiff(fn)
        self.im.set_data(self.img)

        self.process_image()

        self.draw_image()

    def update_peaks(self):
        if self.show_peaks and self.numpeaks:
            # BUG in FigureCanvasWxAgg? 
            # Work-around to fix incorrect display of peak positions on canvas
            # Multiply by 0.99 seems to be OK
            self.coords.set_xdata(0.99 * self.xy[:,1])
            self.coords.set_ydata(0.99 * self.xy[:,0])
            self.center.set_xdata(0.99 * self.beam_center[1])
            self.center.set_ydata(0.99 * self.beam_center[0])
        else:
            self.coords.set_xdata([])
            self.coords.set_ydata([])

    def _process_image(self, img):
        img_corr = img - ndimage.median_filter(img, self.bg_footprint)
        bg = ndimage.gaussian_filter(img_corr, self.sigmin) - ndimage.gaussian_filter(img_corr, self.sigmax)
        
        labels, numlabels = ndimage.label(bg > self.threshold)
        labels = morphology.remove_small_objects(labels, self.nmin)
        
        props = measure.regionprops(labels, img_corr)
        
        self.numpeaks = len(props)
    
        img_corr = np.where(labels > 0, img_corr, np.zeros_like(img_corr))
        
        return img_corr, props

    def process_image(self):
        img_corr, props = self._process_image(self.img)
        self.beam_center = find_beam_center(self.img, sigma=self.beam_center_sigma)
        self.xy = np.array([prop.centroid for prop in props])
        self.img_corr = img_corr
        self.draw_image()

    def draw_image(self):
        self.update_peaks()
        self.Layout()
        self.canvas.draw()

    def go(self, event):
        total = len(self.filelist)

        dlg = wx.ProgressDialog("Processing images...", "",
            maximum=total, parent=self,
            style=wx.PD_CAN_ABORT|wx.PD_APP_MODAL|wx.PD_REMAINING_TIME|wx.PD_ESTIMATED_TIME)

        stream = []

        for i, fn in enumerate(self.filelist):
            keep_going, skip = dlg.Update(i, "{}/{}\n{}".format(i, total, fn))
            if not keep_going:
                dlg.Destroy()
                break

            img, h = read_tiff(fn)
            img_corr, props = self._process_image(img)

            root, ext = os.path.splitext(os.path.basename(fn))
            outdir = os.path.join(os.path.dirname(os.path.dirname(fn)), "processed")
            
            if not os.path.exists(outdir):
                os.mkdir(outdir)
            
            outfile = os.path.join(outdir, root + ".h5")

            if os.path.exists(outfile):
                os.unlink(outfile)

            f = h5py.File(outfile)
            rawdata = f.create_dataset("rawdata", data=img)

            for k,v in h.items():
                try:
                    rawdata.attrs[k] = v
                except TypeError:
                    pass

            data = f.create_dataset("data", data=img_corr)

            data.attrs["date"] = datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f")
            data.attrs["program"] = __file__
            data.attrs["bg_footprint"] = self.bg_footprint
            data.attrs["sigma_min"] = self.sigmin
            data.attrs["sigma_max"] = self.sigmax

            xy = np.array([prop.centroid for prop in props])
            xyw = np.array([prop.weighted_centroid for prop in props])
            pixels = np.array([prop.filled_area for prop in props])
            intensities = np.array([prop.intensity_image.sum() for prop in props])
            orientations = np.array([prop.orientation for prop in props])
            eccentricities = np.array([prop.eccentricity for prop in props])
            
            if len(xy) == 0:
                f.close()
                continue

            beam_center = find_beam_center(img, self.beam_center_sigma)
            xy_corr = xy - beam_center
            
            pixelsize = h["ImagePixelsize"]

            dspacings = np.linalg.norm(1/(pixelsize * xy_corr), axis=1)
            resolution = np.percentile(dspacings, 20) 

            f["peakinfo/xy"] = xy
            f["peakinfo/xy_weighted"] = xyw
            f["peakinfo/xy_corr"] = xy_corr
            f["peakinfo/npixels"] = pixels
            f["peakinfo/intensities"] = intensities
            f["peakinfo/orientations"] = orientations
            f["peakinfo/eccentricities"] = eccentricities
            f["peakinfo/dspacings"] = dspacings
            f["peakinfo/beam_center"] = beam_center

            f["peakinfo"].attrs["resolution"] = resolution
            f["peakinfo"].attrs["beam_center"] = beam_center 
            f["peakinfo"].attrs["pixelsize"] = pixelsize
            f["peakinfo"].attrs["numpeaks"] = self.numpeaks

            radialprofile = radial_profile(img_corr, beam_center[0], beam_center[1])
            f.create_dataset("radialprofile", data=radialprofile)
            f["radialprofile"].attrs["beam_center"] = beam_center
            f["radialprofile"].attrs["source_data"] = "/data"

            f.close()

            hit = (self.numpeaks > 10) and (resolution > 2.0)
            if hit:
                stream.append(outfile)

        dlg.Destroy()

        nhits = len(stream)
        with open("stream.txt", "w") as f:
            f.write(" # Hitrate {}/{} = {:.1%}\n".format(nhits, total, float(nhits)/total))
            for fn in stream:
                f.write(fn + "\n")


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
                        help="File pattern to image files (i.e. data/*.tiff)")

    parser.set_defaults()
    
    options = parser.parse_args()
    arg = options.args

    if not arg:
        if os.path.exists("images"):
            arg = "data/*.tiff"
        else:
            parser.print_help()
            sys.exit()

    filelist = glob.glob(arg)

    app = wx.App(redirect=False)
    frame = MainWindow(None, "hitfinder")
    frame.set_filelist(filelist)
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()