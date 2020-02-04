from pathlib import Path

import lmfit
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patches
from scipy import ndimage
from skimage import filters
from skimage.feature import register_translation
from tqdm.auto import tqdm

from instamatic import config
from instamatic.imreg import translation
from instamatic.tools import bin_ndarray


def sorted_grid_indices(grid):
    """Sorts 2d the grid by its values, and returns an array with the indices
    (i.e. np.argsort on 2d arrays) https://stackoverflow.com/a/30577520."""
    return np.dstack(np.unravel_index(np.argsort(grid.ravel()), grid.shape))[0]


def find_threshold(values, half='lower') -> float:
    """Find largest discontinuity in the `lower` or `upper` half of the data.

    Parameters
    ----------
    half : str
        Whether to use the `upper` or `lower` half of the data after sorting

    Returns
    -------
    threshold : float
        Threshold splitting the largest discontinuity to segment data with
    """
    x = np.array(sorted(values))
    halfway = int(len(x) / 2)
    sel = x[:halfway] if half == 'lower' else x[halfway:]
    diff = np.diff(sel)
    i = diff.argmax()
    if half == 'upper':
        i += halfway
    thresh = (x[i] + x[i + 1]) / 2
    return thresh


def weight_map(shape, method='block', plot=False):
    """Generate a weighting map for the given shape.

    Parameters
    ----------
    shape : tuple
        Shape defines the 2 integers defining the shape of the image
    method : str
        Method to use `circle`/`block`
    plot : bool
        Plot the image

    Returns
    -------
    weight : np.array
        Weight array with the given shape
    """
    res_x, res_y = shape
    c_x = int(res_x / 2) - 0.5
    c_y = int(res_y / 2) - 0.5

    corner = (c_x**2 + c_y**2)**0.5

    a, b = np.meshgrid(np.arange(-c_x, c_x + 1), np.arange(-c_y, c_y + 1))

    if method == 'block':
        a2 = c_x - np.abs(a)
        b2 = c_y - np.abs(b)

        d = np.min(np.stack((a2, b2)), axis=0)
    elif method == 'circle':
        d = corner - np.sqrt(a**2 + b**2)
    else:
        raise ValueError(f'No such method: `{method}`')

    # scale to 1
    d = d / d.max()

    if plot:
        plt.imshow(d)

    return d


def make_grid(gridshape: tuple, direction: str = 'updown', zigzag: bool = True, flip: bool = False) -> 'np.array':
    """Defines the grid montage collection scheme.

    Parameters
    ----------
    gridshape : tuple(int, int)
        Defines the shape of the grid
    direction : str
        Defines the direction of data collection starting from the top (lr, rl) or left-hand (ud, du) side
        `updown`, `downup`, `leftright`, `rightleft`
    zigzag : bool
        Defines if the data has been collected in a zigzag manner
    flip : bool
        Flip around the vertical (lr, rl) or horizontal (ud, du) axis, i.e. start from the
        botton (lr, rl) or right-hand (ud, du) side.

    Returns
    -------
    np.array
    """
    nx, ny = gridshape
    grid = np.arange(nx * ny).reshape(gridshape)

    if zigzag:
        grid[1::2] = np.fliplr(grid[1::2])

    if direction == 'updown':
        pass
        if flip:
            grid = np.fliplr(grid)
    elif direction == 'downup':
        grid = np.flipud(grid)
        if flip:
            grid = np.fliplr(grid)
    elif direction == 'rightleft':
        grid = grid.T
        grid = np.fliplr(grid)
        if flip:
            grid = np.flipud(grid)
    elif direction == 'leftright':
        grid = grid.T
        if flip:
            grid = np.flipud(grid)
    else:
        raise ValueError(f'Invalid direction: {direction}')

    return grid


def make_slices(overlap_x: int, overlap_y: int, shape=(512, 512), plot: bool = False) -> dict:
    """Make slices for left/right/top/bottom image.

    Parameters
    ----------
    overlap_x/overlap_y : int
        Defines how far to set the overlap from the edge (number of pixels),
        this corresponds to the overlap between images
    shape : tuple:
        Define the shape of the image (only for plotting)
    plot : bool
        Plot the boundaries on blank images

    Returns
    -------
    Dictionary with the slices for each side
    """
    d = {}

    s_right = np.s_[:, -overlap_x:]
    s_left = np.s_[:, :overlap_x]
    s_top = np.s_[:overlap_y]
    s_bottom = np.s_[-overlap_y:]

    slices = (s_right, s_left, s_top, s_bottom)
    labels = ('right', 'left', 'top', 'bottom')

    d = dict(zip(labels, slices))

    if plot:
        fig, axes = plt.subplots(2, 2, sharex=True, sharey=True)
        axes = axes.flatten()

        for ax, s_, label in zip(axes, slices, labels):
            arr = np.zeros(shape, dtype=int)
            arr[s_] = 1
            ax.imshow(arr)
            ax.set_title(label)

        plt.show()

    return d


def define_directions(pairs: list):
    """Define pairwise relations between indices.

    Takes a list of index pair dicts, and determines on which side they
    are overlapping. The dictionary is updated with the keywords
    `side0`/`side1`.
    """
    for pair in pairs:
        i0, j0 = pair['idx0']
        i1, j1 = pair['idx1']

        # checked 21-11-2019 for 'leftright' config
        if j0 == j1:
            if i1 > i0:
                side0, side1 = 'bottom', 'top'
            else:
                side0, side1 = 'top', 'bottom'
        else:
            if j1 > j0:
                side0, side1 = 'right', 'left'
            else:
                side0, side1 = 'left', 'right'

        # print(i0, j0, i1, j1, side0, side1)

        pair['side0'] = side0
        pair['side1'] = side1

    return pairs


def define_pairs(grid: 'np.ndarray'):
    """Take a sequence grid and return all pairs of neighbours.

    Returns a list of dictionaries containing the indices of the pairs
    (neighbouring only), and the corresponding sequence numbers
    (corresponding to the image array)
    """
    nx, ny = grid.shape

    footprint = np.array([[0, 1, 0],
                          [1, 0, 1],
                          [0, 1, 0]])

    shape = np.array(footprint.shape)
    assert shape[0] == shape[1], 'Axes must be equal'
    assert shape[0] % 2 == 1, 'Axis length must be odd'
    center = shape // 2

    connected = np.argwhere(footprint == 1) - center

    pairs = []

    for idx0, i0 in np.ndenumerate(grid):
        neighbours = connected + idx0

        for neighbour in neighbours:
            neighbour = tuple(neighbour)
            if neighbour[0] < 0 or neighbour[0] >= nx:
                pass
            elif neighbour[1] < 0 or neighbour[1] >= ny:
                pass
            else:
                assert i0 == grid[idx0]
                d = {
                    'seq0': grid[idx0],
                    'seq1': grid[neighbour],
                    'idx0': idx0,
                    'idx1': neighbour,
                }
                pairs.append(d)

    return pairs


def disambiguate_shift(strip0, strip1, shift, verbose: bool = False) -> tuple:
    """Disambiguate the shifts obtained from cross correlation."""
    shift_x, shift_y = shift

    best_sum = np.inf
    best_shift = shift

    for i in (-1, 1):
        for j in (-1, 1):
            new_shift = (i * shift_x, j * shift_y)
            strip1_offset = ndimage.shift(strip1, new_shift)
            offset = strip1_offset - strip0.astype(float)
            sum_score = np.abs(offset).sum()
            if verbose:
                print(f'{i:2d} {j:2d} -> {sum_score:10.0f}  {new_shift}')
            if sum_score < best_sum:
                best_sum = sum_score
                best_shift = new_shift

    if verbose:
        print('Disambiguated shift:', best_shift)

    return best_shift


def plot_images(im0, im1, seq0, seq1, side0, side1, idx0, idx1):
    fig, axes = plt.subplots(ncols=2, figsize=(6, 3))
    ax0, ax1 = axes.flatten()

    ax0.imshow(im0)
    ax0.set_title(f'{seq0} {idx0} {side0}')
    ax0.set_axis_off()
    ax1.imshow(im1)
    ax1.set_title(f'{seq1} {idx1} {side1}')
    ax1.set_axis_off()
    plt.tight_layout()
    plt.show()


def plot_fft(strip0, strip1, shift, fft, side0, side1):
    fig, axes = plt.subplots(nrows=4, figsize=(8, 5))
    axes = axes.flatten()
    for ax in axes:
        ax.set_axis_off()
    ax0, ax1, ax2, ax3 = axes

    shape0 = strip0.shape
    shape1 = strip1.shape

    if shape0[0] > shape1[1]:
        strip0 = strip0.T
        strip1 = strip1.T
        fft = fft.T
        shift_y, shift_x = shift
    else:
        shift_x, shift_y = shift

    # Show difference
    strip1_shifted = ndimage.shift(strip1, (shift_x, shift_y))
    difference = strip1_shifted - strip0.astype(float)

    ax0.imshow(strip0, interpolation='nearest')
    ax0.set_title(f'{side0}')
    ax1.imshow(strip1, interpolation='nearest')
    ax1.set_title(f'{side1}')
    ax2.imshow(difference, interpolation='nearest')
    ax2.set_title('Abs(Difference)')
    ax3.imshow(fft, vmin=np.percentile(fft, 50.00), vmax=np.percentile(fft, 99.99))
    ax3.set_title(f'Cross correlation (max={fft.max():.4f})')

    plt.subplots_adjust(hspace=0.0)
    plt.show()


def plot_shifted(im0, im1, difference_vector, seq0, seq1, idx0, idx1, res_x, res_y):
    blank = np.zeros((res_x * 2, res_y * 2), dtype=np.int32)

    center = np.array(blank.shape) // 2
    origin = np.array((res_x, res_y)) // 2

    coord0 = (center - difference_vector / 2 - origin).astype(int)
    coord1 = (center + difference_vector / 2 - origin).astype(int)

    print(f'Coord0: {coord0} | Coord1: {coord1}')

    txt = f'Difference vector\n#{seq0}:{idx0} -> #{seq1}:{idx1} = {difference_vector}'

    blank[coord0[0]: coord0[0] + res_x, coord0[1]: coord0[1] + res_y] += im0
    blank[coord1[0]: coord1[0] + res_x, coord1[1]: coord1[1] + res_y] += im1

    # Create a Rectangle patch
    rect0 = patches.Rectangle(coord0[::-1], res_x, res_y, linewidth=1, edgecolor='r', facecolor='none')
    rect1 = patches.Rectangle(coord1[::-1], res_x, res_y, linewidth=1, edgecolor='r', facecolor='none')

    fig, ax = plt.subplots(1, figsize=(8, 8))

    # Add the patch to the Axes
    ax.add_patch(rect0)
    ax.add_patch(rect1)

    ax.imshow(blank)
    ax.set_title(txt)
    ax.set_axis_off()
    plt.show()


class MontagePatch:
    """Simple class to calculate the bounding box for an image tile as part of
    a montage.

    Parameters
    ----------
    image : np.ndarray [ m x n ]
        Original image tile
    coord : tuple
        Tuple with x/y coordinates of the patch (original size) location in the montage image
    binning : int
        Binning of the image patch
    """

    def __init__(self, image, coord, binning: int = 1):
        super().__init__()
        self.binning = binning
        self.coord = coord
        self._image = image
        self._shape = image.shape

    @property
    def shape(self):
        res_x, res_y = self._shape
        shape = int(res_x / self.binning), int(res_y / self.binning)
        return shape

    @property
    def res_x(self):
        return self.shape[0]

    @property
    def res_y(self):
        return self.shape[1]

    @property
    def image(self):
        return bin_ndarray(self._image, self.shape)

    @property
    def x0(self):
        return int(self.coord[0] / self.binning)

    @property
    def x1(self):
        return self.x0 + self.shape[0]

    @property
    def y0(self):
        return int(self.coord[1] / self.binning)

    @property
    def y1(self):
        return self.y0 + self.shape[1]


class Montage:
    """This class is used to stitch together a set of images to make a larger
    image.

    Parameters
    ----------
    images : list
        List of images in numpy format
    gridspec : dict
        Dictionary defining the grid characteristics, directly passed to `make_grid`.
    overlap : float
        Defines the % of overlap between the images

    Based on Preibisch et al. (2009), Bioinformatics, 25(11):1463-1465
             http://dx.doi.org/10.1093/bioinformatics/btp184
    """

    def __init__(self,
                 images: list,
                 gridspec: dict,
                 overlap=0.1,
                 ):
        super().__init__()

        self.images = images
        self.image_shape = images[0].shape
        self.gridspec = gridspec
        self.grid = make_grid(**gridspec)
        self.software = None

        res_x, res_y = self.image_shape
        self.overlap_x = int(res_x * overlap)
        self.overlap_y = int(res_y * overlap)

    @classmethod
    def from_serialem_mrc(cls, filename: str, gridshape: tuple, direction: str = 'leftright', zigzag: bool = True):
        """Load a montage object from a SerialEM file image stack.

        Parameters
        ----------
        filename : str
            Filename of the mrc file to load.
        gridshape : tuple(2)
            Tuple describing the number of of x and y points in the montage grid.
            TODO: Find a way to get this from the .mrc/.mdoc
        direction : str
            Defines the direction of data collection
        zigzag : bool
            Defines if the data has been collected in a zigzag manner

        Returns
        -------
        Montage object constructed from the given images
        """
        import mrcfile
        from instamatic.serialem import read_mdoc_file
        gm = mrcfile.open(filename)
        images = gm.data

        # is the mdoc needed?
        mdoc = read_mdoc_file(filename + '.mdoc', only_kind='zvalue')
        assert len(mdoc) == len(images)

        gridspec = {
            'gridshape': gridshape,
            'direction': direction,
            'zigzag': zigzag,
            'flip': False,
        }

        m = cls(images=images, gridspec=gridspec)
        m.mdoc = mdoc
        m.filename = filename
        m.stagecoords = np.array([d['StagePosition'] for d in m.mdoc]) * 1000  # um->nm
        c1 = np.array([d['PieceCoordinates'][0:2] for d in m.mdoc])
        m.piececoords = c1[:, ::-1]  # flip coordinates
        c2 = np.array([d['AlignedPieceCoords'][0:2] for d in m.mdoc])
        c2 = c2[:, ::-1]  # flip coordinates
        c2 -= c2.min(axis=0)  # set minval to 0
        m.alignedpiececoords = c2

        try:
            c3 = np.array([d['AlignedPieceCoordsVS'][0:2] for d in m.mdoc])
        except KeyError:
            pass
        else:
            c3 = c3[:, ::-1]  # flip coordinates
            c3 -= c3.min(axis=0)  # set minval to 0
            m.alignedpiececoordsvs = c3

        m.image_binning = m.mdoc[-1]['Binning']
        m.magnification = m.mdoc[-1]['Magnification']
        m.coords = m.piececoords  # map .coords to .piececoords
        m.software = 'serialem'

        try:
            m.optimized_coords = m.alignedpiececoordsvs  # map .optimized_coords to .alignedpiececoordsvs
        except AttributeError:
            m.optimized_coords = m.alignedpiececoords  # map .optimized_coords to .alignedpiececoords

        return m

    def update_gridspec(self, **gridspec):
        """Update the grid specification."""
        self.gridspec.update(gridspec)
        self.grid = make_grid(**self.gridspec)

    @classmethod
    def from_montage_yaml(cls, filename: str = 'montage.yaml'):
        """Load montage from a series of tiff files + `montage.yaml`)"""
        import yaml
        from instamatic.formats import read_tiff

        p = Path(filename)
        drc = p.parent

        d = yaml.safe_load(open(p, 'r'))
        fns = (drc / fn for fn in d['filenames'])
        overlap = d['overlap']

        images = [read_tiff(fn)[0] for fn in fns]

        gridspec = {k: v for k, v in d.items() if k in ('gridshape', 'direction', 'zigzag', 'flip')}

        m = cls(images=images, gridspec=gridspec, overlap=overlap)
        m.update_gridspec(flip=not d['flip'])  # BUG: Work-around for gridspec madness
        # Possibly related is that images are rotated 90 deg. in SerialEM mrc files
        m.stagecoords = np.array(d['stagecoords'])
        m.stagematrix = np.array(d['stagematrix'])
        m.mode = d['mode']
        m.magnification = d['magnification']
        m.image_binning = d['binning']
        m.software = 'instamatic'

        return m

    def set_calibration(self, mode: str, magnification: int) -> None:
        """Set the calibration parameters for the montage map. Sets the
        pixelsize and stagematrix from the config files.

        Parameters
        ----------
        mode : str
            The TEM mode used, i.e. `lowmag`, `mag1`, `samag`
        magnification : int
            The magnification used
        """
        self.pixelsize = getattr(config.calibration, f'pixelsize_{mode}')[magnification]

        binning = self.image_binning
        stagematrix = getattr(config.calibration, f'stagematrix_{mode}')[magnification]
        self.stagematrix = np.array(stagematrix).reshape(2, 2) / (1000 * binning)  # um -> nm

        self.mode = mode
        self.magnification = magnification

    def get_difference_vector(self,
                              idx0: int,
                              idx1: int,
                              shift: list,
                              overlap_k: float = 1.0,
                              verbose: bool = False,
                              ) -> list:
        """Calculate the pixel distance between 2 images using the calculate
        pixel shift from cross correlation.

        Parameters
        ----------
        idx0, idx1 : int
            Grid coordinate of im0 and im0, defining their relative position
        shift : list
            The offset between the 2 strips of the images used for cross correlation
        overlap_k : float
            Extend the overlap by this factor, may help with the cross correlation
            For example, if the overlap is 50 pixels, `overlap_k=1.5` will extend the
            strips used for cross correlation to 75 pixels.

        Returns
        -------
        difference_vector : np.array[1,2]
            Vector describing the pixel offset between the 2 images
        """
        res_x, res_y = self.image_shape
        overlap_x = int(self.overlap_x * overlap_k)
        overlap_y = int(self.overlap_y * overlap_k)

        vect = np.array(idx1) - np.array(idx0)
        vect = vect * np.array((res_x - overlap_x, res_y - overlap_y))

        difference_vector = vect + shift

        if verbose:
            print(f'Vector from indices: {vect}')
            print(f'Shift: {shift}')
            print(f'Difference vector: {difference_vector}')

        return difference_vector

    def calculate_difference_vectors(self,
                                     threshold: float = 'auto',
                                     overlap_k: float = 1.0,
                                     method: str = 'imreg',
                                     segment: bool = False,
                                     plot: bool = False,
                                     verbose: bool = True,
                                     ) -> dict:
        """Get the difference vectors between the neighbouring images The
        images are overlapping by some amount defined using `overlap`. These
        strips are compared with cross correlation to calculate the shift
        offset between the images.

        Parameters
        ----------
        threshold : float
            Lower for the cross correlation score to accept a shift or not
            If a shift is not accepted, the shift is set to (0, 0). Use the value 'auto' to automatically determine the threshold value. The threshold can be visualized using `.plot_fft_scores()`.
        overlap_k : float
            Extend the overlap by this factor, may help with the cross correlation
            For example, if the overlap is 50 pixels, `overlap_k=1.5` will extend the
            strips used for cross correlation to 75 pixels.
        segment : bool
            Segment the image using otsu's method before cross correlation. This improves
            the contrast for registration.
        method : str
            Which cross correlation function to use `skimage`/`imreg`. `imreg` seems
            to perform slightly better in this scenario.
        verbose : bool
            Be more verbose

        Returns
        -------
        difference_vectors : dict
            Dictionary with the pairwise shifts between the neighbouring
            images
        """
        grid = self.grid
        res_x, res_y = self.image_shape
        images = self.images

        overlap_x = int(self.overlap_x * overlap_k)
        overlap_y = int(self.overlap_y * overlap_k)

        pairs = define_pairs(grid)
        pairs = define_directions(pairs)

        self.pairs = pairs

        slices = make_slices(overlap_x, overlap_y)

        self.slices = slices

        results = {}

        for i, pair in enumerate(tqdm(pairs)):
            seq0 = pair['seq0']
            seq1 = pair['seq1']

            side0 = pair['side0']
            side1 = pair['side1']
            idx0 = pair['idx0']
            idx1 = pair['idx1']
            im0 = images[seq0]
            im1 = images[seq1]

            if plot and False:
                plot_images(im0, im1, seq0, seq1, side0, side1, idx0, idx1)

            # If the pair of images has already been compared, copy that result instead
            if (seq1, seq0) in results:
                result = results[seq1, seq0]
                shift = -result['shift']
                score = result['fft_score']
            else:
                strip0 = im0[slices[side0]]
                strip1 = im1[slices[side1]]

                if segment:
                    t0 = filters.threshold_otsu(strip0)
                    t1 = filters.threshold_otsu(strip1)
                    strip0 = strip0 > t0
                    strip1 = strip1 > t1
                    # print(f"Thresholds: {t1} {t1}")

                if method == 'imreg':
                    shift, fft = translation(strip0, strip1, return_fft=True)
                    score = fft.max()
                else:  # method = skimage.feature.register_translation
                    shift, error, phasediff = register_translation(strip0, strip1, return_error=True)
                    fft = np.ones_like(strip0)
                    score = 1 - error

                if plot:
                    plot_fft(strip0, strip1, shift, fft, side0, side1)

            shift = disambiguate_shift(strip0, strip1, shift, verbose=False)
            shift = np.array(shift)

            results[seq0, seq1] = {
                'shift': shift,
                'idx0': idx0,
                'idx1': idx1,
                'overlap_k': overlap_k,
                'fft_score': np.nan_to_num(score, nan=0.0),
            }

            # if plot:
            #     plot_shifted(im0, im1, difference_vector, seq0, seq1, idx0, idx1, res_x, res_y)

        self.raw_difference_vectors = results

        difference_vectors = self.filter_difference_vectors(threshold=threshold,
                                                            verbose=verbose)

        self.difference_vectors = difference_vectors

        return difference_vectors

    def filter_difference_vectors(self, threshold: float = 'auto', verbose: bool = True) -> dict:
        """Filter the raw difference vectors based on their fft scores.

        Parameters
        ----------
        threshold : float
            Lower for the cross correlation score to accept a shift or not
            If a shift is not accepted, the shift is set to (0, 0). Use the value 'auto' to automatically determine the threshold value. The threshold can be visualized using `.plot_fft_scores()`.
        verbose : bool
            Be more verbose
        """
        results = self.raw_difference_vectors

        if threshold == 'auto':
            scores = [item['fft_score'] for item in results.values()]
            threshold = find_threshold(scores)

        self.fft_threshold = threshold

        out = {}
        for i, (key, item) in enumerate(results.items()):
            score = item['fft_score']
            seq0, seq1 = key
            idx0 = item['idx0']
            idx1 = item['idx1']
            overlap_k = item['overlap_k']

            if score < threshold:
                shift = np.array((0, 0))
                if verbose:
                    print(f'Pair {seq0:2d}:{idx0} - {seq1:2d}:{idx1} -> S: {score:.4f} -> Below threshold!')
            else:
                shift = item['shift']
                if verbose:
                    print(f'Pair {seq0:2d}:{idx0} - {seq1:2d}:{idx1} -> S: {score:.4f} -> Shift: {shift}')

            difference_vector = self.get_difference_vector(idx0, idx1, shift, overlap_k=overlap_k, verbose=False)
            out[seq0, seq1] = difference_vector

        return out

    def plot_fft_scores(self) -> None:
        """Plot the distribution of fft scores for the cross correlation."""
        scores = [item['fft_score'] for item in self.raw_difference_vectors.values()]
        auto_thresh = find_threshold(scores)
        used_thresh = self.fft_threshold
        plt.axhline(auto_thresh, lw=0.5, color='red', label=f'Suggested threshold={auto_thresh:.4f}')
        plt.axhline(used_thresh, lw=0.5, color='green', label=f'Actual threshold={used_thresh:.4f}')
        plt.plot(sorted(scores), '.')
        plt.title('FFT scores')
        plt.xlabel('Index')
        plt.ylabel('Score')
        plt.legend()
        plt.show()

    def calculate_montage_coords(self) -> list:
        """Get the coordinates for each section based on the gridspec only (not
        optimized)

        Returns
        -------
        coords : np.array[-1, 2]
            Coordinates for each section in the montage map
        """

        res_x, res_y = self.image_shape
        grid = self.grid

        overlap_x = self.overlap_x
        overlap_y = self.overlap_y

        # make starting values
        vect = np.array((res_x - overlap_x, res_y - overlap_y))
        vects = []

        for i, idx in enumerate(sorted_grid_indices(grid)):
            x0, y0 = vect * idx
            vects.append((x0, y0))

        vects = np.array(vects)

        self.coords = vects

        return vects

    def optimize_montage_coords(self,
                                method: str = 'leastsq',
                                verbose: bool = False,
                                ) -> list:
        """Use the difference vectors between each pair of images to calculate
        the optimal coordinates for each section using least-squares
        minimization.

        Parameters
        ----------
        method : str
            Least-squares minimization method to use (lmfit)
        verbose : bool
            Be more verbose

        Returns
        -------
        coords : np.array[-1, 2]
            Optimized coordinates for each section in the montage map
        """
        if not hasattr(self, 'coords'):
            self.calculate_montage_coords()
        vects = self.coords

        difference_vectors = self.difference_vectors

        res_x, res_y = self.image_shape
        grid = self.grid
        grid_x, grid_y = grid.shape
        n_gridpoints = grid_x * grid_y

        # determine which frames items have neighbours
        has_neighbours = {i for key in difference_vectors.keys() for i in key}

        # setup parameters
        params = lmfit.Parameters()

        middle_i = int(n_gridpoints / 2)  # Find index of middlemost item
        for i, row in enumerate(vects):
            if i not in has_neighbours:
                vary = False
            else:
                vary = (i != middle_i)  # anchor on middle frame
            params.add(f'C{i}{0}', value=row[0], vary=vary, min=row[0] - res_x / 2, max=row[0] + res_x / 2)
            params.add(f'C{i}{1}', value=row[1], vary=vary, min=row[1] - res_y / 2, max=row[1] + res_y / 2)

        def obj_func(params, diff_vects):
            V = np.array([p.value for p in params.values()]).reshape(-1, 2)
            n = len(V)

            # Minimization function from 2.2
            new = []
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    if not (i, j) in diff_vects:
                        continue

                    diffij = diff_vects[i, j]

                    x = V[j] - V[i] - diffij

                    new.append(x)

            return np.array(new)

        args = (difference_vectors,)
        res = lmfit.minimize(obj_func, params, args=args, method=method)

        lmfit.report_fit(res, show_correl=verbose, min_correl=0.8)

        Vn = np.array([p.value for p in res.params.values()]).reshape(-1, 2)
        offset = min(Vn[:, 0]), min(Vn[:, 1])
        coords = Vn - offset

        self.optimized_coords = coords

        return coords

    def _montage_patches(self, coords, binning=1):
        montage_patches = []
        for i, coord in enumerate(coords):
            image = self.images[i]
            patch = MontagePatch(image, coord, binning=binning)
            montage_patches.append(patch)
        return montage_patches

    def stitch(self,
               method: str = None,
               binning: int = 1,
               optimized: bool = True):
        """Stitch the images together using the given list of pixel coordinates
        for each section.

        Parameters
        ----------
        coords : np.array[-1, 2]
            List of x/y pixel coordinates
        binning : int
            Bin the Montage image by this factor
        optimized : bool
            Use optimized coordinates if they are available [default = True]

        Return
        ------
        stitched : np.array
            Stitched image
        """
        if optimized:
            try:
                coords = self.optimized_coords
            except AttributeError:
                coords = self.coords
        else:
            coords = self.coords

        grid = self.grid
        images = self.images
        nx, ny = grid.shape
        res_x, res_y = self.image_shape

        c = coords.astype(int)
        stitched_x, stitched_y = c.max(axis=0) - c.min(axis=0)
        stitched_x += res_x
        stitched_y += res_y

        stitched = np.zeros((int(stitched_x / binning),
                             int(stitched_y / binning)),
                            dtype=np.int32)

        if method in ('average', 'weighted'):
            n_images = np.zeros_like(stitched)

            if method == 'weighted':
                weight = weight_map(stitched.shape, method='circle')

        montage_patches = self._montage_patches(coords, binning=binning)
        for i, patch in enumerate(montage_patches):
            im = patch.image
            x0 = patch.x0
            y0 = patch.y0
            x1 = patch.x1
            y1 = patch.y1

            if method == 'average':
                stitched[x0:x1, y0:y1] += im
                n_images[x0:x1, y0:y1] += 1
            if method == 'weighted':
                stitched[x0:x1, y0:y1] += im * weight
                n_images[x0:x1, y0:y1] += weight
            else:
                stitched[x0:x1, y0:y1] = im

        if method in ('average', 'weighted'):
            n_images = np.where(n_images == 0, 1, n_images)
            stitched /= n_images

        self.stitched = stitched
        self.centers = coords + np.array((res_x, res_y)) / 2
        self.stitched_binning = binning
        self.montage_patches = montage_patches

        return stitched

    def plot(self, ax=None, vmax: int = None):
        """Plots the stitched image.

        Parameters
        ----------
        ax : matplotlib.Axis
            Matplotlib axis to plot on.
        """
        stitched = self.stitched

        if not ax:
            fig, ax = plt.subplots(figsize=(10, 10))

        grid = self.grid
        indices = sorted_grid_indices(grid)
        montage_patches = self.montage_patches
        for i, patch in enumerate(montage_patches):
            idx = indices[i]
            txt = f'{i}\n{idx}'

            # NOTE that y/x are flipped for display in matplotlib ONLY
            ax.text((patch.y0 + patch.y1) / 2,
                    (patch.x0 + patch.x1) / 2,
                    txt,
                    color='red',
                    fontsize=18,
                    ha='center',
                    va='center',
                    )
            rect = patches.Rectangle([patch.y0, patch.x0],
                                     patch.res_x,
                                     patch.res_y,
                                     linewidth=0.5,
                                     edgecolor='r',
                                     facecolor='none',
                                     )
            ax.add_patch(rect)

        ax.imshow(stitched, vmax=vmax)
        ax.set_title('Stitched image')

        if not ax:
            plt.show()
        else:
            return ax

    def pixel_to_stagecoord(self,
                            px_coord: tuple,
                            stagematrix=None,
                            plot=False,
                            ) -> tuple:
        """Takes a pixel coordinate and transforms it into a stage
        coordinate."""
        if stagematrix is None:
            stagematrix = self.stagematrix

        mati = np.linalg.inv(stagematrix)

        px_coord = np.array(px_coord) * self.stitched_binning
        center_offset = np.dot(np.array(self.image_shape) / 2, mati)

        diffs = np.linalg.norm((self.centers - px_coord), axis=1)
        j = np.argmin(diffs)

        # image_pixel_coord = self.coords[j][::-1]  # FIXME: Why do these coordinates need to be flipped (SerialEM)?
        image_pixel_coord = self.coords[j]  # 2020-01-31: make it work in Python
        image_stage_coord = self.stagecoords[j]

        tx, ty = np.dot(px_coord - image_pixel_coord, mati)  # 2020-01-31: make it work in Python

        stage_coord = np.array((tx, -ty)) + image_stage_coord - center_offset
        stage_coord = stage_coord.astype(int)  # round to integer

        if plot:
            img = self.images[j]
            plt.imshow(img)
            plot_x, plot_y = px_coord - image_pixel_coord
            plt.scatter(plot_y, plot_x, color='red')
            plt.text(plot_y, plot_x, ' P', fontdict={'color': 'red', 'size': 20})
            plt.title(f'Image coord: {image_stage_coord}\nP: {stage_coord}')
            plt.show()

        return stage_coord

    def stage_to_pixelcoord(self,
                            stage_coord: tuple,
                            stagematrix=None,
                            ) -> tuple:
        """Takes a stage coordinate and transforms it into a pixel
        coordinate."""
        if stagematrix is None:
            stagematrix = self.stagematrix

        mat = stagematrix
        mati = np.linalg.inv(stagematrix)

        center_offset = np.dot(np.array(self.image_shape) / 2, mati)
        stage_coord = np.array(stage_coord)

        diffs = np.linalg.norm((self.stagecoords - stage_coord), axis=1)
        j = np.argmin(diffs)

        image_stage_coord = self.stagecoords[j]
        image_pixel_coord = self.coords[j][::-1]  # FIXME: Why do these coordinates need to be flipped (SerialEM)?

        # The image pixel coordinate `image_pixel_coord` cooresponds to the corner,
        # but the stage coord `image_stage_coord` at the center of the image.
        # `px_coord` is the relative offset added to the corner pixel coordiante of the image
        px_coord = np.dot(stage_coord - image_stage_coord + center_offset, mat) + image_pixel_coord
        px_coord /= self.stitched_binning

        return px_coord.astype(int)

    def find_holes(self,
                   diameter: float = 40e3,
                   tolerance: float = 0.1,
                   pixelsize: float = None,
                   plot: bool = False,
                   ) -> tuple:
        """Find grid holes in the montage image.

        Parameters
        ----------
        diameter : float
            In nm, approximate diameter of squares/grid holes
        tolerance : float
            Tolerance in % how far the calculate diameter can be off
        pixelsize : float
            Unbinned tile pixelsize in nanometers
        plot : bool
            Plot the segmentation results and coordinates using Matplotlib

        Returns
        -------
        stagecoords : np.array, imagecoords : np.array
            Return both he stage and imagecoords as numpy arrays
        """
        from skimage import filters
        from skimage import morphology
        from skimage.measure import regionprops

        stitched = self.stitched

        thresh = filters.threshold_otsu(stitched)
        selem = morphology.disk(10)
        seg = morphology.binary_closing(stitched > thresh, selem=selem)

        labeled, _ = ndimage.label(seg)
        props = regionprops(labeled)

        binning = self.stitched_binning

        if not pixelsize:
            pixelsize = self.pixelsize * binning
        else:
            pixelsize *= binning

        max_val = tolerance * diameter

        stagecoords = []
        imagecoords = []

        allds = []  # all diameters
        selds = []  # selected diameters

        for prop in props:
            x, y = prop.centroid

            d = (prop.area ** 0.5) * pixelsize
            allds.append(d)

            if abs(d - diameter) < max_val:
                stagecoord = self.pixel_to_stagecoord((x, y))
                stagecoords.append(stagecoord)
                imagecoords.append((x, y))
                selds.append(d)

        stagecoords = np.array(stagecoords)
        imagecoords = np.array(imagecoords)

        if plot:
            fig, (ax0, ax1, ax2) = plt.subplots(ncols=3, figsize=(12, 4))

            ax0.set_title('Segmentation')
            ax0.imshow(seg)

            ax1.set_title('Image coords')
            ax1.imshow(stitched)

            plot_x, plot_y = np.array(imagecoords).T
            ax1.scatter(plot_y, plot_x, marker='+', color='r')

            ax2.set_title('Stage coords')
            plot_x, plot_y = np.array(stagecoords).T
            ax2.scatter(-plot_y / 1000, -plot_x / 1000)  # fiddle with coordinates to match the layout with the other axes

        prc = np.percentile
        mdn = np.median
        print(f'All hole diameters     50%: {mdn(allds):6.0f} | 5%: {prc(allds, 5):6.0f} | 95%: {prc(allds, 95):6.0f}')
        print(f'Selected hole diameter 50%: {mdn(selds):6.0f} | 5%: {prc(selds, 5):6.0f} | 95%: {prc(selds, 95):6.0f}')

        return stagecoords, imagecoords


if __name__ == '__main__':
    pass
