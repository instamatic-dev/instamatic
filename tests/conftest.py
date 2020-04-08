import os
from pathlib import Path

import pytest


base_drc = Path(__file__).parent
os.environ['instamatic'] = str(base_drc.absolute())


@pytest.fixture(scope='module')
def ctrl():
    from instamatic.TEMController import initialize
    ctrl = initialize()
    return ctrl
