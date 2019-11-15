import numpy as np


def sorted_grid_indices(grid):
    """
    Sorts 2d the grid by its values, and returns an array
    with the indices (i.e. np.argsort on 2d arrays)
    https://stackoverflow.com/a/30577520
    """
    return np.dstack(np.unravel_index(np.argsort(grid.ravel()), grid.shape))[0]


def make_grid(shape: tuple, direction: str="updown", zigzag: bool=True) -> "np.array":
    """Defines the grid montage collection scheme
    
    Parameters
    ----------
    shape : tuple(int, int)
        Defines the shape of the grid
    direction : str
        Defines the direction of data collection
    zigzag : bool
        Defines if the data has been collected in a zigzag manner
    
    Returns
    -------
    np.array
    """
    nx, ny = shape
    grid = np.arange(nx * ny).reshape(shape)

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


def make_slices(boundary_x: int, boundary_y: int, shape=(512,512), plot: bool=False) -> dict:
    """Make slices for left/right/top/bottom image
    
    Parameters
    ----------
    boundary_x/boundary_y : int
        Defines how far to set the boundary
    shape : tuple:
        Define the shape of the image (only for plotting)
    plot : bool
        Plot the boundaries on blank images
    
    Returns
    -------
    Dictionary with the slices for each side
    """
    d = {}
    
    s_right = np.s_[:, -boundary_x:]
    s_left = np.s_[:, :boundary_x]
    s_top = np.s_[:boundary_y]
    s_bottom  = np.s_[-boundary_y:]

    slices = (s_right, s_left, s_top, s_bottom)
    labels = ("right", "left", "top", "bottom")

    d = dict(zip(labels, slices))
    
    if plot:
        fig, axes = plt.subplots(2,2, sharex=True, sharey=True)
        axes = axes.flatten()

        for ax, s_, label in zip(axes, slices, labels):
            arr = np.zeros((512, 512), dtype=int)
            arr[s_] = 1
            ax.imshow(arr)
            ax.set_title(label)

        plt.show()
    
    return d


def define_directions(pairs: list):
    """Define pairwise relations between indices

    TODO: doc
    """
    for pair in pairs:
        i0, j0 = pair["idx0"]
        i1, j1 = pair["idx1"]
    
        if i0 == i1:
            if j1 > j0:
                side0, side1 = "bottom", "top"
            else:
                side0, side1 = "top", "bottom"
        else:
            if i1 > i0:
                side0, side1 = "right", "left"
            else:
                side0, side1 = "left", "right"
        
        # print(i0, j0, i1, j1, side0, side1)
        
        pair["side0"] = side0
        pair["side1"] = side1
    
    return pairs


def define_pairs(grid: "np.ndarray"):
    """Take a sequence grid and return all pairs of neighbours

    TODO: doc
    """
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


class GridMontage(object):
    """docstring for GridMontage"""
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
    
    def setup(self, nx: int, ny: int, overlap: float=0.1, stage_shift: tuple=(0.0, 0.0), binning: int=None) -> "np.array":
        res_x = 4096
        res_y = 4096

        print("shape:", res_x, res_y)

        overlap_x = int(res_x * overlap)
        overlap_y = int(res_y * overlap)

        vect = np.array((res_x - overlap_x, res_y - overlap_y))

        grid = make_grid((nx, ny))
        grid_indices = sorted_grid_indices(grid)
        px_coords = grid_indices * vect

        px_center = vect * (np.array(grid.shape) / np.array((nx/2, ny/2)))

        print(px_center)

        stagematrix = self.ctrl.get_stagematrix(binning=binning)

        mati = np.linalg.inv(stagematrix)

        print(mati)

        stage_center = np.dot(px_center, mati) + stage_shift
        stagepos = np.dot(px_coords, mati)

        montage_pos = ((stagepos - stage_center)).astype(int)

        return montage_pos
    
    def start(self):
        pass


if __name__ == '__main__':
    from instamatic import TEMController
    ctrl = TEMController.initialize()
    ctrl.mode = "lowmag"
    ctrl.magnification.value = 100

    m = GridMontage(ctrl)
    pos = m.setup(5, 5)
    print(pos)
