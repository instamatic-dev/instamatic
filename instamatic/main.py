import datetime
import logging
import os
import sys

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
    if name == 'base':
        drc = config.base_drc
    elif name == 'config':
        drc = config.config_drc
    elif name == 'logs':
        drc = config.logs_drc
    elif name == 'scripts':
        drc = config.scripts_drc
    elif name == 'work':
        drc = config.settings.work_directory
    elif name == 'data':
        drc = config.settings.data_directory
    else:
        raise ValueError(f'No such directory: `{name}`')

    if show:
        try:
            os.startfile(drc)
        except FileNotFoundError:
            os.startfile(drc.parent)
    else:
        print(drc)

    return drc


def main():
    import argparse

    description = ''
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-s', '--script',
                        action='store', type=str, dest='script',
                        help='Run the script given')

    parser.add_argument('-n', '--nav',
                        action='store', type=str, dest='nav_file',
                        help='Load the given .nav file')

    parser.add_argument('-a', '--acquire_at_items',
                        action='store_true', dest='acquire_at_items',
                        help='Run the script file `--script` at every point marked with `Acquire` in the nav file `--nav`.')

    parser.add_argument('-l', '--locate',
                        action='store', type=str, dest='locate',
                        help="Locate a requested directory and exit, i.e. `config`, `data`, `scripts`, `base`, 'work`, `logs`")

    parser.add_argument('-o', '--open',
                        action='store', type=str, dest='show',
                        help='Open the requested directory and exit, see `--locate`.')

    parser.set_defaults(script=None,
                        acquire_at_items=False,
                        nav_file=None,
                        start_gui=True,
                        locate=None,
                        show=False,
                        )

    options = parser.parse_args()

    if options.locate:
        locate(options.locate)
        exit()
    if options.show:
        locate(options.show, show=True)
        exit()

    from instamatic.utils import high_precision_timers
    high_precision_timers.enable()  # sleep timers with 1 ms resolution

    # enable faster switching between threads
    sys.setswitchinterval(0.001)  # seconds

    from instamatic import version
    version.register_thank_you_message()

    from instamatic import config

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.logs_drc / f'instamatic_{date}.log'

    logging.basicConfig(format='%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s',
                        filename=logfile,
                        level=logging.DEBUG)

    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    log.info(f'Instamatic started: {repr(options.__dict__)}')

    from instamatic import TEMController
    ctrl = TEMController.initialize(stream=True)

    if options.nav_file:
        from instamatic.serialem import read_nav_file
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
