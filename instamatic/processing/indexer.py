from instamatic.formats import *
from instamatic.stretch_correction import affine_transform_ellipse_to_circle, apply_transform_to_image
from scipy import ndimage
import heapq
from extensions.indexer import get_score
import lmfit

from collections import namedtuple

import yaml
from collections import OrderedDict


def yaml_ordered_dump(obj, f=None, Dumper=yaml.Dumper, **kwds):
    """
    Maintain order when saving data to yaml file
    http://stackoverflow.com/a/21912744

    obj: object to serialize
    f: file-like object or str path to file
    """
    if isinstance(f, str):
        f = open(f, "w")
    class OrderedDumper(Dumper):
        pass
    def _dict_representer(dumper, obj):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            obj.items())
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    return yaml.dump(obj, f, OrderedDumper, **kwds)


def yaml_ordered_load(f, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    """
    Maintain order when reading yaml file
    http://stackoverflow.com/a/21912744
    
    f: file-like object or str path to file
    """
    if isinstance(f, str):
        f = open(f, "w")
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(f, OrderedLoader)


def get_score_python(img, pks, scale, center_x, center_y):
    """Equivalent of get_score implemented in python"""
    xmax = img.shape[0]
    ymax = img.shape[1]
    xmin = 0
    ymin = 0
    nrows = pks.shape[0]
    score = 0 
    
    for n in range(nrows):
        i = int(pks[n, 0] * scale + center_x)
        j = int(pks[n, 1] * scale + center_y)
        
        if j < ymin:
            continue
        if j >= ymax:
            continue
        if i < xmin:
            continue
        if i >= xmax:
            continue

        score = score + img[i, j]

    return score


def remove_background_gauss(img, min_sigma=3, max_sigma=30, threshold=1):
    """Remove background from an image using a difference of gaussian approach

    img: ndarray
        Image array
    min_sigma: float, optional
        The minimum standard deviation for the gaussian filter
    max_sigma: float, optional
        The maximum standard deviation for the gaussian filter
    threshold: float, optional
        Remove any remaining features below this threshold

    Returns img: ndarray
        Image array with background removed
    """
    img = np.maximum(ndimage.gaussian_filter(img, min_sigma) - ndimage.gaussian_filter(img, max_sigma) - threshold, 0)
    return img


def make_2d_rotmat(theta):
    """Take angle in radians, and return 2D rotation matrix"""
    R = np.array([[np.cos(theta), -np.sin(theta)],
                  [np.sin(theta),  np.cos(theta)]])
    return R


def get_indices(pks, scale, center, shape):
    """Get the pixel indices for an image"""
    shapex, shapey = shape
    i, j = (pks * scale + center).astype(int).T
    sel = (0 < j) & (j < shapey) & (0 < i) & (i < shapex)
    return i[sel], j[sel]


# store the results of indexing
IndexingResult = namedtuple("IndexingResult", ["score", "number", "alpha", "beta", "gamma", "center_x", "center_y", "scale"])

# description of each projection
ProjInfo = namedtuple("ProjectionInfo", ["number", "alpha", "beta"])


class Indexer(object):
    """Indexing class for serial snapshot crystallography. Find the crystal orientations 
    from a single electron diffraction snapshot using a brute force method 

    The projections of all possible crystal orientations are generated in advance.
    For each projection, the corresponding value at the x,y coordinates of each
    diffraction spot are summed. The idea is that the best fitting orientation has 
    the highest score.

    Based on http://journals.iucr.org/m/issues/2015/04/00/fc5010/index.html

    projections: tuple or list of ndarrays
        List of numpy arrays with 5 columns, h, k, l, x, y
        x and y are the reciprocal lattice vectors of the reflections in diffracting
        condition. See Projector.
    infos: tuple or list of ProjInfo objects
        List of information corresponding to the projections
        Contains (n, alpha, beta)
    pixelsize: float
        the dimensions of each pixel expressed in Angstrom^-1. The detector is placed
        at the origin of the reciprocal lattice, with the incident beam perpendicular 
        to the detector.
    theta: float
        Angle step in radians for gamma
    projector: instance of Projector
        Used for generating projections of arbitrary orientation.

    To use:
        img = read_tiff("image_0357_0001.tiff")
        projector = Projector.from_parameters((5.4301,), spgr="Fd-3m")
        indexer = Indexer.from_projector(projector, pixelsize=0.00316)
        results = indexer.index(img, center=(256, 256))
        indexer.plot(results[0])
        refined = indexer.refine_all(img, results)
        indexer.plot(refined[0])
    """
    def __init__(self, projections, infos, pixelsize, theta=0.03, projector=None):
        super(Indexer, self).__init__()
        
        self.projections = projections
        self.infos = infos
        
        self._projector = projector
        
        self.pixelsize = pixelsize
        self.scale = 1/pixelsize
        
        self.theta = theta
        
        nprojections = len(self.projections)
        nrotations = int(2*np.pi/self.theta)
        print "{} projections x {} rotations = {} items".format(nprojections, nrotations, nprojections*nrotations)
    
    @classmethod
    def from_projections_file(cls, fn="projections.npy", **kwargs):
        """Initialize instance of Indexing using a projections file

        fn: str
            path to projections.npy
        """
        infos, projections = np.load(fn)
        infos = [ProjInfo(*info) for info in infos]

        return cls(projections=projections, infos=infos, **kwargs)
    
    @classmethod
    def from_projector(cls, projector, **kwargs):
        """Initialize isntance of Indexer using an instance of Projector

        projector: Projector object
        """
        projections, infos = projector.generate_all_projections()
        infos = [ProjInfo(*info) for info in infos]
        return cls(projections=projections, infos=infos, projector=projector, **kwargs)
    
    @property
    def projector(self):
        if self._projector:
            return self._projector
        else:
            raise AttributeError("Please supply an instance of 'Projector'.")
    
    @projector.setter
    def projector(self, projector):
        self._projector = projector
    
    def index(self, img, center, **kwargs):
        """
        This function attempts to index the diffraction pattern in `img`

        img: ndarray
            image array
        center: tuple(x, y)
            x and y coordinates to the position of the primary beam
        """
        return self.find_orientation(img, center, **kwargs)
        
    def find_orientation(self, img, center, **kwargs):
        """
        This function attempts to find the orientation of the crystal in `img`

        img: ndarray
            image array
        center: tuple(x, y)
            x and y coordinates to the position of the primary beam
        """
        theta      = kwargs.get("theta", self.theta)
        nsolutions = kwargs.get("nsolutions", 20)
        
        heap = [(0, None, None) for nsolution in range(nsolutions + 1)]
        vals  = []
        
        center_x, center_y = center
        scale = self.scale
        
        rotations = np.arange(0, 2*np.pi, theta)
        R = make_2d_rotmat(theta)
        
        t1 = time.time()
        for n, projection in enumerate(self.projections):
            pks = projection[:,3:5]
            
            for m, rotation in enumerate(rotations):
                score  = get_score(img, pks, scale, center_y, center_x)
        
                vals.append(score)
                
                heapq.heapreplace(heap, (score, n, m))
                
                pks = np.dot(pks, R) # for next round
        
        t2 = time.time()
        print "Time total/proj/run: {:.2f} s / {:.2f} ms / {:.2f} us".format(t2-t1, 1e3*(t2-t1) / (n+1), 1e6*(t2-t1)/ ((n+1)*len(rotations)))
               
        heap = sorted(heap, reverse=True)[0:nsolutions]
        
        results = [IndexingResult(score=score,
                                 number=n,
                                 alpha=self.infos[n].alpha,
                                 beta=self.infos[n].beta,
                                 gamma=theta*m,
                                 center_x=center_x,
                                 center_y=center_y,
                                 scale=scale) for (score,n,m) in heap]

        return results
    
    def plot_all(self, img, results, **kwargs):
        """
        Plot each projection given in results on the image

        img: ndarray
            image array
        results: tuple or list of IndexingResult objects
        """
        for result in results:
            self.plot(img, result, **kwargs)
    
    def plot(self, img, result, **kwargs):
        """Plot the image with the projection given in 'result'

        img: ndarray
            image array
        result: IndexingResult object

        """
        n = result.number
        cx = result.center_x
        cy = result.center_y
        scale = result.scale
        alpha = result.alpha
        beta = result.beta
        gamma = result.gamma
        
        pks = projector.get_projection(alpha, beta, gamma)[:,3:5]
        
        score = get_score(img, pks, scale, cy, cx)
        
        i, j = get_indices(pks, scale, (cy, cx), img.shape)
        
        plt.imshow(img, vmax=200)
        plt.plot(cx, cy, marker="o")
        plt.title("alpha: {:.2f}, beta: {:.2f}, gamma: {:.2f}\n score = {}, proj = {}".format(alpha, beta, gamma, score, n))
        plt.plot(j, i, marker="+", lw=0)
        plt.show()
    
    def refine_all(self, img, results, projector=None, sort=True, **kwargs):
        """
        Refine the orientations of all solutions in results agains the given image

        img: ndarray
            Image array
        results: tuple or list of IndexingResult objects
            Specifications of the solutions to be refined
        projector: Projector object, optional
            This keyword should be specified if projector is not already an attribute on Indexer,
            or if a different one should be used
        sort: bool, optional
            Sort the result of the refinement
        """
        kwargs.setdefault("verbose", False)
        new_results = [self.refine(img, result, projector=projector, **kwargs) for result in results]

        # sort in descending order by score
        if sort:
            return sorted(new_results, key=lambda t: t.score, reverse=True)
        else:
            return new_results
    
    def refine(self, img, result, projector=None, verbose=True, **kwargs):
        """
        Refine the orientations of all solutions in results agains the given image

        img: ndarray
            Image array
        result: IndexingResult object
            Specifications of the solution to be refined
        projector: Projector object, optional
            This keyword should be specified if projector is not already an attribute on Indexer,
            or if a different one should be used
        """
        n = result.number
        cx = result.center_x
        cy = result.center_y
        scale = result.scale
        alpha = result.alpha
        beta = result.beta
        gamma = result.gamma
        score = result.score

        if not projector:
            projector = self.projector
        
        def objfunc(params, pks, img):
            cx = params["center_x"].value
            cy = params["center_y"].value
            alpha = params["alpha"].value
            beta = params["beta"].value
            gamma = params["gamma"].value
            scale = params["scale"].value
            
            pks = projector.get_projection(alpha, beta, gamma)[:,3:5]
            score = get_score(img, pks, scale, cy, cx)
            # print cx, cy, scale, gamma, score
            
            return 1e3/(1+score)
        
        method = kwargs.get("method", "nelder")
        # should be one of nelder, powell, cobyla, least-squares
        
        params = lmfit.Parameters()
        params.add("center_x", value=cx, vary=True, min=cx - 2.0, max=cx + 2.0)
        params.add("center_y", value=cy, vary=True, min=cy - 2.0, max=cy + 2.0)
        params.add("alpha", value=alpha, vary=True)
        params.add("beta",  value=beta,  vary=True)
        params.add("gamma", value=gamma, vary=True)
        params.add("scale", value=scale, vary=True)
        
        pks = projector.get_projection(alpha, beta, gamma)[:,3:5]
        
        args = pks, img
        
        res = lmfit.minimize(objfunc, params, args=args, method=method)
        if verbose:
            lmfit.report_fit(res)
                
        p = res.params
        
        alpha_new, beta_new, gamma_new = p["alpha"].value, p["beta"].value, p["gamma"].value
        scale_new, center_x_new, center_y_new = p["scale"].value, p["center_x"].value, p["center_y"].value
        
        pks_new = projector.get_projection(alpha_new, beta_new, gamma_new)[:,3:5]
        
        score_new = get_score(img, pks_new, scale_new, center_y_new, center_x_new)
        
        # print "Score: {} -> {}".format(int(score), int(score_new))
        
        refined = IndexingResult(score=score_new,
                                 number=n,
                                 alpha=alpha_new,
                                 beta=beta_new,
                                 gamma=gamma_new,
                                 center_x=center_x_new,
                                 center_y=center_y_new,
                                 scale=scale_new)
        
        return refined


def main():
    pixelsize = 0.0031593

    azimuth = np.radians(83.39 - 90)
    stretch = 2.43 / (2*100)
    tr_mat = affine_transform_ellipse_to_circle(azimuth, stretch)

    filelist = yaml_ordered_load("filelist.yaml")
    indexer = Indexer.from_projections_file(pixelsize=pixelsize)

    drc = "/images/"
    
    all_results = {}
    
    for i, (fn, settings) in enumerate(filelist.items()):
        print fn
        center = settings["det_xcent"], settings["det_ycent"]
          
        img, h = read_tiff(os.path.join(drc, fn))
        
        img = apply_transform_to_image(img, tr_mat)
        img = remove_background_gauss(img, 3, 30, threshold=2)
        
        results = indexer.index(img, center, nsolutions=25)
        
        refined = indexer.refine_all(img, results, method="nelder")
        # indexer.plot_all(img, refined[0:5])
        all_results[fn] = refined[0]
            
        # indexer.plot(img, refined[0])



if __name__ == '__main__':
    main()