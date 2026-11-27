from __future__ import annotations

import importlib
import logging

from instamatic import config

from .jobs import JOBS  # Import central list of jobs

logger = logging.getLogger(__name__)

all_modules = (
    'cred',
    'cred_tvips',
    'cred_fei',
    'fast_adt',
    'scan_ed',
    'sed',
    'autocred',
    'red',
    'machine_learning',
    'ctrl',
    'console',
    'debug',
    'about',
    'io',
)

try:
    modules = config.settings.modules
except AttributeError:
    modules = all_modules
finally:
    if 'io' not in modules:
        modules.insert(0, 'io')  # io is always needed
        modules = list(dict.fromkeys(modules))  # remove duplicates, but preserve order

MODULES = []

for module in modules:
    if module not in all_modules:
        raise AttributeError(f'No such module: `{module}`, must be in {all_modules}.')

    # import module for GUI
    lib = importlib.import_module('..' + module + '_frame', package=__name__)
    MODULES.append(lib.module)

    # try to import any associated jobs
    try:
        for job, function in lib.commands.items():
            if job in JOBS:
                logger.info(f'New job `{job}` already exists in `JOBS` listing!')
            else:
                JOBS[job] = function
    except AttributeError:
        print(f'No jobs from `{module}`!')
