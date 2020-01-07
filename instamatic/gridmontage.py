import numpy as np

from .montage import *


class GridMontage:
    """Set up an automated montage map"""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.direction = "updown"
        self.zigzag = True
        self.flip = False

    @property
    def gridspec(self):
        gridspec = {
            "gridshape": (self.nx, self.ny),
            "direction": self.direction,
            "zigzag": self.zigzag,
            "flip": self.flip
        }
        return gridspec

    def setup(self,
              nx: int, ny: int,
              overlap: float = 0.1,
              stage_shift: tuple = (0.0, 0.0),
              binning: int = None) -> "np.array":
        """Set up the experiment, run `GridMontage.start` to acquire data.

        Parameters
        ----------
        nx, ny : int
            Number of images to collect int he x/y directions.
        overlap : float
            How much the images should overlap to calculate the shift between the images.
        stage_shift : tuple
            Apply a shift to the calculated stage coordinates.
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

        res_x, res_y = self.ctrl.cam.getDimensions()

        overlap_x = int(res_x * overlap)
        overlap_y = int(res_y * overlap)

        vect = np.array((res_x - overlap_x, res_y - overlap_y))

        grid = make_grid((nx, ny), direction=self.direction, zigzag=self.zigzag)
        grid_indices = sorted_grid_indices(grid)
        px_coords = grid_indices * vect

        px_center = vect * (np.array(grid.shape) / np.array((nx / 2, ny / 2)))

        stagematrix = self.ctrl.get_stagematrix(binning=binning)

        mati = np.linalg.inv(stagematrix)

        stage_center = np.dot(px_center, mati) + stage_shift
        stagepos = np.dot(px_coords, mati)

        coords = (stagepos - stage_center).astype(int)

        self.stagecoords = coords
        self.grid = grid
        self.mode = self.ctrl.mode
        self.magnification = self.ctrl.magnification.value
        self.spotsize = self.ctrl.spotsize

        print("Setting up gridscan.")
        print("  Mag:", self.magnification)
        print("  Mode:", self.mode)
        print("  Grid: {nx} x {ny}; {self.direction}; zigzag: {self.zigzag}; flip:, {self.flip}")
        print("  Overlap:", self.overlap)
        print()
        print("  Image shape:", res_x, res_y)
        print("  Pixel center:", px_center)
        print("  Spot size:", self.spotsize)

        # return coords

    def start(self):
        """Start the experiment."""
        ctrl = self.ctrl

        buffer = []

        def pre_acquire(ctrl):
            print("Attempt to eliminate backlash.")
            ctrl.stage.eliminate_backlash_xy()

        def acquire(ctrl):
            img, h = ctrl.getImage()
            buffer.append((img, h))

        def post_acquire(ctrl):
            print("Post-acquire: done!")

        ctrl.acquire_at_items(self.stagecoords,
                              acquire=acquire,
                              pre_acquire=pre_acquire,
                              post_acquire=post_acquire)

        self.stagematrix = self.ctrl.get_stagematrix()
        self.buffer = buffer

        self.save()

    def to_montage(self):
        """Convert the experimental data to a `Montage` object."""
        images = [im for im, h in self.buffer]
        m = Montage(images=images, gridspec=self.gridspec, overlap=self.overlap)
        m.update_gridspec(flip=not self.flip)  # BUG: Work-around for gridspec madness
        # Possibly related is that images are rotated 90 deg. in SerialEM mrc files
        m.stagecoords = self.stagecoords
        m.stagematrix = self.stagematrix
        return m

    def save(self, drc: str = None):
        """Save the data to the given directory,
        defaults to the instamatic data directory defined in the config
        """
        from instamatic.formats import write_tiff
        from instamatic.io import get_new_work_subdirectory

        if not drc:
            drc = get_new_work_subdirectory("montage")

        fns = []
        for i, (img, h) in enumerate(self.buffer):
            name = f"mont_{i:04d}.tiff"
            write_tiff(drc / name, img, header=h)
            fns.append(name)

        d = {}
        d["stagecoords"] = self.stagecoords.tolist()
        d["stagematrix"] = self.stagematrix.tolist()
        d["gridshape"] = [self.nx, self.ny]
        d["direction"] = self.direction
        d["zigzag"] = self.zigzag
        d["overlap"] = self.overlap
        d["filenames"] = fns
        d["magnification"] = self.magnification
        d["mode"] = self.mode
        d["spotsize"] = self.spotsize

        import yaml
        yaml.dump(d, stream=open(drc / "montage.yaml", "w"))
        print(f" >> Wrote {len(self.stagecoords)} montage images to {drc}")


if __name__ == '__main__':
    from instamatic import TEMController
    ctrl = TEMController.initialize()
    ctrl.mode = "lowmag"
    ctrl.magnification.value = 100

    gm = GridMontage(ctrl)
    pos = m.setup(5, 5)

    m = gm.to_montage()

    # unoptimized coords
    coords = m.get_montage_coords(dv)
    m.plot_stitched(coords)

    # get coords optimized using cross correlation
    dv = m.get_difference_vectors()
    coords2 = m.get_optimized_montage_coords(dv)
    m.plot_stitched(coords2)
