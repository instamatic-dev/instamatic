import os, sys

from instamatic.formats import *
from instamatic.tools import find_beam_center
from instamatic.processing.extensions import radial_profile
from instamatic.processing.stretch_correction import affine_transform_ellipse_to_circle, apply_transform_to_image

import argparse, glob

from scipy import ndimage
from skimage import feature, morphology, measure, filters

import numpy as np
import wx
from wx.lib.masked import NumCtrl

import datetime

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2Wx as NavigationToolbar

from IPython import embed

__version__ = "2017-06-02"


MIN_NPEAKS = 50
MIN_RESOLUTION = 9999


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
        self.left.status = self.status
        self.right.status = self.status

        # Setting up the menu.
        filemenu = wx.Menu()

        menuOpen = filemenu.Append(wx.ID_OPEN, '&Open')
        filemenu.AppendSeparator()

        # wx.ID_ABOUT and wx.ID_EXIT are standard ids provided by wxWidgets.
        menuAbout = filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program")
        menuExit = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")

        # Creating the menubar.
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.

        # Set events.
        self.Bind(wx.EVT_MENU, self.OnOpen, menuOpen)
        self.Bind(wx.EVT_MENU, self.OnAbout, menuAbout)
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)

        self.Show(True)

    def OnAbout(self, event):
        # A message dialog box with an OK button. wx.OK is a standard ID in wxWidgets.
        dlg = wx.MessageDialog( self, "Hitfinder", "About", wx.OK)
        dlg.ShowModal() # Show it
        dlg.Destroy() # finally destroy it when finished.

    def OnExit(self, event):
        self.Close(True)  # Close the frame.

    def OnOpen(self, event):
        open_dialog = wx.FileDialog(self, "Open image", "", "", "HDF5 (*.h5, *.hdf5)|*.h5;*.hdf5|TIFF (*.tif, *.tiff)|*.tif;*.tiff", wx.FC_OPEN|wx.FD_MULTIPLE)
        if open_dialog.ShowModal() == wx.ID_OK:
            filelist = open_dialog.GetPaths()
        else:
            return
        self.set_filelist(filelist)

    def set_filelist(self, filelist):
        self.right.filelist = filelist
        self.right.load_image()


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
        row7 = wx.BoxSizer(wx.HORIZONTAL)
        row8 = wx.BoxSizer(wx.HORIZONTAL)
        row9 = wx.BoxSizer(wx.HORIZONTAL)
        row10 = wx.BoxSizer(wx.HORIZONTAL)
        
        row11 = wx.BoxSizer(wx.HORIZONTAL)
        row12 = wx.BoxSizer(wx.HORIZONTAL)

        lsigmin = wx.StaticText(self, label='Sigma min\t')
        lsigmax = wx.StaticText(self, label='Sigma max\t')
        lthresh = wx.StaticText(self, label='Threshold\t')
        lnmin   = wx.StaticText(self, label='Nmin     \t')
        lnmax   = wx.StaticText(self, label='Nmax     \t')

        ssigmin = wx.Slider(self, wx.ID_ANY, value=self.mpp.sigmin, minValue=1, maxValue=20, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        ssigmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.sigmax, minValue=1, maxValue=20, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        sthresh = wx.Slider(self, wx.ID_ANY, value=self.mpp.threshold, minValue=1, maxValue=100, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        snmin = wx.Slider(self, wx.ID_ANY, value=self.mpp.nmin,  minValue=1, maxValue=50, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)
        snmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.nmax, minValue=10, maxValue=1000, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        lvmax = wx.StaticText(self, label='Vmax     \t')
        svmax = wx.Slider(self, wx.ID_ANY, value=self.mpp.vmax, minValue=1, maxValue=500, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        lbackground_footprint   = wx.StaticText(self, label='Bkg. footprint')
        sbackground_footprint = wx.Slider(self, wx.ID_ANY, value=self.mpp.background_footprint, minValue=1, maxValue=50, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        lbeam_center_sigma   = wx.StaticText(self, label='Beam center sigma')
        sbeam_center_sigma = wx.Slider(self, wx.ID_ANY, value=self.mpp.beam_center_sigma, minValue=1, maxValue=50, style=wx.SL_HORIZONTAL | wx.SL_LABELS | wx.SL_VALUE_LABEL | wx.SL_AUTOTICKS)

        check_show_raw_data = wx.CheckBox(self, wx.ID_ANY, label="Show raw data")
        check_show_raw_data.SetValue(self.mpp.show_raw_data)
        check_show_peaks = wx.CheckBox(self, wx.ID_ANY, label="Show peaks")
        check_show_peaks.SetValue(self.mpp.show_peaks)
        check_remove_background = wx.CheckBox(self, wx.ID_ANY, label="Remove background")
        check_remove_background.SetValue(self.mpp.remove_background)

        l_stretch_amplitude   = wx.StaticText(self, -1, label='Stretch amplitude')
        l_stretch_azimuth     = wx.StaticText(self, -1, label='Stretch azimuth')
        self.mpp.e_stretch_amplitude = NumCtrl(self, -1, value=self.mpp.stretch_amplitude, fractionWidth=4, integerWidth=1)
        self.mpp.e_stretch_azimuth   = NumCtrl(self, -1, value=self.mpp.stretch_azimuth,   fractionWidth=4, integerWidth=3)

        row11.Add(l_stretch_amplitude, 0, wx.ALL|wx.CENTER, 5)
        row11.Add(self.mpp.e_stretch_amplitude, 1, wx.ALL|wx.EXPAND, 5)
        row12.Add(l_stretch_azimuth, 0, wx.ALL|wx.CENTER, 5)
        row12.Add(self.mpp.e_stretch_azimuth, 1, wx.ALL|wx.EXPAND, 5)

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
        row6.Add(lbeam_center_sigma, 0, wx.ALL|wx.EXPAND, 5)
        row6.Add(sbeam_center_sigma, 1, wx.ALL|wx.EXPAND, 5)

        row7.Add(lbackground_footprint, 0, wx.ALL|wx.EXPAND, 5)
        row7.Add(sbackground_footprint, 1, wx.ALL|wx.EXPAND, 5)
        row8.Add(check_remove_background, 0, wx.ALL|wx.EXPAND, 5)

        row9.Add(lvmax, 0, wx.ALL|wx.CENTER, 5)
        row9.Add(svmax, 1, wx.ALL|wx.EXPAND, 5)
        row10.Add(check_show_raw_data,0, wx.ALL|wx.EXPAND, 5)
        row10.Add(check_show_peaks, 0, wx.ALL|wx.EXPAND, 5)

        ssigmin.Bind(wx.EVT_SLIDER, self.on_sigmin)
        ssigmax.Bind(wx.EVT_SLIDER, self.on_sigmax) 
        sthresh.Bind(wx.EVT_SLIDER, self.on_threshold) 
        snmin.Bind(wx.EVT_SLIDER, self.on_nmin) 
        snmax.Bind(wx.EVT_SLIDER, self.on_nmax)
        svmax.Bind(wx.EVT_SLIDER, self.on_vmax)
        sbackground_footprint.Bind(wx.EVT_SLIDER, self.on_background_footprint)
        sbeam_center_sigma.Bind(wx.EVT_SLIDER, self.on_beam_center_sigma)
        
        check_show_raw_data.Bind(wx.EVT_CHECKBOX, self.on_display_raw_data)
        check_show_peaks.Bind(wx.EVT_CHECKBOX, self.on_show_peaks)
        check_remove_background.Bind(wx.EVT_CHECKBOX, self.on_remove_background) 

        # processing parameters
        add_to.Add(row1, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row2, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row3, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row4, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row5, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row6, 0, wx.ALL|wx.EXPAND, 5)
        
        #background
        add_to.Add(wx.StaticLine(self,), 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row7, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row8, 0, wx.ALL|wx.EXPAND, 5)

        # display
        add_to.Add(wx.StaticLine(self,), 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row9, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row10, 0, wx.ALL|wx.EXPAND, 5)

        # stretch corrections
        add_to.Add(wx.StaticLine(self,), 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row11, 0, wx.ALL|wx.EXPAND, 5)
        add_to.Add(row12, 0, wx.ALL|wx.EXPAND, 5)

    def on_sigmin(self, event):
        self.mpp.sigmin = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.update_image()

    def on_sigmax(self, event):
        self.mpp.sigmax = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.update_image()

    def on_threshold(self, event):
        self.mpp.threshold = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.update_image()

    def on_nmin(self, event):
        self.mpp.nmin = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.update_image()

    def on_nmax(self, event):
        self.mpp.nmax = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.update_image()

    def on_vmax(self, event):
        self.mpp.vmax = event.GetEventObject().GetValue()
        self.mpp.im.set_clim(vmax=self.mpp.vmax)
        self.mpp.canvas.draw()

    def on_background_footprint(self, event):
        self.mpp.background_footprint = event.GetEventObject().GetValue()
        self.mpp._img_corr = None
        self.mpp._xy = None
        self.mpp.update_image()

    def on_beam_center_sigma(self, event):
        self.mpp.beam_center_sigma = event.GetEventObject().GetValue()
        self.mpp.update_image()

    def on_display_raw_data(self, event):
        val = event.GetEventObject().GetValue()
        self.mpp.show_raw_data = val
        self.mpp.update_image()

    def on_show_peaks(self, event):
        val = event.GetEventObject().GetValue()
        self.mpp.show_peaks = val
        self.mpp.update_image()

    def on_remove_background(self, event):
        val = event.GetEventObject().GetValue()
        self.mpp._xy = None
        self.mpp.remove_background = val
        self.mpp.update_image()


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

        self.show_raw_data = True
        self.show_peaks = True
        self.remove_background = True

        self.vmax = 500
        self.vmin = 0

        self.background_footprint = 19
        self.beam_center_sigma = 10

        self.numpeaks = 0
        self.beam_center = []

        self.apply_stretch_correction = True
        self.stretch_azimuth = -6.61
        self.stretch_amplitude = 2.43

        self.min_npeaks = MIN_NPEAKS
        self.min_resolution = MIN_RESOLUTION

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

        self.im_shape = 512, 512
        self.im = self.ax.imshow(np.random.random(self.im_shape), cmap="gray", vmax=self.vmax)
        self.coords, = self.ax.plot([], [], marker="o", color="red", mew=1, lw=0, mfc="none")
        self.center, = self.ax.plot([], [], marker="o", color="green", lw=0)
        self.reset_properties()

    @property
    def index(self):
        return self._index % len(self.filelist)

    @index.setter
    def index(self, value):
        self._index = value

    def next_image(self, event):
        self.index += 1
        self.load_image()

    def previous_image(self, event):
        self.index -= 1
        self.load_image()

    def load_image(self):
        fn = self.filelist[self.index]
        self.status.SetStatusText("{}/{}: {}".format(self.index, len(self.filelist), fn))
        self.reset_properties()

        img, h = read_image(fn)

        # unsigned integers are bad for doing subtractions later on
        if np.issubdtype(img.dtype, np.unsignedinteger):
            img = img.astype(int)

        self.img = img

        self.update_image()

    def update_image(self):
        if self.show_raw_data:
            data = self.img
        else:
            data = self.img_corr

        if self.im_shape != self.img.shape:
            self.im_shape = self.img.shape
            self.im = self.ax.imshow(data, cmap="gray", vmax=self.vmax)
        else:
            self.im.set_data(data)

        self.draw_image()

    def update_peaks(self):
        self.beam_center = find_beam_center(self.img, sigma=self.beam_center_sigma)
        if self.show_peaks:
            try:
                self.coords.set_xdata(self.xy[:,1])
                self.coords.set_ydata(self.xy[:,0])
            except IndexError:
                self.coords.set_xdata([])
                self.coords.set_ydata([])
            self.center.set_xdata(self.beam_center[1])
            self.center.set_ydata(self.beam_center[0])
        else:
            self.coords.set_xdata([])
            self.coords.set_ydata([])
            self.center.set_xdata([])
            self.center.set_ydata([])

    def reset_properties(self):
        self.beam_center = []
        self.coords.set_xdata([])
        self.coords.set_ydata([])
        self._img_corr = None
        self._labels = None
        self._xy = None

    @property
    def img_corr(self):
        if self._img_corr is None:
            selem = morphology.square(self.background_footprint)
            # skimage only accepts input image as uint16
            self._img_corr = self.img - filters.median(self.img.astype(np.uint16), selem).astype(self.img.dtype)
        return self._img_corr

    @property
    def xy(self):
        if self._xy is None:
            if self.remove_background:
                img = self.img_corr
            else:
                img = self.img
            bg = ndimage.gaussian_filter(img, self.sigmin) - ndimage.gaussian_filter(img, self.sigmax)
        
            labels, numlabels = ndimage.label(bg > self.threshold)
            labels = morphology.remove_small_objects(labels, self.nmin)
            
            props = measure.regionprops(labels, img)
            self._xy = np.array([prop.centroid for prop in props])
        return self._xy

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

        stretch_amplitude = self.e_stretch_amplitude.GetValue()
        stretch_azimuth   = self.e_stretch_azimuth.GetValue()

        stretch_azimuth_rad = np.radians(stretch_azimuth)
        stretch_amplitude_pc = stretch_amplitude/ (2*100)
        tr_mat = affine_transform_ellipse_to_circle(stretch_azimuth_rad, stretch_amplitude_pc)

        for i, fn in enumerate(self.filelist):
            keep_going, skip = dlg.Update(i, "{}/{}\n{}".format(i, total, fn))
            if not keep_going:
                dlg.Destroy()
                break

            img, h = read_image(fn)

            # unsigned integers are bad for doing subtractions later on
            if np.issubdtype(img.dtype, np.unsignedinteger):
                img = img.astype(int)

            beam_center = find_beam_center(img, self.beam_center_sigma)

            if self.remove_background:
                selem = morphology.square(self.background_footprint)
                # skimage only accepts input image as uint16
                img_corr = img - filters.median(img.astype(np.uint16), selem).astype(img.dtype)
            else:
                img_corr = img
            
            # stretch correction second to avoid artifacts at the edges
            img_corr = apply_transform_to_image(img, tr_mat, center=beam_center)

            bg = ndimage.gaussian_filter(img_corr, self.sigmin) - ndimage.gaussian_filter(img_corr, self.sigmax)
            
            labels, numlabels = ndimage.label(bg > self.threshold)
            labels = morphology.remove_small_objects(labels, self.nmin)
            
            props = measure.regionprops(labels, img_corr)
            
            img_corr = np.where(labels > 0, img_corr, np.zeros_like(img_corr))
            
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
            data.attrs["background_footprint"] = self.background_footprint
            data.attrs["sigma_min"] = self.sigmin
            data.attrs["sigma_max"] = self.sigmax
            data.attrs["stretch_amplitude"] = stretch_amplitude
            data.attrs["stretch_azimuth"] = stretch_azimuth
            data.attrs["remove_background"] = self.remove_background
            data.attrs["apply_stretch_correction"] = self.apply_stretch_correction

            npeaks = len(props)

            if npeaks == 0:
                f.close()
                continue

            xy = np.array([prop.centroid for prop in props])
            xyw = np.array([prop.weighted_centroid for prop in props])
            pixels = np.array([prop.filled_area for prop in props])
            intensities = np.array([prop.intensity_image.sum() for prop in props])
            orientations = np.array([prop.orientation for prop in props])
            eccentricities = np.array([prop.eccentricity for prop in props])

            xy_corr = xy - beam_center
            
            try:
                pixelsize = h["ImagePixelsize"]
            except KeyError:
                pixelsize = 1.0

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
            f["peakinfo"].attrs["num_peaks"] = npeaks
            f["peakinfo"].attrs["remove_background"] = self.remove_background
            f["peakinfo"].attrs["background_median_footprint"] = self.background_footprint

            f["peakinfo"].attrs["sigma_min"] = self.sigmin
            f["peakinfo"].attrs["sigma_max"] = self.sigmax
            f["peakinfo"].attrs["threshold"] = self.threshold
            f["peakinfo"].attrs["n_min_pixels"] = self.nmin
            f["peakinfo"].attrs["n_max_pixels"] = self.nmax
            f["peakinfo"].attrs["min_npeaks"] = self.min_npeaks
            f["peakinfo"].attrs["min_resolution"] = self.min_resolution

            radialprofile = radial_profile(img_corr, beam_center[0], beam_center[1])
            f.create_dataset("radialprofile", data=radialprofile)
            f["radialprofile"].attrs["beam_center"] = beam_center
            f["radialprofile"].attrs["source_data"] = "/data"

            f.close()

            hit = (npeaks > self.min_npeaks) and (resolution < self.min_resolution)
            if hit:
                stream.append(outfile)

        dlg.Destroy()

        nhits = len(stream)
        with open("stream.txt", "w") as f:
            f.write("# Hitrate {}/{} = {:.1%}\n".format(nhits, total, float(nhits)/total))
            for fn in stream:
                f.write(fn + "\n")


def select(fns, min_npeaks=MIN_NPEAKS, min_resolution=MIN_RESOLUTION):
    """Reselect diffraction patterns for stream based on min_npeaks and min_resolution"""
    import tqdm

    counter = 0
    stream = []

    for fn in tqdm.tqdm(fns):
        f = h5py.File(fn)
    
        try:
            n, r = f["peakinfo"].attrs["num_peaks"], f["peakinfo"].attrs["resolution"]
        except KeyError:
            f.close()
            continue
    
        if n < min_npeaks:
            f.close()
            continue
        if r > min_resolution:
            f.close()
            continue
    
        counter += 1
        txt = "\n{}        # {:5d}{:4.1f}".format(fn, n, r)
    
        stream.append(txt)
    
        f.close()
    
    with open("stream.txt", "w") as f:
        f.write("# Hitrate {}/{} = {:.1%}".format(counter, len(fns), float(counter)/len(fns)))
        f.writelines(stream)
        f.write("\n")


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

    parser.add_argument("-s", "--select",
                        action="store_true", dest="select",
                        help="Reselect diffraction patterns based on number of peaks and resolution")

    parser.set_defaults(select=False)
    
    options = parser.parse_args()
    arg = options.args

    if not arg:
        if os.path.exists("images"):
            arg = "data/*.h5"
        else:
            parser.print_help()
            sys.exit()

    filelist = glob.glob(arg)

    if options.select:
        minpks = float(raw_input("minimum number of reflections? [default] >> ") or MIN_NPEAKS)
        minres = float(raw_input("minimum resolution? [default] >> ") or MIN_RESOLUTION)
        select(filelist, min_npeaks=minpks, min_resolution=minres)
        sys.exit()

    app = wx.App(redirect=False)
    frame = MainWindow(None, "hitfinder")
    frame.set_filelist(filelist)
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()