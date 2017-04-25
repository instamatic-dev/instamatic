import numpy as np
import matplotlib.pyplot as plt
from xcore import UnitCell
from xcore.spacegroup import generate_hkl_listing
from fractions import Fraction, gcd


def recover_integer_vector(u, denom=10):
    """
    For a given vector u, return the smallest vector with all integer entries.
    http://stackoverflow.com/a/36367043
    """

    # make smallest non-zero entry 1
    u /= min(abs(x) for x in u if x)

    # get the denominators of the fractions
    denoms = [Fraction(x).limit_denominator(denom).denominator for x in u]

    # multiply the scaled u by LCM(denominators)
    lcm = lambda a, b: a * b / gcd(a, b)
    return u * reduce(lcm, denoms)


def pythoncross(v1, v2):
    """Take the cross product between v1 and v2, slightly faster than np.cross"""
    c = [v1[1]*v2[2] - v1[2]*v2[1],
         v1[2]*v2[0] - v1[0]*v2[2],
         v1[0]*v2[1] - v1[1]*v2[0]]

    return c


def fromtorotation(v1, v2):
    """
    Efficient routine to find rotation matrix from one vector to another
    like rotation_matrix_fromv1_to_v2

    http://dx.doi.org/10.1080/10867651.1999.10487509
    """
    EPSILON = 0.000001

    # normalizing is essential for getting the rotational component only
    v1 = v1/np.sqrt(np.dot(v1, v1))
    v2 = v2/np.sqrt(np.dot(v2, v2))

    e = np.dot(v1, v2)

    f = abs(e)

    if (f > 1.0-EPSILON):
        raise ValueError('fromtorotation does not work well with near parallel axes')

    v = np.array(pythoncross(v1, v2))
    h = 1.0/(1.0 + e)

    hvx = h * v[0]
    hvz = h * v[2]
    hvxy = hvx * v[1]
    hvxz = hvx * v[2]
    hvyz = hvz * v[1]

    mtx = np.array([[e + hvx * v[0],         hvxy + v[2],    hvxz - v[1]],
                    [hvxy - v[2], e + h * v[1] * v[1],    hvyz + v[0]],
                    [hvxz + v[1],         hvyz - v[0], e + hvz * v[2]]])

    return mtx


def compose_rotation(angx, angy, angz):
    """
    angx,angy,angz = decompose_rotation(m)
    m = compose_rotation(angx,angy,angz)
    """
    cosa = np.cos(angx)
    cosb = np.cos(angy)
    cosc = np.cos(angz)
    sina = np.sin(angx)
    sinb = np.sin(angy)
    sinc = np.sin(angz)
    return np.array([[cosc*cosb, cosc*sinb*sina-sinc*cosa, cosc*sinb*cosa+sinc*sina],
                     [sinc*cosb, sinc*sinb*sina+cosc*cosa,
                         sinc*sinb*cosa-cosc*sina],
                     [-sinb, cosb*sina, cosb*cosa]])


def polar2xyz(psi, phi, r=1.0):
    """Converts polar to carthesian coordinates"""
    return np.array([r*np.sin(psi)*np.cos(phi),
                     r*np.sin(psi)*np.sin(phi),
                     r*np.cos(psi)])


def generate_all_vectors(psistep=0.01, phistep=0.01, x1=0.5, x2=2.0):
    """
    Generate all polar coordinates to positions on a sphere

    psistep, phistep: float, optional
        Rough distance between vectors in radians
    x1, x2: float, optional
        Determines how much of the sphere to generate
        with x1=0.5, x2=2.0, half a sphere is generated
    """
    npsi = np.ceil(x1*np.pi/psistep)
    psirange = np.linspace(0, x1*np.pi, npsi)
    # use [:-1] to prevent last step overlapping with first step
    for psi in psirange:
        nphi = np.ceil(x2*np.pi*np.sin(psi)/phistep)
        phirange = np.linspace(0, x2*np.pi, nphi)
        for phi in phirange[:-1]:
            yield psi, phi
    yield 0, 0  # this one is otherwise not generated


def make_2d_rotmat(theta):
    """Take angle in radians, and return 2D rotation matrix"""
    R = np.array([[np.cos(theta), -np.sin(theta)],
                  [np.sin(theta),  np.cos(theta)]])
    return R


def intersect_plane(O, D, P, N):
    """
    Return the distance from O to the intersection of the ray (O, D) with the
    plane (P, N), or +inf if there is no intersection.
    O and P are 3D points, D and N (normal) are normalized vectors.
    
    # https://gist.github.com/rossant/6046463
    """
    denom = np.dot(D, N)
    d = np.dot(P - O, N) / denom
    sel = (d < 0) | (denom < 1e-6)
    d[sel] = np.inf
    return d


def dists_to_sphere(vects, center, radius):
    """
    Return the distances from vects (np.array) to a sphere
    vects: (M, 3) numpy array
    radius: float, radius of sphere
    center: (N, 1) numpy array, center of sphere
    """
    return abs(np.sum((center-vects)**2, axis=1)**0.5 - radius)


class Projector(object):
    """Generate the diffraction spots on the detector. Projections are generated along a
    particular direction, and based on the distance of each spot from the Ewald sphere.

    cell: xcore.unitcell.UnitCell
        Instance of UnitCell used to generate the indices
    thickness: float, optional
        Crystal thickness in Angstrom defining the maximum distance from the Ewald sphere 
        (as 1/thickness) for a reflection to be considered in diffracting condition.
    wavelength: float, optional
        Wavelength in Angstrom defining the curvature of the Ewald sphere
    dmin, dmax: float, optional
        The range of d-spacings in Angstrom in which reflections should be generated.
    """

    def __init__(self, cell, thickness=200, wavelength=0.0251, dmin=1.0, dmax=np.inf, verbose=False):
        super(Projector, self).__init__()
        self.cell = cell
        
        self.basis = np.array([1, 0, 0])

        self.thickness = thickness
        self.wavelength = wavelength
        
        self.orth  = cell.orthogonalization_matrix()
        self.iorth = np.linalg.inv(self.orth)
        
        self.hkl = generate_hkl_listing(cell, dmin=1.0, dmax=dmax, expand=True)
        self.repl = np.dot(self.hkl, self.iorth)
        
        if verbose:
            self.cell.info()

            print "Projection data"
            print "   Reflections:", self.repl.shape[0]
            print "         Range: {} - {} Angstrom".format(dmin, dmax)
            print "    min(u,v,w):", self.repl.min(axis=0)
            print "    max(u,v,w):", self.repl.max(axis=0)
            print
        
    @classmethod
    def from_parameters(cls, params=None, spgr=None, name=None, **kwargs):
        """Return instance of Projector from cell parameters and space group

        See: xcore.unitcell.UnitCell"""
        return cls(UnitCell(params, spgr=spgr, name=name), **kwargs)
        
    def get_projection(self, alpha, beta, gamma=0):
        """Get projection along a particular zone axis

        alpha, beta: float
            Polar coordinates in radians defining defining the beam direction
        gamma: float, optional
            Angle in radians defining the in-plane rotation of the projection

        Returns array (5, n):
            5-column array hkl indices and xy coordinates in reciprocal coordinates
        """  
        beam_direction = polar2xyz(alpha, beta)
        
        proj = self._get_projection(beam_direction)
        
        if gamma:
            rot_gamma = make_2d_rotmat(gamma)
            proj[:,3:5] = np.dot(proj[:,3:5], rot_gamma)
        
        return proj

    def get_projection_along_axis(self, zone_axis=(1, 0, 0), gamma=0):
        """Get projection along a particular zone axis

        zone_axis: array or tuple (3)
            Zone axis defining the beam direction
        gamma: float, optional
            Angle in radians defining the in-plane rotation of the projection

        Returns array (5, n):
            5-column array hkl indices and xy coordinates in reciprocal coordinates
        """  
        beam_direction = np.dot(np.array(zone_axis), self.orth)
        
        proj = self._get_projection(beam_direction)
        
        if gamma:
            rot_gamma = make_2d_rotmat(gamma)
            proj[:,3:5] = np.dot(proj[:,3:5], rot_gamma)
        
        return proj
        
    def _get_projection(self, beam_direction):
        """Get projection along a particular beam direction

        beam_direction: array (3, 1)
            Direction of the incident beam which defines the orientation of the Ewald sphere

        Returns array (5, n):
            5-column array hkl indices and xy coordinates in reciprocal coordinates
        """        
        thresh1 = 0.05
        radius = 1.0/self.wavelength
        thresh2 = 1.0/self.thickness
        basis = self.basis
        
        try:
            tr_mat = fromtorotation(beam_direction, basis)
        except ValueError as e:
#             print e, beam_direction
            tr_mat = np.eye(3)
        
        # project to normal
        normproj = np.dot(self.repl, beam_direction)
        # cut out slab to work with. Prevents expensive operations on other (irrelevant) vectors
        sel1 = abs(normproj) < thresh1

        # transform to align ewald sphere with detector plane [0, x, y]
        vects = np.dot(self.repl[sel1], tr_mat)

        # calculate distance to ewald circle
        CO = basis * radius
        dists = dists_to_sphere(vects, -CO, radius)

        # select vectors in diffracting condition based based on thresh2
        sel2 = dists < thresh2
        vects = vects[sel2]

        # normalize to ewald sphere

        O = np.array([0, 0, 0])

        # CP = CO + OP, where OP = vects
        CP = CO + vects

        # normalize CP vectors
        normalized_vects = CP/np.linalg.norm(CP, axis=1).reshape(-1,1)

        # find intersection of CO vector with detector plane (0, x, y)
        proj = normalized_vects*intersect_plane(-CO, normalized_vects, O, basis).reshape(-1,1) - CO
       
        return np.hstack((self.hkl[sel1][sel2], proj[:,1:3]))

    def plot(self, alpha, beta, gamma=0.0, show_hkl=True):
        """Plot projection with given alpha/beta/gamma"""
        vects = self.get_projection(alpha, beta, gamma)
        
        # beam_direction = polar2xyz(alpha, beta)
        # axis = np.dot(beam_direction, self.iorth)
        # zone_axis = recover_integer_vector(axis.round(5), denom=5).round(1)
        
        plt.scatter(vects[:,3], vects[:,4])
        plt.scatter(0, 0)
        if show_hkl:
            for h,k,l,x,y in vects:
                plt.text(x, y, "{:.0f} {:.0f} {:.0f}".format(h,k,l))
        plt.title("alpha: {}, beta: {}, gamma: {}".format(alpha, beta, gamma))
        plt.xlim(-1, 1)
        plt.ylim(-1, 1)
        # plt.axis("equal")
        plt.show()

    def plot_along_axis(self, zone_axis=(1, 0, 0), gamma=0.0, show_hkl=True):
        """Plot projection with given zone_axis and gamma"""
        vects = self.get_projection_along_axis(zone_axis, gamma)
        plt.scatter(vects[:,3], vects[:,4])
        plt.scatter(0, 0)
        if show_hkl:
            for h,k,l,x,y in vects:
                plt.text(x, y, "{:.0f} {:.0f} {:.0f}".format(h,k,l))
        plt.title("zone axis: {}, gamma: {}".format(zone_axis, gamma))
        plt.xlim(-1, 1)
        plt.ylim(-1, 1)
        # plt.axis("equal")
        plt.show()
    
    def generate_all_projections(self):
        """Generates all vectors with a separation of phistep/psistep

        phistep, psistep: float
            Angle separation in radians between polar coordinates of normals to projections

        Returns projections, infos: list, list
            Projections is a list of hkl and xy coordinates in reciprocal coordinates
            Infos is a list of accompanying data, such as the number, and alpha/beta angle in radians
        """

        lauegr = self.cell.laue_group

        from orientations import get_orientations

        alpha_beta = get_orientations(lauegr=lauegr)[:,3:5]

        projections = []
        infos = []
        for i, (alpha, beta) in enumerate(alpha_beta):
            projections.append(self.get_projection(alpha=alpha, beta=beta))
            infos.append((i, alpha, beta))
        return projections, infos

