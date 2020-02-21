import time

import matplotlib.pyplot as plt
import mrcfile
import numpy as np

from instamatic.formats import read_tiff
from instamatic.serialem import read_nav_file


class Browser:
    """docstring for Browser."""

    def __init__(self, montage):
        super().__init__()
        self.montage = montage
        self.mmap = None
        self.imagecoords = montage.feature_coords_image
        self.stagecoords = montage.feature_coords_stage
        self.stitched = montage.stitched

    def set_images(self, mmm: str = 'mmm.mrc'):
        self.mmap = mrcfile.mmap(mmm)

    def set_nav_file(self, nav='output.nav'):
        nav_items = read_nav_file(nav)
        self.map_items = [item for item in nav_items if item.kind == 'Map']
        self.stagecoords = np.array([mi.stage_xy for mi in self.map_items]) * 1000
        self.imagecoords = self.montage.stage_to_pixelcoords(self.stagecoords)

    def set_data_location(self, s: str = 'data/diff_{key}.tiff'):
        self.data_fmt = s

    def start(self, ctrl):
        double_click_delay = 0.5

        fig, (ax1, ax2, ax3) = plt.subplots(ncols=3, figsize=(10, 5))

        px1_x, px1_y = self.imagecoords.T

        # FIXME: How to transform the coordinates instead?
        self.stitched = np.flipud(np.rot90(self.stitched))

        im1 = ax1.imshow(self.stitched)
        ax1.set_title('Global map')

        # FIXME: Where does the 512 come from?
        ax1.scatter(px1_x, px1_y + 512, marker='+', color='r', picker=8)

        im2 = ax2.imshow(self.mmap.data[0], vmax=5000)
        ax2.set_title('Medium image')
        data2, = ax2.plot([], [], marker='+', color='red', picker=8, lw=0)

        im3 = plt.imshow(np.arange(100).reshape(10, 10), vmax=5000)

        key_active = ''
        current_ind = -1
        t0 = time.clock()
        map_item = None

        def onclick(event):
            nonlocal current_ind, t0, map_item

            t1 = time.clock()

            axes = event.artist.axes
            ind = event.ind[0]

            if axes == ax1:
                coord = self.stagecoords[ind]
                img2 = self.mmap.data[ind]

                # FIXME: Why is the flip needed here?
                img2 = np.flipud(img2)

                im2.set_data(img2)

                map_item = self.map_items[ind]
                coords = np.array([item.stage_xy for item in map_item.markers.values()])

                pxcoords = map_item.stage_to_pixelcoords(coords)

                xdata, ydata = pxcoords.T
                data2.set_xdata(xdata)
                data2.set_ydata(ydata)
                ax2.set_title(map_item.tag)

            elif axes == ax2:
                key, nav_item = list(map_item.markers.items())[ind]
                coord = nav_item.stage_xy
                imagecoord = map_item.pixel_to_stagecoords(coord)

                try:
                    img3 = read_tiff(self.data_fmt.format(key=key))[0]
                    im3.set_data(img3)
                    ax3.set_title(key)
                except FileNotFoundError:
                    pass

            if ind == current_ind and (t1 - t0 < double_click_delay):
                print(f'Moving stage to:', coord)
                ctrl.stage.xy = coord

            t0 = t1
            current_ind = ind
            fig.canvas.draw()

        fig.canvas.mpl_connect('pick_event', onclick)
