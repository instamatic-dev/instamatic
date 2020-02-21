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

    def start(self, ctrl):
        double_click_delay = 0.5

        fig, (ax1, ax2, ax3) = plt.subplots(ncols=3, figsize=(10, 5))

        px1_x, px1_y = self.imagecoords.T

        im1 = ax1.imshow(self.stitched)
        ax1.set_title('Global map')
        ax1.scatter(px1_y, px1_x, marker='+', color='r', picker=8)

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
                im2.set_data(img2)

                map_item = self.map_items[ind]
                coords = np.array([item.stage_xy for item in map_item.markers.values()])

                pxcoords = map_item.stage_to_pixelcoords(coords)

                xdata, ydata = pxcoords.T
                data2.set_xdata(ydata)
                data2.set_ydata(xdata)
                ax2.set_title(map_item.tag)

            elif axes == ax2:
                key, nav_item = list(map_item.markers.items())[ind]
                print(key)

                imagecoord = map_item.pixel_to_stagecoords(nav_item.stage_xy)

                try:
                    img3 = read_tiff(f'data/diff_{key}.tiff')[0]
                    im3.set_data(img3)
                    ax3.set_title(key)
                except Exception:
                    pass

            if ind == current_ind and (t1 - t0 < double_click_delay):
                print(f'Moving stage to:', coord)
                ctrl.stage.xy = coord

            t0 = t1
            current_ind = ind
            fig.canvas.draw()

        fig.canvas.mpl_connect('pick_event', onclick)
