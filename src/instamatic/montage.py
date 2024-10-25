from __future__ import annotations

from pathlib import Path

import numpy as np
from pyserialem import Montage


class InstamaticMontage(Montage):
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
        from instamatic import config

        pixelsize = config.calibration[mode]['pixelsize'][magnification]

        stagematrix = config.calibration[mode]['stagematrix'][magnification]
        stagematrix = np.array(stagematrix).reshape(2, 2)

        self.set_pixelsize(pixelsize)
        self.set_stagematrix(stagematrix)
        self.mode = mode
        self.magnification = magnification

    @classmethod
    def from_montage_yaml(cls, filename: str = 'montage.yaml'):
        """Load montage from a series of tiff files + `montage.yaml`"""
        import yaml

        from instamatic.formats import read_tiff

        p = Path(filename)
        drc = p.parent

        d = yaml.safe_load(open(p))
        fns = (drc / fn for fn in d['filenames'])

        d['stagecoords'] = np.array(d['stagecoords'])
        d['stagematrix'] = np.array(d['stagematrix'])

        images = [read_tiff(fn)[0] for fn in fns]

        gridspec = {
            k: v for k, v in d.items() if k in ('gridshape', 'direction', 'zigzag', 'flip')
        }

        m = cls(images=images, gridspec=gridspec, **d)
        m.update_gridspec(flip=not d['flip'])  # BUG: Work-around for gridspec madness
        # Possibly related is that images are rotated 90 deg. in SerialEM mrc files

        return m

    def export(self, outfile: str = 'stitched.tiff') -> None:
        """Export the stitched image to a tiff file.

        Parameters
        ----------
        outfile : str
            Name of the image file.
        """
        from instamatic.formats import write_tiff

        write_tiff(outfile, self.stitched)

    def to_browser(self):
        from instamatic.browser import Browser

        browser = Browser(self)
        return browser
