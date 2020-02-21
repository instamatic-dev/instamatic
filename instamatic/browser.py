import time

import matplotlib.pyplot as plt
import mrcfile


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

    def start(self, ctrl):
        double_click_delay = 0.5

        fig, (ax1, ax2) = plt.subplots(ncols=2, figsize=(10, 5))

        px1_x, px1_y = self.imagecoords.T

        im1 = ax1.imshow(self.stitched)
        ax1.set_title('Global map')
        ax1.scatter(px1_y, px1_x, marker='+', color='r', picker=8)

        im2 = ax2.imshow(self.mmap.data[0], vmax=5000)
        ax2.set_title('Medium image')

        key_active = ''
        current_ind = -1
        t0 = time.clock()

        def onclick(event):
            nonlocal current_ind, t0

            t1 = time.clock()

            axes = event.artist.axes
            ind = event.ind[0]

            data = self.mmap.data[ind]
            im2.set_data(data)

            if ind == current_ind and (t1 - t0 < double_click_delay):
                coord = self.stagecoords[ind]
                print(f'Moving stage to:', coord)
                ctrl.stage.xy = coord

            t0 = t1
            current_ind = ind

        fig.canvas.mpl_connect('pick_event', onclick)
