from __future__ import annotations

from pathlib import Path

from instamatic import config


def get_new_work_subdirectory(stem='experiment', drc=None, number=1, mkdir=True):
    """Simple function to grab new empty working directory."""
    if not drc:
        drc = config.locations['work']
    else:
        drc = Path(drc)

    path = drc / f'{stem}_{number}'
    while path.exists():
        number += 1
        path = drc / f'{stem}_{number}'

    if mkdir:
        path.mkdir(exist_ok=True, parents=True)

    return path


def find_script(script: str):
    """Resolves the script name Looks in the local directory, absolute
    directory and in the scripts directory."""
    script = Path(script)

    if not script.exists():
        test_location = config.locations['scripts'] / script
        if not test_location.exists():
            raise OSError(f'No such script: {script}')
        else:
            script = test_location

    return script
