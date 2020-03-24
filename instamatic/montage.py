from pathlib import Path

import lmfit
import matplotlib.pyplot as plt
import mrcfile
import numpy as np
from matplotlib import patches
from scipy import ndimage
from skimage import filters
from skimage.feature import register_translation
from tqdm.auto import tqdm

from instamatic import config
from instamatic.config import defaults
from instamatic.image_utils import bin_ndarray
from instamatic.imreg import translation


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


def make_grid(gridshape: tuple,
              direction: str = 'updown',
              zigzag: bool = True,
              flip: bool = False,
              ) -> 'np.array':
    """Defines the grid montage collection scheme.

    Parameters
    ----------
    gridshape : tuple(int, int)
        Defines the shape of the grid
    direction : str
        Defines the direction of data collection starting from the top (lr, rl)
        or left-hand (ud, du) side `updown`, `downup`, `leftright`, `rightleft`
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

    assert strip0.shape == strip1.shape, f'Shapes do not match, strip1: {strip1.shape} strip2: {strip2.shape}'
    shape = strip0.shape

    if shape[0] > shape[1]:
        strip0 = strip0.T
        strip1 = strip1.T
        fft = fft.T
        t1, t0 = shift
    else:
        t0, t1 = shift

    # Show difference
    strip1_shifted = ndimage.shift(strip1, (t0, t1))
    difference = strip1_shifted - strip0.astype(float)

    ax0.imshow(strip0, interpolation='nearest')
    ax0.set_title(f'{side0}')
    ax1.imshow(strip1, interpolation='nearest')
    ax1.set_title(f'{side1}')
    ax2.imshow(difference, interpolation='nearest')
    ax2.set_title(f'Abs(Difference) - Shift: {t0} {t1}')
    ax3.imshow(fft, vmin=np.percentile(fft, 90.0), vmax=np.percentile(fft, 99.99))
    ax3.set_title(f'Cross correlation (max={fft.max():.4f})')

    if t0 < 0:
        t0 += shape[0]
    if t1 < 0:
        t1 += shape[0]

    ax3.scatter(t1, t0, color='red', marker='o', facecolor='none', s=100)
    ax3.set_xlim(0, fft.shape[1])
    ax3.set_ylim(0, fft.shape[0])

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
                 **kwargs,
                 ):
        super().__init__()

        self.images = images
        self.image_shape = images[0].shape
        self.gridspec = gridspec
        self.grid = make_grid(**gridspec)

        self.__dict__.update(**kwargs)

        res_x, res_y = self.image_shape
        self.overlap_x = int(res_x * overlap)
        self.overlap_y = int(res_y * overlap)

    @classmethod
    def from_serialem_mrc(cls,
                          filename: str,
                          gridshape: tuple,
                          direction: str = defaults.montage['from_serialem_mrc']['direction'],
                          zigzag: bool = defaults.montage['from_serialem_mrc']['zigzag'],
                          flip: bool = defaults.montage['from_serialem_mrc']['flip'],
                          image_rot90: int = defaults.montage['from_serialem_mrc']['rot90'],
                          image_flipud: bool = defaults.montage['from_serialem_mrc']['flipud'],
                          image_fliplr: bool = defaults.montage['from_serialem_mrc']['fliplr'],
                          ):
        """Load a montage object from a SerialEM file image stack. The default
        parameters transform the images to data suitable for use with
        Instamatic. It makes no further assumptions about the way the data were
        collected.

        The parameters image_rot90/image_flipud/image_fliplr manipulate the images in this order, so they can look the same as when collected with Instamatic. This is necessary to use the stage calibration, which is not specified in the SerialEM mrc file.

        Use .set_calibration(mode, mag) to set the correct stagematrix, or specify the one from SerialEM.

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
        flip : bool
            Flip around the vertical (lr, rl) or horizontal (ud, du) axis,
            i.e. start from the botton (lr, rl) or right-hand (ud, du) side.
        image_rot90 : int
            Rotate the image by 90 degrees (clockwise) for this times, i.e.,
            `image_rot90=3` rotates the image by 270 degrees.
        image_flipud:
            Flip the images around the horizintal axis.
        image_fliplr:
            Flip the images around the vertical axis. The


        Returns
        -------
        Montage object constructed from the given images
        """
        from instamatic.serialem import read_mdoc_file
        filename = str(filename)  # in case of Path object

        gm = mrcfile.open(filename)
        images = gm.data

        mdoc = read_mdoc_file(filename + '.mdoc', only_kind='zvalue')
        assert len(mdoc) == len(images)

        gridspec = {
            'gridshape': gridshape,
            'direction': direction,
            'zigzag': zigzag,
            'flip': flip,
        }

        # Rotate the images so they are in the same orientation as those from Instamatic
        if image_rot90:
            images = [np.rot90(image, k=image_rot90) for image in images]
        if image_flipud:
            images = [np.flipud(image) for image in images]
        if image_fliplr:
            images = [np.fliplr(image) for image in images]

        kwargs = {
            'stagecoords': np.array([d['StagePosition'] for d in mdoc]) * 1000,  # um->nm
            'magnifiation': mdoc[-1]['Magnification'],
            'image_binning': mdoc[-1]['Binning'],
            'software': 'serialem',
            'abs_mag_index': mdoc[-1]['MagIndex'],
            'mdoc': mdoc,
            'filename': filename,
        }

        m = cls(images=images, gridspec=gridspec, **kwargs)

        c1 = np.array([d['PieceCoordinates'][0:2] for d in mdoc])

        def convert_coords(c,
                           rot90=image_rot90,
                           flipud=image_flipud,
                           fliplr=image_fliplr,
                           ):
            # SerialEM uses a different convention for X/Y
            c = np.fliplr(c)

            angle = np.radians(image_rot90 * 90)
            R = np.array([np.cos(angle), -np.sin(angle), np.sin(angle), np.cos(angle)]).reshape(2, 2)

            c = np.dot(c, R)

            if flipud:
                c[:, 1] *= -1
            if fliplr:
                c[:, 0] *= -1

            c -= c.min(axis=0)

            return c

        # Apparently, SerialEM can save one or the other or both
        # prefer APCVS over APC and move on
        for key in 'AlignedPieceCoordsVS', 'AlignedPieceCoords':
            if key in mdoc[0]:
                c2 = np.array([d[key][0:2] for d in mdoc])
                break

        m.coords = convert_coords(c1)
        m.optimized_coords = convert_coords(c2)

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

        d['stagecoords'] = np.array(d['stagecoords'])
        d['stagematrix'] = np.array(d['stagematrix'])

        images = [read_tiff(fn)[0] for fn in fns]

        gridspec = {k: v for k, v in d.items() if k in ('gridshape', 'direction', 'zigzag', 'flip')}

        m = cls(images=images, gridspec=gridspec, **d)
        m.update_gridspec(flip=not d['flip'])  # BUG: Work-around for gridspec madness
        # Possibly related is that images are rotated 90 deg. in SerialEM mrc files

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
        self.pixelsize = config.calibration[mode]['pixelsize'][magnification]

        image_binning = self.image_binning
        stagematrix = config.calibration[mode]['stagematrix'][magnification]
        self.stagematrix = np.array(stagematrix).reshape(2, 2) * image_binning

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
                                     max_shift: int = 200,
                                     method: str = 'skimage',
                                     segment: bool = False,
                                     plot: bool = False,
                                     verbose: bool = False,
                                     ) -> dict:
        """Get the difference vectors between the neighbouring images The
        images are overlapping by some amount defined using `overlap`. These
        strips are compared with cross correlation to calculate the shift
        offset between the images.

        Parameters
        ----------
        threshold : float
            Lower for the cross correlation score to accept a shift or not
            If a shift is not accepted, the shift is set to (0, 0).
            Use the value 'auto' to automatically determine the threshold value.
            The threshold can be visualized using `.plot_fft_scores()`.
        overlap_k : float
            Extend the overlap by this factor, may help with the cross correlation
            For example, if the overlap is 50 pixels, `overlap_k=1.5` will extend the
            strips used for cross correlation to 75 pixels.
        max_shift : int
            Maximum pixel shift for difference vector to be accepted.
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
                if verbose:
                    print(f'{seq0:3d}{seq1:3d} | copy')
                result = results[seq1, seq0]
                shift = -result['shift']
                score = result['fft_score']
            else:
                if verbose:
                    print(f'{seq0:3d}{seq1:3d} | fft')
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
                    score = 1 - error**0.5

                if plot:
                    plot_fft(strip0, strip1, shift, fft, side0, side1)

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
                                                            verbose=verbose,
                                                            max_shift=max_shift)

        self.difference_vectors = difference_vectors
        self.weights = {k: v['fft_score'] for k, v in results.items()}

        return difference_vectors

    def filter_difference_vectors(self,
                                  threshold: float = 'auto',
                                  max_shift: int = 200,
                                  verbose: bool = True,
                                  plot: bool = True,
                                  ) -> dict:
        """Filter the raw difference vectors based on their fft scores.

        Parameters
        ----------
        threshold : float
            Lower for the cross correlation score to accept a shift or not
            If a shift is not accepted, the shift is set to (0, 0).
            Use the value 'auto' to automatically determine the threshold value.
            The threshold can be visualized using `.plot_fft_scores()`.
        max_shift : int
            Maximum pixel shift for difference vector to be accepted.
        verbose : bool
            Be more verbose
        plot : bool
            Plot the difference vectors
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
            shift = item['shift']
            include = False

            if score < threshold:
                new_shift = np.array((0, 0))
                msg = '-> Below threshold!'
            elif np.linalg.norm(shift) > max_shift:
                new_shift = np.array(0.0)
                msg = '-> Too large!'
            else:
                new_shift = item['shift']
                msg = '-> :-)'
                include = True

            if verbose:
                t0, t1 = shift
                print(f'Pair {seq0:2d}:{idx0} - {seq1:2d}:{idx1} -> S: {score:.4f} -> Shift: {t0:4} {t1:4} {msg}')

            if include:
                out[seq0, seq1] = self.get_difference_vector(idx0,
                                                             idx1,
                                                             new_shift,
                                                             overlap_k=overlap_k,
                                                             verbose=False)

        return out

    def plot_shifts(self) -> None:
        """Plot the pixel shifts from the cross correlation."""
        shifts = np.array([item['shift'] for item in self.raw_difference_vectors.values()])
        scores = np.array([item['fft_score'] for item in self.raw_difference_vectors.values()])
        t0, t1 = shifts.T
        plt.scatter(t0, t1, c=scores, marker='+')
        plt.xlabel('Shift X (px)')
        plt.ylabel('Shift Y (px)')
        plt.title('Pixel shifts (color = FFT score)')
        plt.axis('equal')
        plt.colorbar()
        plt.show()

    def plot_fft_scores(self) -> None:
        """Plot the distribution of fft scores for the cross correlation."""
        scores = [item['fft_score'] for item in self.raw_difference_vectors.values()]
        shifts = np.array([item['shift'] for item in self.raw_difference_vectors.values()])
        amplitudes = np.linalg.norm(shifts, axis=1)
        auto_thresh = find_threshold(scores)
        used_thresh = self.fft_threshold
        plt.axhline(auto_thresh, lw=0.5, color='red', label=f'Suggested threshold={auto_thresh:.4f}')
        plt.axhline(used_thresh, lw=0.5, color='green', label=f'Actual threshold={used_thresh:.4f}')
        plt.scatter(np.arange(len(scores)), sorted(scores), c=amplitudes, marker='.')
        plt.colorbar()
        plt.title('FFT scores (color = pixel shift)')
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
                                skip: tuple = (),
                                verbose: bool = False,
                                plot: bool = False,
                                ) -> list:
        """Use the difference vectors between each pair of images to calculate
        the optimal coordinates for each section using least-squares
        minimization.

        Parameters
        ----------
        method : str
            Least-squares minimization method to use (lmfit)
        skip : tuple
            List of integers of frames to ignore
        verbose : bool
            Be more verbose
        plot : bool
            Plot the original and optimized pixel coordinates

        Returns
        -------
        coords : np.array[-1, 2]
            Optimized coordinates for each section in the montage map
        """
        if not hasattr(self, 'coords'):
            self.calculate_montage_coords()
        vects = self.coords

        difference_vectors = self.difference_vectors
        weights = self.weights

        res_x, res_y = self.image_shape
        grid = self.grid
        grid_x, grid_y = grid.shape
        n_gridpoints = grid_x * grid_y

        # determine which frames items have neighours
        has_neighbours = {i for key in difference_vectors.keys() for i in key}

        # setup parameters
        params = lmfit.Parameters()

        middle_i = int(n_gridpoints / 2)  # Find index of middlemost item
        for i, row in enumerate(vects):
            if i in skip:
                vary = False
            elif i not in has_neighbours:
                vary = False
            else:
                vary = (i != middle_i)  # anchor on middle frame
            params.add(f'C{i}{0}', value=row[0], vary=vary, min=row[0] - res_x / 2, max=row[0] + res_x / 2)
            params.add(f'C{i}{1}', value=row[1], vary=vary, min=row[1] - res_y / 2, max=row[1] + res_y / 2)

        def obj_func(params, diff_vects, weights):
            V = np.array([v.value for k, v in params.items() if k.startswith('C')]).reshape(-1, 2)

            # Minimization function from 2.2
            out = []
            for i, j in diff_vects.keys():
                if i in skip:
                    continue
                if j in skip:
                    continue

                diffij = diff_vects[i, j]
                x = V[j] - V[i] - diffij
                weight = weights[i, j]
                out.append(x * weight)

            return np.array(out)

        args = (difference_vectors, weights)
        res = lmfit.minimize(obj_func, params, args=args, method=method)

        lmfit.report_fit(res, show_correl=verbose, min_correl=0.8)

        params = res.params
        Vn = np.array([v.value for k, v in params.items() if k.startswith('C')]).reshape(-1, 2)

        offset = min(Vn[:, 0]), min(Vn[:, 1])
        coords = Vn - offset

        self.optimized_coords = coords

        if plot:
            # center on average coordinate to better show displacement
            c1 = self.coords - np.mean(self.coords, axis=0)
            c2 = self.optimized_coords - np.mean(self.optimized_coords, axis=0)
            plt.title(f'Shifts from minimization (`{method}`)\nCentered on average position')
            plt.scatter(*c1.T, label='Original', marker='+')
            plt.scatter(*c2.T, label='Optimized', marker='+')
            # for (x1,y1), (x2, y2) in zip(m.coords, m.optimized_coords):
            #     arrow = plt.arrow(x1, x2, x2-x1, y2-y1)
            plt.axis('equal')
            plt.legend()

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
        method : str
            Choices: [None, 'weighted', 'average']
            With `weighted`, the intensity contribution is weighted by
            the distance from the center of the image. With 'average',
            the images are averaged, and 'None' simply places the patches
            in sequential order, overwriting previous data.
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
                            dtype=np.float32)

        if method in ('average', 'weighted'):
            n_images = np.zeros_like(stitched)

            if method == 'weighted':
                weight = weight_map((int(res_x / binning),
                                     int(res_y / binning)),
                                    method='circle')

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
            elif method == 'weighted':
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

    def plot(self, ax=None, vmax: int = None, labels: bool = True):
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

            if labels:
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

    def export(self, outfile: str = 'stitched.tiff') -> None:
        """Export the stitched image to a tiff file.

        Parameters
        ----------
        outfile : str
            Name of the image file.
        """
        from instamatic.formats import write_tiff
        write_tiff(outfile, self.stitched)

    def to_nav(self,
               fn: str = 'stitched.nav',
               coords: list = None,
               kind: str = 'pixel'):
        """Write montage to a SerialEM .nav file.
        NOTE: The stage coordinates in the .nav file are not reliable.

        Parameters
        ----------
        coords : np.array
            List of pixel / stagecoords
        kind : str
            Specify whether the coordinates are pixel or stage coordinates,
            must be one of `pixel` or `stage`.

        Returns
        -------
        map_item : `MapItem`
            Map item corresponding to the stitched image. Any coords
            specified are accessed as a dict of markers
            through `map_item.markers`.
        """
        from instamatic.serialem import MapItem, write_nav_file

        stem = fn.rsplit('.', 1)[-1]
        fn_mrc = stem + '.mrc'
        f = mrcfile.new(fn_mrc, data=self.stitched, overwrite=True)
        f.close()

        map_scale_mat = np.linalg.inv(self.stagematrix)

        d = {
            'StageXYZ': [0, 0, 0],
            'MapFile': fn_mrc,
            'MapSection': 0,
            'MapBinning': self.image_binning,
            'MapMagInd': self.abs_mag_index,
            'MapScaleMat': map_scale_mat.flatten().tolist(),
            'MapWidthHeight': self.stitched.shape,
        }

        map_item = MapItem.from_dict(d)

        if coords is not None:
            markers = map_item.add_marker_group(coords, kind=kind)

        write_nav_file(fn, map_item, *map_item.markers.values())

        return map_item

    def pixel_to_stagecoord(self,
                            px_coord: tuple,
                            stagematrix=None,
                            plot=False,
                            ) -> 'np.array':
        """Takes a pixel coordinate and transforms it into a stage coordinate.

        Parameters
        ----------
        stage_coords : np.array (nx2)
            List of stage coordinates in nm.
        stagematrix : np.array (2x2)
            Stage matrix to convert from pixel to stage coordinates
        plot : bool
            Visualize the pixelcoordinates on the stitched images

        Returns
        -------
        np.array (nx2)
            Stage coordinates (nm) corresponding to pixel coordinates
            given in the stitched image.
        """
        if stagematrix is None:
            stagematrix = self.stagematrix

        stagematrix = self.stagematrix

        px_coord = np.array(px_coord) * self.stitched_binning
        cx, cy = np.dot(np.array(self.image_shape) / 2, stagematrix)

        diffs = np.linalg.norm((self.centers - px_coord), axis=1)
        j = np.argmin(diffs)

        image_pixel_coord = self.coords[j]
        image_stage_coord = self.stagecoords[j]

        tx, ty = np.dot(px_coord - image_pixel_coord, stagematrix)

        stage_coord = np.array((tx, ty)) + image_stage_coord - np.array((cx, cy))
        stage_coord = stage_coord.astype(int)  # round to integer

        if plot:
            img = self.images[j]
            plt.imshow(img)
            plot_x, plot_y = px_coord - image_pixel_coord
            plt.scatter(plot_y, plot_x, color='red')
            plt.text(plot_y, plot_x, ' P', fontdict={'color': 'red', 'size': 20})
            plt.title(f'Image coord: {image_stage_coord}\nP: {stage_coord}\nLinked to: {j}')
            plt.show()

        return stage_coord

    def pixel_to_stagecoords(self, pixelcoords, stagematrix=None, plot: bool = False):
        """Convert a list of pixel coordinates into stage coordinates. Uses
        `.pixel_to_stagecoord`

        Parameters
        ----------
        pixel_coords : np.array (nx2)
            List of pixel coordinates.
        stagematrix : np.array (2x2)
            Stage matrix to convert from pixel to stage coordinates
        plot : bool
            Visualize the pixelcoordinates on the stitched images

        Returns
        -------
        stage_coords : np.array (nx2)
            stage coordinates corresponding to the given pixel coordinates on the stitched image.
        """
        if stagematrix is None:
            stagematrix = self.stagematrix

        f = self.pixel_to_stagecoord
        stage_coords = np.array([f(px_coord, stagematrix=stagematrix) for px_coord in pixelcoords])

        if plot:
            plot_x, plot_y = px_coords.T
            plt.scatter(plot_x, plot_y, color='red', marker='.')
            plt.title(f'Stage coordinates')
            plt.xlabel('X (nm)')
            plt.xlabel('Y (nm)')
            plt.show()

        return stage_coords

    def stage_to_pixelcoord(self,
                            stage_coord: tuple,
                            stagematrix=None,
                            plot: bool = False,
                            ) -> 'np.array':
        """Takes a stage coordinate and transforms it into a pixel coordinate.

        Note that this is not the inverse of `.pixel_to_stagecoord`, as this function
        finds the closest image to 'hook onto', and calculates the pixel coordinate
        with that image as the reference position.

        Parameters
        ----------
        stage_coords : np.array (nx2)
            List of stage coordinates in nm.
        stagematrix : np.array (2x2)
            Stage matrix to convert from pixel to stage coordinates
        plot : bool
            Visualize the pixelcoordinates on the stitched images

        Returns
        -------
        px_cord : np.array (1x2)
            Pixel coordinates corresponding to the stitched image.
        """
        if stagematrix is None:
            stagematrix = self.stagematrix

        mat = stagematrix
        mati = np.linalg.inv(stagematrix)

        center_offset = np.dot(np.array(self.image_shape) / 2, mat)
        stage_coord = np.array(stage_coord)

        diffs = np.linalg.norm((self.stagecoords - stage_coord), axis=1)
        j = np.argmin(diffs)

        image_stage_coord = self.stagecoords[j]
        image_pixel_coord = self.coords[j].copy()

        # The image pixel coordinate `image_pixel_coord` corresponds to the corner,
        # but the stage coord `image_stage_coord` at the center of the image.
        # `px_coord` is the relative offset added to the corner pixel coordiante of the image
        px_coord = np.dot(stage_coord - image_stage_coord + center_offset, mati) + image_pixel_coord

        px_coord /= self.stitched_binning
        px_coord = px_coord.astype(int)

        if plot:
            plot_x, plot_y = px_coord
            plt.imshow(self.stitched)
            plt.scatter(plot_y, plot_x, color='red', marker='.')
            plt.text(plot_y, plot_x, ' P', fontdict={'color': 'red', 'size': 20})
            plt.title(f'P: {px_coord}\nStage: {stage_coord}\nLinked to: {j}')
            plt.show()

        return px_coord

    def stage_to_pixelcoords(self,
                             stage_coords: tuple,
                             stagematrix=None,
                             plot: bool = False,
                             ) -> 'np.array':
        """Convert a list of stage coordinates into pixelcoordinates. Uses
        `.stage_to_pixelcoord`

        Note that this is not the inverse of `.pixel_to_stagecoord`, as this function
        finds the closest image to 'hook onto', and calculates the pixel coordinate
        with that image as the reference position.

        Parameters
        ----------
        stage_coords : np.array (nx2)
            List of stage coordinates in nm.
        stagematrix : np.array (2x2)
            Stage matrix to convert from pixel to stage coordinates
        plot : bool
            Visualize the pixelcoordinates on the stitched images

        Returns
        -------
        px_coords : np.array (nx2)
            Pixel coordinates corresponding to the stitched image.
        """
        f = self.stage_to_pixelcoord
        px_coords = np.array([f(stage_coord, stagematrix=stagematrix) for stage_coord in stage_coords])

        if plot:
            plot_x, plot_y = px_coords.T
            plt.imshow(self.stitched)
            plt.scatter(plot_y, plot_x, color='red', marker='.')
            plt.title(f'Pixel coordinates mapped on stitched image')
            plt.show()

        return px_coords

    def find_holes(self,
                   diameter: float = None,
                   tolerance: float = 0.1,
                   pixelsize: float = None,
                   plot: bool = False,
                   ) -> tuple:
        """Find grid holes in the montage image.

        Parameters
        ----------
        diameter : float
            In nm, approximate diameter of squares/grid holes. If it
            it is not specified, take the median diameter of all props.
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

        stitched_binning = self.stitched_binning

        if not pixelsize:
            pixelsize = self.pixelsize * stitched_binning
        else:
            pixelsize *= stitched_binning

        if diameter is None:
            diameter = np.median([(prop.area ** 0.5) * pixelsize for prop in props])
            print(f'Diameter: {diameter:.0f} nm')

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

            ax2.set_title('Stage coords')

            try:
                plot_x, plot_y = np.array(imagecoords).T
                ax1.scatter(plot_y, plot_x, marker='+', color='r')
            except ValueError:
                pass

            try:
                plot_x, plot_y = np.array(stagecoords).T
                ax2.scatter(plot_x / 1000, plot_y / 1000, marker='+')
                ax2.scatter(0, 0, marker='+', color='red', label='Origin')
                ax2.legend()
                ax2.axis('equal')
                ax2.set_xlabel('X (μm)')
                ax2.set_ylabel('Y (μm)')
            except ValueError:
                pass

        prc = np.percentile
        mdn = np.median
        print(f'All hole diameters     50%: {mdn(allds):6.0f} | 5%: {prc(allds, 5):6.0f} | 95%: {prc(allds, 95):6.0f}')
        if len(selds) > 0:
            print(f'Selected hole diameter 50%: {mdn(selds):6.0f} | 5%: {prc(selds, 5):6.0f} | 95%: {prc(selds, 95):6.0f}')
        else:
            print(f'Selected hole diameter 50%: {"-":>6s} | 5%: {"-":>6s} | 95%: {"-":>6s}')

        self.feature_coords_stage = stagecoords
        self.feature_coords_image = imagecoords

        return stagecoords, imagecoords

    def to_browser(self):
        from instamatic.browser import Browser
        browser = Browser(self)
        return browser


if __name__ == '__main__':
    pass
