from __future__ import annotations

import datetime
import logging
import os
import pprint
import sys
from pathlib import Path
from typing import Callable

import instamatic
from instamatic import config


def locate(name, show=False):
    """Locate the directory given by `name`

    Parameters
    ----------
    name : str
    show : bool
        Open the directory in `File Explorer`

    Returns
    -------
    drc : pathlib.Path
    """
    try:
        drc = config.locations[name]
    except KeyError:
        raise ValueError(f'No such directory: `{name}`')

    if show:
        try:
            os.startfile(drc)
        except FileNotFoundError:
            os.startfile(drc.parent)
    else:
        print(drc)

    return Path(drc)


def show_info():
    """Show info about the current instamatic installation."""
    print('\n# Version')
    print(f'{instamatic.__version__}')

    print('\n# Locations')
    for name, value in config.locations.items():
        print(f' - ({name}) {value}')

    print('\n# Config files')
    print(f' - {config.settings.location}')
    print(f' - {config.defaults.location}')
    print(f' - {config.camera.location}')
    print(f' - {config.microscope.location}')
    print(f' - {config.calibration.location}')

    print('\n# settings.yaml')
    pprint.pprint(config.settings.mapping)  # py37
    # pprint.pprint(config.settings.mapping, sort_dicts=True)  # py38


def main():
    import argparse

    description = """Start instamatic with various functions (see below). If no arguments are given, start the instamatic GUI. The GUI is modular and can be defined using the config system. The GUI can be used to control the microscope and run the experiments. The GUI itself is further described on the GUI page."""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-s', '--script', action='store', type=str, dest='script', help='Run the script given'
    )

    parser.add_argument(
        '-n',
        '--nav',
        action='store',
        type=str,
        dest='nav_file',
        help='Load the given .nav file',
    )

    parser.add_argument(
        '-a',
        '--acquire_at_items',
        action='store_true',
        dest='acquire_at_items',
        help='Run the script file `--script` at every point marked with `Acquire` in the nav file `--nav`.',
    )

    parser.add_argument(
        '-l',
        '--locate',
        action='store',
        type=str,
        dest='locate',
        help="Locate a requested directory and exit, i.e. `config`, `data`, `scripts`, `base`, 'work`, `logs`",
    )

    parser.add_argument(
        '-o',
        '--open',
        action='store',
        type=str,
        dest='show',
        help='Open the requested directory and exit, see `--locate`.',
    )

    parser.add_argument(
        '-i',
        '--info',
        action='store_true',
        dest='info',
        help='Show info about the current instamatic installation.',
    )

    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        dest='verbose',
        help='Write debug messages of instamatic (-v) and other imported packages (-vv) to the log',
        default=0,
    )

    parser.set_defaults(
        script=None,
        acquire_at_items=False,
        nav_file=None,
        start_gui=True,
        locate=None,
        show=False,
        info=False,
    )

    options = parser.parse_args()

    if options.locate:
        locate(options.locate)
        exit()
    if options.show:
        locate(options.show, show=True)
        exit()
    if options.info:
        show_info()
        exit()

    from instamatic.utils import high_precision_timers

    high_precision_timers.enable()  # sleep timers with 1 ms resolution

    # enable faster switching between threads
    sys.setswitchinterval(0.001)  # seconds

    from instamatic import banner

    banner.register_thank_you_message()

    from instamatic import config

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_{date}.log'

    def log_filter_factory(verbosity: int) -> Callable[[logging.LogRecord], bool]:
        instamatic_logging_level = logging.DEBUG if verbosity >= 1 else logging.INFO
        imported_logging_level = logging.DEBUG if verbosity >= 2 else logging.INFO

        def log_filter_function(r: logging.LogRecord) -> bool:
            if r.name.startswith('instamatic') or r.name == '__main__':
                return r.levelno >= instamatic_logging_level
            else:
                return r.levelno >= imported_logging_level

        return log_filter_function

    log_main = logging.getLogger()
    log_main.setLevel(logging.DEBUG)
    log_detail = 'module' if options.verbose <= 2 else 'pathname'
    log_format = f'%(asctime)s | %({log_detail})s:%(lineno)s | %(levelname)s | %(message)s'
    log_handler = logging.FileHandler(logfile)
    log_handler.setFormatter(logging.Formatter(log_format))
    log_handler.addFilter(log_filter_factory(verbosity=options.verbose))
    log_main.addHandler(log_handler)

    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    log.info(f'Instamatic started: {repr(options.__dict__)}')

    from instamatic import controller

    ctrl = controller.initialize(stream=True)

    if options.nav_file:
        from pyserialem import read_nav_file

        nav_items = read_nav_file(options.nav_file, acquire_only=True)

    if options.acquire_at_items:
        ctrl.run_script_at_items(nav_items=nav_items, script=options.script)
    elif options.script:
        ctrl.run_script(options.script)
    elif options.start_gui:
        from instamatic.gui import start_gui

        start_gui(ctrl, log=log)


if __name__ == '__main__':
    main()
