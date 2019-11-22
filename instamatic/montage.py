import numpy as np
import matplotlib.pyplot as plt
from instamatic.imreg import translation
from skimage.feature import register_translation
from scipy import ndimage
import lmfit
from instamatic.tools import bin_ndarray


def sorted_grid_indices(grid):
    """
    Sorts 2d the grid by its values, and returns an array
    with the indices (i.e. np.argsort on 2d arrays)
    https://stackoverflow.com/a/30577520
    """
    return np.dstack(np.unravel_index(np.argsort(grid.ravel()), grid.shape))[0]


def weight_map(shape, method="block", plot=False):
    """Generate a weighting map for the given shape
    
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
    
    a, b = np.meshgrid(np.arange(-c_x, c_x+1), np.arange(-c_y, c_y+1))
    
    if method == "block":
        a2 = c_x - np.abs(a)
        b2 = c_y - np.abs(b)
        
        d = np.min(np.stack((a2, b2)), axis=0)
    elif method == "circle":
        d = corner - np.sqrt(a**2+b**2)
    else:
        raise ValueError(f"No such method: `{method}`")
    
    # scale to 1
    d = d / d.max()

    if plot:
        plt.imshow(d)
    
    return d


def make_grid(gridshape: tuple, direction: str="updown", zigzag: bool=True) -> "np.array":
    """Defines the grid montage collection scheme
    
    Parameters
    ----------
    gridshape : tuple(int, int)
        Defines the shape of the grid
    direction : str
        Defines the direction of data collection
    zigzag : bool
        Defines if the data has been collected in a zigzag manner
    
    Returns
    -------
    np.array
    """
    nx, ny = gridshape
    grid = np.arange(nx * ny).reshape(gridshape)

    if zigzag:
        grid[1::2] = np.fliplr(grid[1::2])

    if direction == "updown":
        pass
    elif direction == "downup":
        grid = np.flipud(grid)
    elif direction == "rightleft":
        grid = grid.T
        grid = np.fliplr(grid)
    elif direction == "leftright":
        grid = grid.T
    else:
        raise ValueError(f"Invalid direction: {direction}")

    return grid


def make_slices(overlap_x: int, overlap_y: int, shape=(512, 512), plot: bool=False) -> dict:
    """Make slices for left/right/top/bottom image
    
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
    s_bottom  = np.s_[-overlap_y:]

    slices = (s_right, s_left, s_top, s_bottom)
    labels = ("right", "left", "top", "bottom")

    d = dict(zip(labels, slices))
    
    if plot:
        fig, axes = plt.subplots(2,2, sharex=True, sharey=True)
        axes = axes.flatten()

        for ax, s_, label in zip(axes, slices, labels):
            arr = np.zeros(shape, dtype=int)
            arr[s_] = 1
            ax.imshow(arr)
            ax.set_title(label)

        plt.show()
    
    return d


def define_directions(pairs: list):
    """Define pairwise relations between indices

    Takes a list of index pair dicts, and determines on which side
    they are overlapping. The dictionary is updated with the keywords
    `side0`/`side1`.
    """
    for pair in pairs:
        i0, j0 = pair["idx0"]
        i1, j1 = pair["idx1"]
        
        # checked 21-11-2019 for 'leftright' config
        if j0 == j1:
            if i1 > i0:
                side0, side1 = "bottom", "top"
            else:
                side0, side1 = "top", "bottom"
        else:
            if j1 > j0:
                side0, side1 = "right", "left"
            else:
                side0, side1 = "left", "right"

        # print(i0, j0, i1, j1, side0, side1)
        
        pair["side0"] = side0
        pair["side1"] = side1
    
    return pairs


def define_pairs(grid: "np.ndarray"):
    """Take a sequence grid and return all pairs of neighbours

    Returns a list of dictionaries containing the indices of the pairs 
    (neighbouring only), and the corresponding sequence numbers (corresponding to the image array)
    """
    nx, ny = grid.shape

    footprint = np.array([[0,1,0],
                          [1,0,1],
                          [0,1,0]])

    shape = np.array(footprint.shape)
    assert shape[0] == shape[1], "Axes must be equal"
    assert shape[0] % 2 == 1,    "Axis length must be odd"
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
                d = dict(
                    seq0 = grid[idx0],
                    seq1 = grid[neighbour],
                    idx0 = idx0,
                    idx1 = neighbour
                )
                pairs.append(d)
    
    return pairs


def plot_images(im0, im1, seq0, seq1, side0, side1, idx0, idx1):
    fig, axes = plt.subplots(ncols=2, figsize=(6,3))
    ax0, ax1 = axes.flatten()
    
    ax0.imshow(im0)
    ax0.set_title(f"{seq0} {idx0} {side0}")
    ax0.set_axis_off()
    ax1.imshow(im1)
    ax1.set_title(f"{seq1} {idx1} {side1}")
    ax1.set_axis_off()
    plt.tight_layout()
    plt.show()


def plot_fft(strip0, strip1, shift, fft, side0, side1):
    fig, axes = plt.subplots(nrows=4, figsize=(8,5))
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
    strip1_offset = ndimage.shift(strip1, (shift_x, shift_y))
    
    # Show shift in fourier space
    image_product = np.fft.fft2(strip0) * np.fft.fft2(strip1).conj()
    cc_image = np.fft.fftshift(np.fft.ifft2(image_product))
        
    ax0.imshow(strip0, interpolation="nearest")
    ax0.set_title(f"{side0}")
    ax1.imshow(strip1, interpolation="nearest")
    ax1.set_title(f"{side1}")
    ax2.imshow(strip1_offset - strip0, interpolation="nearest")
    ax2.set_title("Abs(Difference)")
    ax3.imshow(fft, vmin=np.percentile(fft, 50.00), vmax=np.percentile(fft, 99.99))
    ax3.set_title(f"Cross correlation (max={fft.max():.4f})")
    
    plt.subplots_adjust(hspace=0.0)
    plt.show()


def plot_shifted(im0, im1, difference_vector, seq0, seq1, idx0, idx1, res_x, res_y):
    import matplotlib.patches as patches
    
    blank = np.zeros((res_x*2, res_y*2), dtype=np.int32)

    center = np.array(blank.shape) // 2
    origin = np.array((res_x, res_y)) // 2

    coord0 = (center - difference_vector/2 - origin).astype(int)
    coord1 = (center + difference_vector/2 - origin).astype(int)
    
    print(f"Coord0: {coord0} | Coord1: {coord1}")
    
    txt = f"Difference vector\n#{seq0}:{idx0} -> #{seq1}:{idx1} = {difference_vector}"

    blank[coord0[0]: coord0[0]+res_x, coord0[1]: coord0[1] + res_y] += im0
    blank[coord1[0]: coord1[0]+res_x, coord1[1]: coord1[1] + res_y] += im1

    # Create a Rectangle patch
    rect0 = patches.Rectangle(coord0[::-1], res_x, res_y, linewidth=1, edgecolor='r', facecolor='none')
    rect1 = patches.Rectangle(coord1[::-1], res_x, res_y, linewidth=1, edgecolor='r', facecolor='none')

    fig, ax = plt.subplots(1, figsize=(8,8))

    # Add the patch to the Axes
    ax.add_patch(rect0)
    ax.add_patch(rect1)

    ax.imshow(blank)
    ax.set_title(txt)
    ax.set_axis_off()
    plt.show()


class Montage(object):
    """This class is used to stitch together a set of images to make a larger image

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
                 overlap=0.1
                 ):
        super().__init__()
        
        self.images = images
        self.image_shape = images[0].shape
        self.gridspec = gridspec
        self.grid = make_grid(**gridspec)
        
        res_x, res_y = self.image_shape
        self.overlap_x = overlap_x = int(res_x * overlap)
        self.overlap_y = overlap_y = int(res_y * overlap)
        
    @classmethod
    def from_serialem_mrc(cls, filename: str, gridshape: tuple, direction: str="leftright", zigzag: bool=True):
        """Load a montage object from a SerialEM file image stack
        
        Parameters
        ----------
        filename : str
            Filename of the mrc file to load.
        gridshape : tuple(2)
            Tuple describing the number of of x and y points in the montage grid.
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
        mdoc = read_mdoc_file(filename + ".mdoc", only_kind="zvalue")
        assert len(mdoc) == len(images)
        
        gridspec = {
            "gridshape": gridshape,
            "direction": direction,
            "zigzag": zigzag
        }
        
        m = cls(images=images, gridspec=gridspec)
        m.mdoc = mdoc
        m.filename = filename
        m.stagecoords = np.array([d["StagePosition"] for d in m.mdoc]) * 1000  # um->nm
        m.piececoords = np.array([d["PieceCoordinates"][0:2] for d in m.mdoc])
        m.alignedpiececoords = np.array([d["AlignedPieceCoords"][0:2] for d in m.mdoc])
        try:
            m.alignedpiececoordsvs = np.array([d["AlignedPieceCoordsVS"][0:2] for d in m.mdoc])
        except KeyError:
            pass

        return m

    @classmethod
    def from_montage_yaml(cls, filename: str):
        """Load montage from a series of tiff files + `montage.yaml`)
        """
        import yaml
        from instamatic.formats import read_tiff
        
        d = yaml.safe_load(open("montage.yaml", "r"))
        fns = d["filenames"]
        overlap = d["overlap"]

        images = [read_tiff(fn)[0] for fn in fns]

        gridspec = {k:v for k,v in d.items() if k in ("gridshape", "direction", "zigzag")}

        m = cls(images=images, gridspec=gridspec, overlap=overlap)
        m.stagecoords = np.array(d["stagecoords"])
        m.stagematrix = np.array(d["stagematrix"])

        return m

    def get_difference_vector(self, idx0: int, idx1: int, shift: list, overlap_k: float=1.0, verbose: bool=False):
        """Calculate the pixel distance between 2 images using the calculate
        pixel shift from cross correlation
        
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
            print(f"Vector from indices: {vect}")
            print(f"Shift: {shift}")
            print(f"Difference vector: {difference_vector}")

        return difference_vector
    
    def get_difference_vectors(self, threshold: float=0.02, overlap_k: float=1.0, method: str="skimage", plot : bool=False, verbose : bool=True):
        """Get the difference vectors between the neighbouring images
        The images are overlapping by some amount defined using `overlap`.
        These strips are compared with cross correlation to calculate the
        shift offset between the images.
        
        Parameters
        ----------
        threshold : float
            Lower for the cross correlation score to accept a shift or not
            If a shift is not accepted, the shift is set to (0, 0)
        overlap_k : float
            Extend the overlap by this factor, may help with the cross correlation
            For example, if the overlap is 50 pixels, `overlap_k=1.5` will extend the
            strips used for cross correlation to 75 pixels.
        method : str
            Which cross correlation function to use `skimage`/`imreg`

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

        difference_vectors = {}
        for i, pair in enumerate(pairs):
            seq0 = pair["seq0"]
            seq1 = pair["seq1"]
            side0 = pair["side0"]
            side1 = pair["side1"]
            idx0 = pair["idx0"]
            idx1 = pair["idx1"]
            im0 = images[seq0]
            im1 = images[seq1]
            
            if plot:
                plot_images(im0, im1, seq0, seq1, side0, side1, idx0, idx1)

            strip0 = im0[slices[side0]]
            strip1 = im1[slices[side1]]

            if method == "imreg":
                shift, fft = translation(strip0, strip1, return_fft=True)
                score = fft.max()
            else:  # method = skimage.feature.register_translation
                shift, error, phasediff = register_translation(strip0, strip1, return_error=True)
                fft = np.ones_like(strip0)
                score = 1-error

            if plot:
                plot_fft(strip0, strip1, shift, fft, side0, side1)

            if score < threshold:
                if verbose:
                    print("Score below threshold")
                shift = np.array((0,0))
                continue
            if verbose:
                print(f"Pair {i} -> {seq0}:{idx0} - {seq1}:{idx1} -> FFT score: {score:.4f} -> Shift: {shift}")

            # pairwise difference vector
            difference_vector = self.get_difference_vector(idx0, idx1, shift, overlap_k=overlap_k, verbose=False)
            # print(f"Difference vector: {difference_vector}")

            difference_vectors[seq0, seq1] = difference_vector

            if plot:
                plot_shifted(im0, im1, difference_vector, seq0, seq1, idx0, idx1, res_x, res_y)

        self.difference_vectors = difference_vectors
        return difference_vectors
    
    def get_montage_coords(self):
        """Get the coordinates for each section based on the gridspec only (not optimized)
               
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
        
        return vects

    def get_optimized_montage_coords(self, difference_vectors, method: str="leastsq", verbose: bool=False):
        """Use the difference vectors between each pair of images to calculate
        the optimal coordinates for each section using least-squares minimization
        
        Parameters
        ----------
        difference_vectors : dict
            dict containing the pairwise difference vectors between each image
        method : str
            Least-squares minimization method to use (lmfit)
        
        Returns
        -------
        coords : np.array[-1, 2]
            Optimized coordinates for each section in the montage map
        """
        res_x, res_y = self.image_shape
        grid = self.grid
        grid_x, grid_y = grid.shape
        n_gridpoints = grid_x * grid_y
        
        overlap_x = self.overlap_x
        overlap_y = self.overlap_y
        
        vects = self.get_montage_coords()

        # determine which frames items have neighbours
        has_neighbours = set([i for key in difference_vectors.keys() for i in key])

        # setup parameters
        params = lmfit.Parameters()

        middle_i = int(n_gridpoints / 2 )  # Find index of middlemost item
        for i, row in enumerate(vects):
            if i == middle_i:   # anchor on middle frame
                vary = False
            if i in has_neighbours:
                vary = True
            else:  # Fix coordinates with no observed neighbours
                vary = True
            vary = (i != middle_i)
            params.add(f"C{i}{0}", value=row[0], vary=vary)
            params.add(f"C{i}{1}", value=row[1], vary=vary)

        def obj_func(params, diff_vects):
            V = np.array([p.value for p in params.values()]).reshape(-1,2)
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

        args = difference_vectors,
        res = lmfit.minimize(obj_func, params, args=args, method=method)

        lmfit.report_fit(res, show_correl=verbose, min_correl=0.8)

        Vn = np.array([p.value for p in res.params.values()]).reshape(-1,2)
        offset = min(Vn[:,0]), min(Vn[:,1])
        coords = Vn - offset

        return coords
   
    def stitch(self, coords: "np.array[-1, 2]", method: str=None, binning: int=1, plot: bool=False):
        """Stitch the images together using the given list of pixel coordinates
        for each section

        Parameters
        ----------
        coords : np.array[-1, 2]
            List of x/y pixel coordinates
        binning : int
            Bin the Montage image by this factor
        plot : bool
            Plot the stitched image

        Return
        ------
        stitched : np.array
            Stitched image
        """

        grid = self.grid
        images = self.images
        nx, ny = grid.shape
        res_x, res_y = self.image_shape
        overlap_x, overlap_y = self.overlap_x, self.overlap_y

        c = coords.astype(int)
        stitched_x, stitched_y = c.max(axis=0) - c.min(axis=0)
        stitched_x += res_x
        stitched_y += res_y

        stitched = np.zeros((int(stitched_x / binning), int(stitched_y / binning)), dtype=np.int32)

        if method in ("average", "weighted"):
            n_images = np.zeros((int(stitched_x), int(stitched_y)), dtype=np.int32)

            if method == "weighted":
                weight = weight_map(self.image_shape, method="circle")

        if plot:
            fig, ax = plt.subplots(figsize=(10, 10))

        for i, idx in enumerate(sorted_grid_indices(grid)):
            new_shape = int(res_x / binning), int(res_y / binning)
            im = bin_ndarray(images[i], new_shape)

            x0, y0 = c[i]
            x0 = int(x0 / binning)
            y0 = int(y0 / binning)

            x1 = x0 + im.shape[0]
            y1 = y0 + im.shape[1]

            # print(f"{x0:10d} {x1:10d} {y0:10d} {y1:10d}")

            if method == "average":
                stitched[x0:x1, y0:y1] += im
                n_images[x0:x1, y0:y1] += 1
            if method == "weighted":
                stitched[x0:x1, y0:y1] += im * weight
                n_images[x0:x1, y0:y1] += weight
            else:
                stitched[x0:x1, y0:y1] = im

            if plot:
                txt = f"{i}\n{idx}"
                ax.text((x0 + x1) / 2, (y0 + y1) / 2, txt, color="red", fontsize=18, ha='center', va='center')

        if method in ("average", "weighted"):
            n_images = np.where(n_images == 0, 1, n_images)
            stitched /= n_images

        if plot:
            ax.imshow(stitched)
            plt.show()

        self.stitched = stitched
        self.centers = coords + np.array((res_x, res_y)) / 2
        self.coords = coords
        self.stitched_binning = binning

        return stitched

    def plot(self, coords: "np.array[-1, 2]"):
        """Stitch the images together using the given list of pixel coordinates
        for each section

        Parameters
        ----------
        coords : np.array[-1, 2]
            List of x/y pixel coordinates
        """
        self.stitch(coords, plot=True)

    def pixel_to_stagecoord(self, px_coord: tuple) -> tuple:
        """Takes a pixel coordinate and transforms it into a stage coordinate"""
        # m.stagematrix = np.array([8.797544, 0.052175, 0.239726, 8.460119]).reshape(2,2) / (2*1000)
        mati = np.linalg.inv(self.stagematrix)

        px_coord = np.array(px_coord)
        
        px_coord = self.stitched_binning * px_coord
        centers = self.centers
        
        diffs = np.linalg.norm((centers - px_coord), axis=1)
        j = np.argmin(diffs)
        print(j)  # ok

        coord = self.coords[j]

        stage_coord = self.stagecoords[j]
        stage_shift = np.dot(px_coord - coord, mati)
        
        print(stage_coord)

        new_stagecoord = stage_coord + stage_shift

        return new_stagecoord

    def stage_to_pixelcoord(self, coord: tuple) -> tuple:
        """Takes a stage coordinate and transforms it into a pixel coordinate"""
        mat = self.stagematrix

        raise NotImplementedError
        return px_coord


class GridMontage(object):
    """Set up an automated montage map"""
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.direction = "updown"
        self.zigzag = True

    @property
    def gridspec(self):
        gridspec = {
            "gridshape": (self.nx, self.ny),
            "direction": self.direction,
            "zigzag": self.zigzag,
        }
        return gridspec

    def setup(self, 
              nx: int, ny: int, 
              overlap: float=0.1, 
              stage_shift: tuple=(0.0, 0.0), 
              binning: int=None) -> "np.array":
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

        px_center = vect * (np.array(grid.shape) / np.array((nx/2, ny/2)))


        stagematrix = self.ctrl.get_stagematrix(binning=binning)

        mati = np.linalg.inv(stagematrix)

        stage_center = np.dot(px_center, mati) + stage_shift
        stagepos = np.dot(px_coords, mati)

        coords = ((stagepos - stage_center)).astype(int)

        self.stagecoords = coords
        self.grid = grid
        self.mode = self.ctrl.mode
        self.magnification = self.ctrl.magnification.value
        self.spotsize = self.ctrl.spotsize

        print("Setting up gridscan.")
        print("  Mag:", self.magnification)
        print("  Mode:", self.mode)
        print("  Grid:", nx, ny, self.direction, self.zigzag)
        print("  Overlap:", self.overlap)
        print()
        print("  Image shape:", res_x, res_y)
        print("  Pixel center:", px_center)
        print("  Spot size:", self.spotsize)

        return coords
    
    def start(self):
        """Start the experiment."""
        ctrl = self.ctrl

        buffer = []

        def pre_acquire(ctrl):
            print("Pre-acquire: done!")

        def acquire(ctrl):
            img, h = ctrl.getImage()
            buffer.append((img, h))

        def post_acquire(ctrl):
            print("Post-acquire: done!")

        self.ctrl.acquire_at_items(self.stagecoords, 
                                   acquire=acquire, 
                                   pre_acquire=pre_acquire, 
                                   post_acquire=post_acquire)

        self.stagematrix = self.ctrl.get_stagematrix()
        self.buffer = buffer

        return buffer

    def to_montage(self):
        """Convert the experimental data to a `Montage` object."""
        images = [im for im,h in self.buffer]
        m = Montage(images=images, gridspec=self.gridspec, overlap=self.overlap)
        m.stagecoords = self.stagecoords
        m.stagematrix = self.stagematrix
        return m

    def save(self, drc: str=None):
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

