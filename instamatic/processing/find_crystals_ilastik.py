import sys
from pathlib import Path

import predicrystal
import yaml

from instamatic import config
from instamatic.config import defaults


def make_map_scale_ind_yaml(fn: str = 'MapScaleInd.yaml'):
    """Generate `MapScaleInd.yaml` for `predicrystal`."""
    mag_ranges = config.microscope.ranges
    combined_range = mag_ranges['lowmag'] + mag_ranges['mag1']
    mapping = {i + 1: mag for (i, mag) in enumerate(combined_range)}

    yaml.dump(mapping, stream=open(fn, 'w'))
    print(f'Wrote file `{fn}`')


class CrystalFinder:
    """Find crystals using models trained in Ilastik using code developed here:
    https://gitlab.tudelft.nl/aj-lab/predicrystal.

    Parameters
    ----------
    nav: str
        Nav file from SerialEM containing the image metadata.
    mrc: str
        Image data in mrc format corresponding to the `.nav file`.
    """

    def __init__(self, nav: str, mrc: str):
        super().__init__()

        self.nav = Path(nav).absolute()
        self.mrc = Path(mrc).absolute()
        self.work_directory = self.nav.parent

        for fn in self.nav, self.mrc:
            if not fn.exists():
                raise OSError(f'`{fn}` does not exist!')

    def write_metadata(self, fn='settings.yaml', drc='.'):
        """Store metadata to a yaml file.

        Used for compatibility with `predicrystal`. `fn` is the
        filename, and `drc` the directory to store it in.
        """
        drc = Path(drc)
        with open(drc / fn, 'w') as f:
            yaml.dump(self.metadata, stream=f)

    def convert_to_tiff(self, classifier):
        """Convert mrc file to tiff files compatible with `Ilastik`"""
        metadata = predicrystal.generate_test_data(
            nav=self.nav,
            mrc=self.mrc,
            classifier=classifier,
        )
        self.metadata = metadata

        self.scaling_factor = metadata['scaling factor']
        self.im_size = metadata['image size']
        self.nav_file = Path(metadata['nav file'])
        self.mrc_file = Path(metadata['mrc file'])
        self.tiff_folder = Path(metadata['tiff folder'])

        self.write_metadata()

    def run_ilastik(self, classifier):
        """Run the Ilastik classifiers (pixel / object)."""
        tiff_folder = self.tiff_folder
        mrc_folder = self.mrc_file.parent

        output_folder = predicrystal.run_classifiers(
            tiff_folder=tiff_folder,
            mrc_folder=mrc_folder,
            classifier=classifier,
        )

        self.metadata['output folder'] = str(output_folder)
        self.output_folder = output_folder

        self.write_metadata()

    def results_to_nav(
        self,
        filter_distance: float = 2.0,
    ):
        """Conver the `Ilastik` results to a new `.nav` file that can be read
        by SerialEM.

        `filter_distance` is the minimum accepted distance in
        micrometers between particles.
        """

        csv_folder = self.output_folder
        scaling_factor = self.scaling_factor
        im_size = self.im_size
        nav_file = self.nav_file  # Open the nav file which can be used as a template
        mrc_file = self.mrc_file

        predicrystal.results_to_nav(
            csv_folder=csv_folder,
            nav_file=nav_file,
            mrc_file=mrc_file,
            scaling_factor=scaling_factor,
            min_sep=filter_distance,
            im_size=im_size,
        )


def remove_argument(parser: object, arg: str) -> None:
    """Remove argument from argument parser."""
    for action in parser._actions:
        if action.dest == arg:
            parser._remove_action(action)

    for group in parser._action_groups:
        for action in group._group_actions:
            if action.dest == arg:
                group._group_actions.remove(action)
                return


def main_entry():
    import argparse
    from predicrystal import parsers

    # Re-use parsers from `predicrystal`
    parents = (
        parsers.test_data_parser(add_help=False),
        # parsers.project_file_parser(add_help=False),
        parsers.output_parser(add_help=False),
    )

    description = """Find crystals in images using Ilastik.

Takes a `.nav` file and `.mrc` file as input.
Performs pixel and object classification using the Ilastik interface in
[predicrystal](https://gitlab.com/aj-lab/predicrystal). Crystals are
filtered by their distance. The resulting data is stored in a new `.nav`
file compatible with `SerialEM` or `Instamatic`."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=parents)

    parser.add_argument(
        '--mapscaleind',
        action='store_true', dest='generate_map_scale_ind',
        help='Generate `MapScaleInd.yaml` for `predicrystal` from config.')

    parser.set_defaults(
        generate_map_scale_ind=False,
        classifier=defaults.predicrystal['classifier'],
        filter_distance=defaults.predicrystal['filter_distance'],
    )

    # hide not implemented arguments
    not_implemented = ('training', 'project_path', 'list_classifiers')
    for arg in not_implemented:
        remove_argument(parser, arg)

    options = parser.parse_args()

    if options.generate_map_scale_ind:
        make_map_scale_ind_yaml()
        sys.exit()

    # Run program
    cf = CrystalFinder(
        nav=options.nav_location,
        mrc=options.mrc_location,
    )

    cf.convert_to_tiff(classifier=options.classifier)

    cf.run_ilastik(classifier=options.classifier)

    cf.results_to_nav(
        filter_distance=options.filter_distance,
    )


if __name__ == '__main__':
    main_entry()
    # nav = 'nav.nav'
    # mrc = 'mmm.mrc'

    # cf = CrystalFinder(nav=nav, mrc=mrc)
    # cf.convert_to_tiff()
    # cf.run_ilastik()
    # cf.results_to_nav()
