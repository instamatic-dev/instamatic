import numpy as np

from pathlib import Path

from skimage.filters import threshold_local
from skimage.measure import find_contours
from skimage import morphology

from instamatic.formats import read_tiff
from instamatic.tools import find_beam_center_with_beamstop


def minimum_bounding_rectangle(points):
    """
    # From https://stackoverflow.com/a/33619018
    
    Find the smallest bounding rectangle for a set of points.
    Returns a set of points representing the corners of the bounding box.

    :param points: an nx2 matrix of coordinates
    :rval: an nx2 matrix of coordinates
    """
    from scipy.ndimage.interpolation import rotate
    from scipy.spatial import ConvexHull
    
    pi2 = np.pi/2.0

    # get the convex hull for the points
    hull_points = points[ConvexHull(points).vertices]

    # calculate edge angles
    edges = np.zeros((len(hull_points)-1, 2))
    edges = hull_points[1:] - hull_points[:-1]

    angles = np.zeros((len(edges)))
    angles = np.arctan2(edges[:, 1], edges[:, 0])

    angles = np.abs(np.mod(angles, pi2))
    angles = np.unique(angles)

    # find rotation matrices
    rotations = np.vstack([
        np.cos(angles),
        np.cos(angles-pi2),
        np.cos(angles+pi2),
        np.cos(angles)]).T

    rotations = rotations.reshape((-1, 2, 2))

    # apply rotations to the hull
    rot_points = np.dot(rotations, hull_points.T)

    # find the bounding points
    min_x = np.nanmin(rot_points[:, 0], axis=1)
    max_x = np.nanmax(rot_points[:, 0], axis=1)
    min_y = np.nanmin(rot_points[:, 1], axis=1)
    max_y = np.nanmax(rot_points[:, 1], axis=1)

    # find the box with the best area
    areas = (max_x - min_x) * (max_y - min_y)
    best_idx = np.argmin(areas)

    # return the best box
    x1 = max_x[best_idx]
    x2 = min_x[best_idx]
    y1 = max_y[best_idx]
    y2 = min_y[best_idx]
    r = rotations[best_idx]

    rval = np.zeros((4, 2))
    rval[0] = np.dot([x1, y2], r)
    rval[1] = np.dot([x2, y2], r)
    rval[2] = np.dot([x2, y1], r)
    rval[3] = np.dot([x1, y1], r)

    return rval


def radial_average(z, center, as_radial_map=False):
    """Calculate the radial profile by azimuthal averaging about a specified
    center.

    Parameters
    ----------
    center : array
        The array indices of the diffraction pattern center about which the
        radial integration is performed.
    as_radial_map : bool
        Return the radial average mapped to the pixel positions of the 2D image

    Returns
    -------
    radial_profile : array
        Radial profile of the diffraction pattern.
    """
    y, x = np.indices(z.shape)
    r = np.sqrt((x - center[1])**2 + (y - center[0])**2)
    r = r.astype(np.int)

    tbin = np.bincount(r.ravel(), z.ravel())
    nr = np.bincount(r.ravel())
    averaged = tbin / nr

    if as_radial_map:
        return averaged[r]
    else:
        return averaged


def find_beamstop_rect(img, center=None, threshold=0.5, pad=1, minsize=500, savefig=False):
    """Find rectangle fitting the beamstop
    
    1. Radially scale the image (divide each point in the image by the radial average)
    2. Segment the image via thresholding. The beamstop is identified by the area where the image < radially scaled image
    3. Contour the segmented image.
    4. Find minimum bounding rectangle for points that define the contours
    5. The contour closest to the beam center is then taken as beamstop
    
    input:
        image, nxn 2D np.array defining the image. The average of the image stack works well
        center, 2x1 np.array defining the center of the image. If omitted, will be find automatically
        threshold, float representing the threshold value for segmentation
        pad, int defining the padding of the beamstop to make it seem a bit larger
        minsize, int defining minimum size of the beamstop
        plot, boolean that defines whether the result should be plotted

    output:
        4x2 np.array defining the corners of the rectangle
    """

    if center is None:
        center = find_beam_center_with_beamstop(img, z=99)

    # get radially averaged image
    r_map = radial_average(img, center=center, as_radial_map=True)

    radial_scaled = img / r_map

    # image segmentation
    seg = radial_scaled < threshold

    seg = morphology.remove_small_objects(seg, 64)
    seg = morphology.remove_small_holes(seg, 64)
    
    # pad the beamstop to make the outline a big bigger
    if pad:
        seg = morphology.binary_dilation(seg, selem=morphology.disk(pad))

    arr = find_contours(seg, 0.5)

    if len(arr) > 1:
        rects = [minimum_bounding_rectangle(a) for a in arr if len(a) > minsize]
    
        a = [np.mean(rect, axis=0) for rect in rects]
        dists = [np.linalg.norm(b - center) for b in a]
        i = np.argmin(dists)
    
        rect = rects[i]

    ## This is not robust if there are other shaded areas
    # rect = sorted(arr, key=lambda x: len(x), reverse=True)[0]
    # rect = minimum_bounding_rectangle(beamstop)

    if savefig:
        import matplotlib
        matplotlib.use("pdf")
        import matplotlib.pyplot as plt

        fig, (ax1, ax2, ax3) = plt.subplots(ncols=3)
        for ax in ax1, ax2, ax3:
            ax.axis('off')

        ax1.imshow(radial_scaled, vmax=np.percentile(radial_scaled, 99))
        ax1.set_title("Radially scaled image")

        cx, cy = center
        ax1.scatter(cy, cx, marker="+", color="red")

        ax2.imshow(seg)
        ax2.set_title("Segmented image")

        ax3.imshow(img, vmax=np.percentile(img, 99))
        ax3.set_title("Mean image showing beamstop")
        ax3.scatter(cy, cx, marker="+")

        bx, by = np.vstack((rect, rect[0])).T
        ax3.plot(by, bx, "r-o")

        fn = "beamstop.png"
        plt.savefig(fn, dpi=150)

    return rect


if __name__ == '__main__':
    drc = "."
    fns = list(Path(drc).glob("raw/*.tif"))

    print(len(fns))
    
    imgs, hs = zip(*(read_tiff(fn) for fn in fns))
    
    stack_mean = np.mean(imgs, axis=0)

    center = find_beam_center_with_beamstop(stack_mean, z=99)

    beamstop_rect = find_beamstop_rect(stack_mean, center, pad=1, plot=True)
    
    from instamatic.tools import to_xds_untrusted_area

    xds_quad = to_xds_untrusted_area("quadrilateral", beamstop_rect)

    print(xds_quad)

