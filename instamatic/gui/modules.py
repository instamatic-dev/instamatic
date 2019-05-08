import importlib
from instamatic import config

all_modules = ( 'cred', 'cred_tvips', 'cred_fei', 'sed', 
                'autocred', 'red', 'machine_learning', 
                'ctrl', 'debug', 'about', 'io' )

try:
    modules = config.cfg.modules
except AttributeError:
    modules = []
else:
    modules.append('io')  # io is always needed
    modules = list(dict.fromkeys(modules))  # remove duplicates, but preserve order

if not modules:
    modules = all_modules

MODULES = []

for module in modules:
    if module not in all_modules:
        raise AttributeError(f'No such module: `{module}`, must be in {all_modules}.')

    lib = importlib.import_module('..' + module + '_frame', package=__name__)
    MODULES.append(lib.module)
