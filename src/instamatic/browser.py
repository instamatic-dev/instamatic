from __future__ import annotations

import os
import time

import matplotlib.pyplot as plt
import mrcfile
import numpy as np
from pyserialem import read_nav_file

from instamatic.formats import read_tiff


class Browser:
    """Simple Navigator class."""

    def __init__(self, montage):
        super().__init__()
        self.montage = montage
        self.mmap = None
        self.imagecoords = montage.feature_coords_image
        self.stagecoords = montage.feature_coords_stage
        self.stitched = montage.stitched

    def set_images(self, mmm: str = 'mmm.mrc'):
        """Set the path to the image data (medium mag).

        Must be mrc format and contain multiple pages.
        """
        self.mmap = mrcfile.mmap(mmm)

    def set_nav_file(self, nav: str = 'output.nav'):
        """Set the `.nav` file to load the stage/image coordinates from."""
        nav_items = read_nav_file(nav)
        self.map_items = [item for item in nav_items if item.kind == 'Map']
        self.stagecoords = np.array([mi.stage_xy for mi in self.map_items]) * 1000
        self.imagecoords = self.montage.stage_to_pixelcoords(self.stagecoords)

    def set_data_location(self, s: str = 'data/diff_{label}.tiff'):
        """Set the data location.

        Must be a string containing the `label` formatting key. The
        label gets filled in by the tag defined in the .nav file.
        """
        self.data_fmt = s

    def start(self, ctrl, cmap: str = 'gray', vmax=5000, levels: int = 3):
        """Display the browser panel.

        Parameters
        ----------
        ctrl : `TEMController`
            TEM control object to allow stage movement to different coordinates.
        cmap : str
            Color map for the images, default 'gray'
        vmax : int
            Vmax defines the upper limit that the colormap covers.
        levels : int
            Number of panels to show:
                1 - Just show the global map
                2 - Additionally show the medium mag map
                3 - Additionally show the data
        """
        assert 3 >= levels > 0, '`levels` must be between 1 and 3'

        self.fig, axes = plt.subplots(ncols=levels, figsize=(10, 5))
        self.ctrl = ctrl
        self.levels = levels
        self.current_ind = 0
        self.gm_ind = 0
        self.mmm_ind = 0
        self.t0 = 0.0

        if levels >= 1:
            self.ax1 = axes if levels == 1 else axes[0]
            self.setup_l1(cmap=cmap, vmax=vmax)
        if levels >= 2:
            self.ax2 = axes[1]
            self.setup_l2(cmap=cmap, vmax=vmax)
            self.process_click_ax1()  # fake click to trigger update
            self.update_ax2()
        if levels >= 3:
            self.ax3 = axes[2]
            self.setup_l3(cmap=cmap, vmax=vmax)
            self.process_click_ax2()  # fake click to trigger update
            self.update_ax3()

        self.fig.canvas.mpl_connect('pick_event', self.onclick)

    def setup_l1(self, cmap='gray', vmax=5000):
        """Setup the left global map panel."""
        # FIXME: How to transform the coordinates instead?
        self.stitched = np.flipud(np.rot90(self.stitched))
        self.blank = np.arange(100).reshape(10, 10)

        px1_x, px1_y = self.imagecoords.T
        self.im1 = self.ax1.imshow(self.stitched, vmax=vmax, cmap=cmap)
        # FIXME: Where does the 512 come from?
        self.data1 = self.ax1.scatter(px1_x, px1_y + 512, marker='+', color='r', picker=8)
        self.ax1.set_title('Global map')
        self.ax1.axis('off')

    def setup_l2(self, cmap='gray', vmax=5000):
        """Setup the middle medium mag panel."""
        self.im2 = self.ax2.imshow(self.mmap.data[0], vmax=vmax, cmap=cmap)
        self.data2 = self.ax2.scatter([], [], marker='+', color='red', picker=8, lw=1.0)
        self.ax2.set_title('Medium image')
        self.ax2.axis('off')

    def setup_l3(self, cmap='gray', vmax=5000):
        """Setup the right data panel."""
        self.im3 = self.ax3.imshow(self.blank, vmax=vmax, cmap=cmap)
        self.ax3.set_title('Data')
        self.ax3.axis('off')

    def onclick(self, event, double_click_delay=0.5):
        t1 = time.perf_counter()

        axes = event.artist.axes
        ind = event.ind[0]

        if axes == self.ax1:
            self.process_click_ax1(ind=ind)
        elif axes == self.ax2:
            self.process_click_ax2(ind=ind)

        if self.levels > 1:
            self.update_ax2(ind)
        if self.levels > 2:
            self.update_ax3(ind)

        if ind == self.current_ind and (t1 - self.t0 < double_click_delay):
            print('Moving stage to:', self.coord)
            self.ctrl.stage.xy = self.coord

        self.t0 = time.perf_counter()
        self.current_ind = ind
        self.fig.canvas.draw()

    def process_click_ax1(self, ind: int = 0):
        self.gm_ind = ind
        self.coord = self.stagecoords[ind]
        self.map_item = self.map_items[ind]
        self.marker_labels, self.markers = zip(*self.map_item.markers.items())

    def process_click_ax2(self, ind: int = 0):
        self.mmm_ind = ind
        marker = self.markers[ind]
        coord = marker.stage_xy
        self.coord = coord

    def update_ax1(self):
        pass

    def update_ax2(self, ind: int = 0):
        ind = self.gm_ind

        img = self.mmap.data[ind]
        # FIXME: Why is the flip needed here?
        img = np.flipud(img)
        self.im2.set_data(img)

        coords = np.array([item.stage_xy for item in self.markers])
        colors_rgba = np.array([item.color_rgba for item in self.markers])

        pxcoords = self.map_item.stage_to_pixelcoords(coords)

        xdata, ydata = pxcoords.T
        self.data2.set_offsets(pxcoords)
        self.data2.set_color(colors_rgba)
        self.ax2.set_title(self.map_item.tag)

    def update_ax3(self, ind: int = 0):
        ind = self.mmm_ind
        label = self.marker_labels[ind]

        data_fn = self.data_fmt.format(label=label)

        if os.path.exists(data_fn):
            img = read_tiff(data_fn)[0]
            self.im3.set_data(img)
            self.ax3.set_title(label)
        else:
            self.im3.set_data(self.blank)
            self.ax3.set_title(f'{label}\nFile not available!')
