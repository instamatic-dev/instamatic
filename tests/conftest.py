import os
from pathlib import Path

import pytest


base_drc = Path(__file__).parent
os.environ['instamatic'] = str(base_drc.absolute())


@pytest.fixture(scope='module')
def ctrl():
    from instamatic.TEMController import initialize
    ctrl = initialize()

    # set instant stage movement for testing
    ctrl.tem._set_instant_stage_movement()

    return ctrl
