from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from pyserialem.montage import make_grid, sorted_grid_indices

from instamatic import config
from instamatic.config import defaults

from .montage import *


class GridMontage:
    """Set up an automated montage map."""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        gridspec = defaults.gridmontage['gridspec']
        self.direction = gridspec['direction']
        self.zigzag = gridspec['zigzag']
        self.flip = gridspec['flip']

    @property
    def gridspec(self):
        gridspec = {
            'gridshape': (self.nx, self.ny),
            'direction': self.direction,
            'zigzag': self.zigzag,
            'flip': self.flip,
        }
        return gridspec

    def setup(
        self,
        nx: int,
        ny: int,
        overlap: float = defaults.gridmontage['overlap'],
        stage_shift: tuple = (0.0, 0.0),
        binning: int = None,
    ) -> 'np.array':
        """Set up the experiment, run `GridMontage.start` to acquire data.

        Parameters
        ----------
        nx, ny : int
            Number of images to collect int he x/y directions.
        overlap : float
            How much the images should overlap to calculate the shift between the images.
        stage_shift : tuple
            Apply a shift to the calculated stage coordinates. For example, to set the origin. Otherwise, the origin is taken at x=0, y=0.
        binning : int
            Binning for the images.

        Returns
        -------
        coords : np.array
            Stage coordinates for the montage acquisition
        """
        self.nx = nx
        self.ny = ny
        self.overlap = overlap

        if not binning:
            binning = self.ctrl.cam.get_binning()

        res_x, res_y = self.ctrl.cam.get_image_dimensions()

        overlap_x = int(res_x * overlap)
        overlap_y = int(res_y * overlap)

        vect = np.array((res_x - overlap_x, res_y - overlap_y))

        grid = make_grid((nx, ny), direction=self.direction, zigzag=self.zigzag)
        grid_indices = sorted_grid_indices(grid)
        px_coords = grid_indices * vect

        px_center = vect * ((np.array(grid.shape) / 2) - 0.5)

        self.stagematrix = self.ctrl.get_stagematrix(binning=binning)

        stage_center = np.dot(px_center, self.stagematrix) + stage_shift
        stagepos = np.dot(px_coords, self.stagematrix)

        coords = (stagepos - stage_center).astype(int)

        mode = self.ctrl.mode.get()
        magnification = self.ctrl.magnification.value
        self.stagecoords = coords
        self.grid = grid
        self.mode = mode
        self.magnification = magnification
        self.abs_mag_index = self.ctrl.magnification.absolute_index
        self.spotsize = self.ctrl.spotsize
        self.binning = binning
        self.pixelsize = config.calibration[mode]['pixelsize'][magnification]  # unbinned

        print('Setting up gridscan.')
        print(f'  Mag: {self.magnification}x')
        print(f'  Mode: `{self.mode}`')
        print(
            f'  Grid: {nx} x {ny}; {self.direction}; zigzag: {self.zigzag}; flip: {self.flip}'
        )
        print(f'  Overlap: {self.overlap}')
        print()
        print(f'  Image shape: {res_x} x {res_y}')
        print(f'  Pixel center: {px_center}')
        print(f'  Spot size: {self.spotsize}')
        print(f'  Binning: {self.binning}')

    def start(self):
        """Start the experiment."""
        ctrl = self.ctrl

        buffer = []

        def eliminate_backlash(ctrl):
            print('Attempting to eliminate backlash...')
            ctrl.stage.eliminate_backlash_xy()

        def acquire_image(ctrl):
            img, h = ctrl.get_image()
            buffer.append((img, h))

        def post_acquire(ctrl):
            pass

        ctrl.acquire_at_items(
            self.stagecoords,
            acquire=acquire_image,
            pre_acquire=eliminate_backlash,
            post_acquire=None,
        )

        self.buffer = buffer

        self.save()

    def to_montage(self):
        """Convert the experimental data to a `Montage` object."""
        images = [im for im, h in self.buffer]
        m = Montage(
            images=images,
            gridspec=self.gridspec,
            overlap=self.overlap,
            stagematrix=self.stagematrix,
            stagecoords=self.stagecoords,
            pixelsize=self.pixelsize,
        )
        m.update_gridspec(flip=not self.flip)  # BUG: Work-around for gridspec madness
        # Possibly related is that images are rotated 90 deg. in SerialEM mrc files

        return m

    def save(self, drc: str = None):
        """Save the data to the given directory.

        drc : str
            Path of the output directory. If `None`, it defaults to the instamatic data directory defined in the config.
        """
        from instamatic.formats import write_tiff
        from instamatic.io import get_new_work_subdirectory

        if not drc:
            drc = get_new_work_subdirectory('montage')

        fns = []
        for i, (img, h) in enumerate(self.buffer):
            name = f'mont_{i:04d}.tiff'
            write_tiff(drc / name, img, header=h)
            fns.append(name)

        n_images = i + 1

        d = {
            'stagecoords': self.stagecoords.tolist(),
            'stagematrix': self.stagematrix.tolist(),
            'gridshape': [self.nx, self.ny],
            'direction': self.direction,
            'zigzag': self.zigzag,
            'overlap': self.overlap,
            'filenames': fns,
            'magnification': self.magnification,
            'abs_mag_index': self.abs_mag_index,
            'mode': self.mode,
            'spotsize': self.spotsize,
            'flip': self.flip,
            'image_binning': self.binning,
            'pixelsize': self.pixelsize,
        }

        import yaml

        yaml.dump(d, stream=open(drc / 'montage.yaml', 'w'))
        print(f' >> Wrote {n_images} montage images to {drc}')

    def plot(self):
        """Simple plot of the stage coordinates."""
        coords = self.stagecoords / 1000  # nm -> μm
        plt.scatter(*coords.T, marker='.', color='red')
        for i, coord in enumerate(coords):
            plt.text(*coord, s=f' {i}')
        plt.axis('equal')
        plt.title('Stage coordinates for grid montage')
        plt.xlabel('x (μm)')
        plt.ylabel('y (μm)')


if __name__ == '__main__':
    from instamatic import controller

    ctrl = controller.initialize()
    ctrl.mode.set('lowmag')
    ctrl.magnification.value = 100

    gm = GridMontage(ctrl)
    pos = m.setup(5, 5)

    m = gm.to_montage()

    # unoptimized coords
    coords = m.get_montage_coords(dv)
    m.plot_stitched(coords)

    # get coords optimized using cross correlation
    coords2 = m.get_montage_coords(optimize=True)
    m.plot_stitched(coords2)
