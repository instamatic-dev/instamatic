import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import numpy as np

from .deflectors import *
from .lenses import *
from .microscope import Microscope
from .stage import *
from .states import *
from instamatic import config
from instamatic.camera import Camera
from instamatic.exceptions import TEMControllerError
from instamatic.formats import write_tiff
from instamatic.image_utils import rotate_image


_ctrl = None  # store reference of ctrl so it can be accessed without re-initializing

default_cam = config.camera.name
default_tem = config.microscope.name

use_tem_server = config.settings.use_tem_server
use_cam_server = config.settings.use_cam_server


def initialize(tem_name: str = default_tem, cam_name: str = default_cam, stream: bool = True) -> 'TEMController':
    """Initialize TEMController object giving access to the TEM and Camera
    interfaces.

    Parameters
    ----------
    tem_name : str
        Name of the TEM to use
    cam_name : str
        Name of the camera to use, can be set to 'None' to skip camera initialization
    stream : bool
        Open the camera as a stream (this enables `TEMController.show_stream()`)

    Returns
    -------
    ctrl : `TEMController`
        Return TEM control object
    """

    print(f"Microscope: {tem_name}{' (server)' if use_tem_server else ''}")
    tem = Microscope(tem_name, use_server=use_tem_server)

    if cam_name:
        if use_cam_server:
            cam_tag = ' (server)'
        elif stream:
            cam_tag = ' (stream)'
        else:
            cam_tag = ''

        print(f'Camera    : {cam_name}{cam_tag}')

        cam = Camera(cam_name, as_stream=stream, use_server=use_cam_server)
    else:
        cam = None

    global _ctrl
    ctrl = _ctrl = TEMController(tem=tem, cam=cam)

    return ctrl


def get_instance() -> 'TEMController':
    """Gets the current `ctrl` instance if it has been initialized, otherwise
    initialize it using default parameters."""

    global _ctrl

    if _ctrl:
        ctrl = _ctrl
    else:
        ctrl = _ctrl = initialize()

    return ctrl


class TEMController:
    """TEMController object that enables access to all defined microscope
    controls.

    tem: Microscope control object (e.g. instamatic/TEMController/simu_microscope.SimuMicroscope)
    cam: Camera control object (see instamatic.camera) [optional]
    """

    def __init__(self, tem, cam=None):
        super().__init__()

        self._executor = ThreadPoolExecutor(max_workers=1)

        self.tem = tem
        self.cam = cam

        self.gunshift = GunShift(tem)
        self.guntilt = GunTilt(tem)
        self.beamshift = BeamShift(tem)
        self.beamtilt = BeamTilt(tem)
        self.imageshift1 = ImageShift1(tem)
        self.imageshift2 = ImageShift2(tem)
        self.diffshift = DiffShift(tem)
        self.stage = Stage(tem)
        self.stageposition = self.stage  # for backwards compatibility
        self.magnification = Magnification(tem)
        self.brightness = Brightness(tem)
        self.difffocus = DiffFocus(tem)
        self.beam = Beam(tem)
        self.screen = Screen(tem)
        self.mode = Mode(tem)

        self.autoblank = False
        self._saved_alignments = config.get_alignments()

        print()
        print(self)
        self.store()

    def __repr__(self):
        return (f'Mode: {self.tem.getFunctionMode()}\n'
                f'High tension: {self.high_tension/1000:.0f} kV\n'
                f'Current density: {self.current_density:.2f} pA/cm2\n'
                f'{self.gunshift}\n'
                f'{self.guntilt}\n'
                f'{self.beamshift}\n'
                f'{self.beamtilt}\n'
                f'{self.imageshift1}\n'
                f'{self.imageshift2}\n'
                f'{self.diffshift}\n'
                f'{self.stage}\n'
                f'{self.magnification}\n'
                f'{self.difffocus}\n'
                f'{self.brightness}\n'
                f'SpotSize({self.spotsize})\n'
                f'Saved alignments: {tuple(self._saved_alignments.keys())}')

    @property
    def high_tension(self) -> float:
        """Get the high tension value in V."""
        return self.tem.getHTValue()

    @property
    def current_density(self) -> float:
        """Get current density from fluorescence screen in pA/cm2."""
        return self.tem.getCurrentDensity()

    @property
    def spotsize(self) -> int:
        return self.tem.getSpotSize()

    @spotsize.setter
    def spotsize(self, value: int):
        self.tem.setSpotSize(value)

    def acquire_at_items(self, *args, **kwargs) -> None:
        """Class to automated acquisition at many stage locations. The
        acquisition functions must be callable (or a list of callables) that
        accept `ctrl` as an argument. In case a list of callables is given,
        they are excecuted in sequence.

        Internally, this runs instamatic.acquire_at_items.AcquireAtItems. See there for more information.

        Parameters
        ----------
        nav_items: list
            List of (x, y) / (x, y, z) coordinates (nm), or
            List of navigation items loaded from a `.nav` file.
        acquire: callable, list of callables
            Main function to call, must take `ctrl` as an argument
        pre_acquire: callable, list of callables
            This function is called before the first acquisition item is run.
        post_acquire: callable, list of callables
            This function is run after the last acquisition item has run.
        backlash: bool
        Move the stage with backlash correction.
        """
        from instamatic.acquire_at_items import AcquireAtItems

        ctrl = self

        aai = AcquireAtItems(ctrl, *args, **kwargs)
        aai.start()

    def run_script_at_items(self, nav_items: list, script: str, backlash: bool = True) -> None:
        """"Run the given script at all coordinates defined by the nav_items.

        Parameters
        ----------
        nav_items: list
            Takes a list of nav items (read from a SerialEM .nav file) and loops over the
            stage coordinates
        script: str
            Runs this script at each of the positions specified in coordinate list
                This function will call 3 functions, which must be defined as:
                    `acquire`
                    `pre_acquire`
                    `post_acquire`

        backlash: bool
            Toggle to move to each position with backlash correction
        """
        from instamatic.io import find_script
        script = find_script(script)

        import importlib.util
        spec = importlib.util.spec_from_file_location('acquire', script)
        acquire = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(acquire)

        ntot = len(nav_items)

        print(f'Running script: {script} on {ntot} items.')

        pre_acquire = getattr(acquire, 'pre_acquire', None)
        post_acquire = getattr(acquire, 'post_acquire', None)
        acquire = getattr(acquire, 'acquire', None)

        self.acquire_at_items(nav_items,
                              acquire=acquire,
                              pre_acquire=pre_acquire,
                              post_acquire=post_acquire,
                              backlash=backlash)

    def run_script(self, script: str, verbose: bool = True) -> None:
        """Run a custom python script with access to the `ctrl` object.

        It will check if the script exists in the scripts directory if
        it cannot find it directly.
        """
        from instamatic.io import find_script
        script = find_script(script)

        if verbose:
            print(f'Executing script: {script}\n')

        ctrl = self

        t0 = time.perf_counter()
        exec(open(script).read())
        t1 = time.perf_counter()

        if verbose:
            print(f'\nScript finished in {t1-t0:.4f} s')

    def get_stagematrix(self, binning: int = None, mag: int = None, mode: int = None):
        """Helper function to get the stage matrix from the config file. The
        stagematrix is used to convert from pixel coordinates to stage
        coordiantes. The parameters are optional and if not given, the current
        values are read out from the microscope/camera.

        Parameters
        ----------
        binning: int
            Binning of the image that the stagematrix will be applied to
        mag: int
            Magnification value
        mode: str
            Current TEM mode ("lowmag", "mag1")

        Returns
        -------
        stagematrix : np.array[2, 2]
            Affine transformation matrix to convert from stage to pixel coordinates
        """

        if not mode:
            mode = self.mode.get()
        if not mag:
            mag = self.magnification.value
        if not binning:
            binning = self.cam.getBinning()

        stagematrix = config.calibration[mode]['stagematrix'][mag]
        stagematrix = np.array(stagematrix).reshape(2, 2) * binning  # um -> nm

        return stagematrix

    def align_to(self,
                 ref_img: 'np.array',
                 apply: bool = True,
                 verbose: bool = False,
                 ) -> list:
        """Align current view by comparing it against the given image using
        cross correlation. The stage is translated so that the object of
        interest (in the reference image) is at the center of the view.

        Parameters
        ----------
        ref_img : np.array
            Reference image that the microscope will be aligned to
        apply : bool
            Toggle to translate the stage to center the image
        verbose : bool
            Be more verbose

        Returns
        -------
        stage_shift : np.array[2]
            The stage shift vector determined from cross correlation
        """
        from skimage.registration import phase_cross_correlation

        current_x, current_y = self.stage.xy

        if verbose:
            print(f'Current stage position: {current_x:.0f} {current_y:.0f}')

        stagematrix = self.get_stagematrix()

        img = self.get_rotated_image()

        pixel_shift, error, phasediff = phase_cross_correlation(ref_img, img, upsample_factor=10)

        stage_shift = np.dot(pixel_shift, stagematrix)
        stage_shift[0] = -stage_shift[0]  # match TEM Coordinate system

        print(f'Aligning: shifting stage by dx={stage_shift[0]:6.0f} dy={stage_shift[1]:6.0f}')

        new_x = current_x + stage_shift[0]
        new_y = current_y + stage_shift[1]

        if verbose:
            print(f'New stage position: {new_x:.0f} {new_y:.0f}')

        if apply:
            self.stage.set_xy_with_backlash_correction(x=new_x, y=new_y)

        return stage_shift

    def find_eucentric_height(self, tilt: float = 5,
                              steps: int = 5,
                              dz: int = 50_000,
                              apply: bool = True,
                              verbose: bool = True) -> float:
        """Automated routine to find the eucentric height, accurate up to ~1 um
        Measures the shift (cross correlation) between 2 angles (-+tilt) over a
        range of z values (defined by `dz` and `steps`). The height is
        calculated by fitting the shifts vs. z.

        Fit: shift = alpha*z + beta -> z0 = -beta/alpha

        Takes roughly 35 seconds (2 steps) or 70 seconds (5 steps) on a JEOL 1400 with a TVIPS camera.

        Based on: Koster, et al., Ultramicroscopy 46 (1992): 207–27.
                  https://doi.org/10.1016/0304-3991(92)90016-D.

        Parameters
        ----------
        tilt:
            Tilt angles (+-)
        steps: int
            Number of images to take along the defined Z range
        dz: int
            Range to cover in nm (i.e. from -dz to +dz) around the current Z value
        apply: bool
            apply the Z height immediately
        verbose: bool
            Toggle the verbosity level

        Returns
        -------
        z: float
            Optimized Z value for eucentric tilting
        """
        from skimage.registration import phase_cross_correlation

        def one_cycle(tilt: float = 5, sign=1) -> list:
            angle1 = -tilt * sign
            self.stage.a = angle1
            img1 = self.get_rotated_image()

            angle2 = +tilt * sign
            self.stage.a = angle2
            img2 = self.get_rotated_image()

            if sign < 1:
                img2, img1 = img1, img2

            shift, error, phasediff = phase_cross_correlation(img1, img2, upsample_factor=10)

            return shift

        self.stage.a = 0
        # self.stage.z = 0 # for testing

        zc = self.stage.z
        print(f'Current z = {zc:.1f} nm')

        zs = zc + np.linspace(-dz, dz, steps)
        shifts = []

        sign = 1

        for i, z in enumerate(zs):
            self.stage.z = z
            if verbose:
                print(f'z = {z:.1f} nm')

            di = one_cycle(tilt=tilt, sign=sign)
            shifts.append(di)

            sign *= -1

        mean_shift = shifts[-1] + shifts[0]
        mean_shift = mean_shift / np.linalg.norm(mean_shift)
        ds = np.dot(shifts, mean_shift)

        p = np.polyfit(zs, ds, 1)  # linear fit
        alpha, beta = p

        z0 = -beta / alpha

        print(f'alpha={alpha:.2f} | beta={beta:.2f} => z0={z0:.1f} nm')
        if apply:
            self.stage.set(a=0, z=z0)

        return z0

    def grid_montage(self):
        """Create an instance of `gridmontage.GridMontage` using the current
        magnification/mode.

        Usage:
            gm = GridMontage(ctrl)
            pos = m.setup(5, 5)
            m = gm.to_montage()
            coords = m.get_montage_coords(optimize=True)
        """
        from instamatic.gridmontage import GridMontage
        gm = GridMontage(self)
        return gm

    def to_dict(self, *keys) -> dict:
        """Store microscope parameters to dict.

        keys: tuple of str (optional)
            If any keys are specified, dict is returned with only the given properties

        self.to_dict('all') or self.to_dict() will return all properties
        """

        # Each of these costs about 40-60 ms per call on a JEOL 2100, stage is 265 ms per call
        funcs = {
            'FunctionMode': self.tem.getFunctionMode,
            'GunShift': self.gunshift.get,
            'GunTilt': self.guntilt.get,
            'BeamShift': self.beamshift.get,
            'BeamTilt': self.beamtilt.get,
            'ImageShift1': self.imageshift1.get,
            'ImageShift2': self.imageshift2.get,
            'DiffShift': self.diffshift.get,
            'StagePosition': self.stage.get,
            'Magnification': self.magnification.get,
            'DiffFocus': self.difffocus.get,
            'Brightness': self.brightness.get,
            'SpotSize': self.tem.getSpotSize,
        }

        dct = {}

        if 'all' in keys or not keys:
            keys = funcs.keys()

        for key in keys:
            try:
                dct[key] = funcs[key]()
            except ValueError:
                # print(f"No such key: `{key}`")
                pass

        return dct

    def from_dict(self, dct: dict):
        """Restore microscope parameters from dict."""

        funcs = {
            # 'FunctionMode': self.tem.setFunctionMode,
            'GunShift': self.gunshift.set,
            'GunTilt': self.guntilt.set,
            'BeamShift': self.beamshift.set,
            'BeamTilt': self.beamtilt.set,
            'ImageShift1': self.imageshift1.set,
            'ImageShift2': self.imageshift2.set,
            'DiffShift': self.diffshift.set,
            'StagePosition': self.stage.set,
            'Magnification': self.magnification.set,
            'DiffFocus': self.difffocus.set,
            'Brightness': self.brightness.set,
            'SpotSize': self.tem.setSpotSize,
        }

        mode = dct['FunctionMode']
        self.tem.setFunctionMode(mode)

        for k, v in dct.items():
            if k in funcs:
                func = funcs[k]
            else:
                continue

            try:
                func(*v)
            except TypeError:
                func(v)

    def get_raw_image(self, exposure: float = None, binsize: int = None) -> np.ndarray:
        """Simplified function equivalent to `get_image` that only returns the
        raw data array.

        Parameters
        ----------
        exposure : float
            Exposure in seconds.
        binsize : int
            Image binning.

        Returns
        -------
        arr : np.array
            Image as 2D numpy array.
        """
        return self.cam.getImage(exposure=exposure, binsize=binsize)

    def get_future_image(self, exposure: float = None, binsize: int = None) -> 'future':
        """Simplified function equivalent to `get_image` that returns the raw
        image as a future. This makes the data acquisition call non-blocking.

        Parameters
        ----------
        exposure: float
            Exposure time in seconds
        binsize: int
            Binning to use for the image, must be 1, 2, or 4, etc

        Returns
        -------
        future : `future`
            Future object that contains the image as 2D numpy array.

        Usage:
            future = ctrl.get_future_image()
            (other operations)
            img = future.result()
        """
        future = self._executor.submit(self.get_raw_image, exposure=exposure, binsize=binsize)
        return future

    def get_rotated_image(self, exposure: float = None, binsize: int = None) -> np.ndarray:
        """Simplified function equivalent to `get_image` that returns the
        rotated image array.

        Parameters
        ----------
        exposure: float
            Exposure time in seconds
        binsize: int
            Binning to use for the image, must be 1, 2, or 4, etc
        mode : str
            Magnification mode
        mag : int
            Magnification value

        Returns
        -------
        arr : np.array
            Image as 2D numpy array.
        """
        future = self.get_future_image(exposure=exposure, binsize=binsize)

        mag = self.magnification.value
        mode = self.mode.get()

        arr = future.result()
        arr = rotate_image(arr, mode=mode, mag=mag)

        return arr

    def get_image(self,
                  exposure: float = None,
                  binsize: int = None,
                  comment: str = '',
                  out: str = None,
                  plot: bool = False,
                  verbose: bool = False,
                  header_keys: Tuple[str] = 'all',
                  ) -> Tuple[np.ndarray, dict]:
        """Retrieve image as numpy array from camera. If the exposure and
        binsize are not given, the default values are read from the config
        file.

        Parameters
        ----------
        exposure: float
            Exposure time in seconds
        binsize: int
            Binning to use for the image, must be 1, 2, or 4, etc
        comment: str
            Arbitrary comment to add to the header file under 'ImageComment'
        out: str
            Path or filename to which the image/header is saved (defaults to tiff)
        plot: bool
            Toggle whether to show the image using matplotlib after acquisition
        full_header: bool
            Return the full header

        Returns
        -------
        image: np.ndarray, headerfile: dict
            Tuple of the image as numpy array and dictionary with all the tem parameters and image attributes

        Usage:
            img, h = self.get_image()
        """
        if not self.cam:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute 'cam' (Camera has not been initialized)")

        if not binsize:
            binsize = self.cam.default_binsize
        if not exposure:
            exposure = self.cam.default_exposure

        if not header_keys:
            h = {}
        else:
            h = self.to_dict(header_keys)

        if self.autoblank:
            self.beam.unblank()

        h['ImageGetTimeStart'] = time.perf_counter()

        arr = self.get_rotated_image(exposure=exposure, binsize=binsize)

        h['ImageGetTimeEnd'] = time.perf_counter()

        if self.autoblank:
            self.beam.blank()

        h['ImageGetTime'] = time.time()
        h['ImageExposureTime'] = exposure
        h['ImageBinsize'] = binsize
        h['ImageResolution'] = arr.shape
        # k['ImagePixelsize'] = config.calibration[mode]['pixelsize'][mag] * binsize
        # k['ImageRotation'] = config.calibration[mode]['rotation'][mag]
        h['ImageComment'] = comment
        h['ImageCameraName'] = self.cam.name
        h['ImageCameraDimensions'] = self.cam.getCameraDimensions()

        if verbose:
            print(f'Image acquired - shape: {arr.shape}, size: {arr.nbytes / 1024:.0f} kB')

        if out:
            write_tiff(out, arr, header=h)

        if plot:
            import matplotlib.pyplot as plt
            plt.imshow(arr)
            plt.show()

        return arr, h

    def store_diff_beam(self, name: str = 'beam', save_to_file: bool = False):
        """Record alignment for current diffraction beam. Stores Guntilt (for
        dose control), diffraction focus, spot size, brightness, and the
        function mode.

        Restore the alignment using:     `ctrl.restore("beam")`
        """
        if self.mode != 'diff':
            raise TEMControllerError('Microscope is not in `diffraction mode`')
        keys = 'FunctionMode', 'Brightness', 'GunTilt', 'DiffFocus', 'SpotSize'
        self.store(name=name, keys=keys, save_to_file=save_to_file)

    def store(self, name: str = 'stash', keys: tuple = None, save_to_file: bool = False):
        """Stores current settings to dictionary.

        Multiple settings can be stored under different names. Specify
        which settings should be stored using `keys`
        """
        if not keys:
            keys = ()
        d = self.to_dict(*keys)
        d.pop('StagePosition', None)
        self._saved_alignments[name] = d

        if save_to_file:
            import yaml
            fn = config.alignments_drc / (name + '.yaml')
            yaml.dump(d, stream=open(fn, 'w'))
            print(f'Saved alignment to file `{fn}`')

    def restore(self, name: str = 'stash'):
        """Restores alignment from dictionary by the given name."""
        d = self._saved_alignments[name]
        self.from_dict(d)
        print(f"Microscope alignment restored from '{name}'")

    def close(self):
        try:
            self.cam.close()
        except AttributeError:
            pass

    def show_stream(self):
        """If the camera has been opened as a stream, start a live view in a
        tkinter window."""
        try:
            self.cam.show_stream()
        except AttributeError:
            print('Cannot open live view. The camera interface must be initialized as a stream object.')


def main_entry():
    import argparse
    description = """Connect to the microscope and camera, and open an IPython terminal to interactively control the microscope. Useful for testing! It initializes the TEMController (accessible through the `ctrl` variable) using the parameters given in the `config`."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-u', '--simulate',
                        action='store_true', dest='simulate',
                        help='Simulate microscope connection (default: False)')

    parser.add_argument('-c', '--camera',
                        action='store', type=str, dest='tem_name',
                        help='Camera configuration to load.')

    parser.add_argument('-t', '--tem',
                        action='store', type=str, dest='cam_name',
                        help='TEM configuration to load.')

    parser.set_defaults(
        simulate=False,
        tem_name=default_tem,
        cam_name=default_cam,
    )

    options = parser.parse_args()

    if options.simulate:
        config.settings.simulate = True

    ctrl = initialize(tem_name=options.tem_name, cam_name=options.cam_name)

    from IPython import embed
    embed(banner1='\nAssuming direct control.\n')
    ctrl.close()


if __name__ == '__main__':
    from IPython import embed
    ctrl = initialize()

    embed(banner1='\nAssuming direct control.\n')

    ctrl.close()
