import os
from pathlib import Path

import pytest

# Actually importing the controller class breaks the tests
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from instamatic.TEMController.TEMController import TEMController


base_drc = Path(__file__).parent
os.environ['instamatic'] = str(base_drc.absolute())


def pytest_configure():
    pytest.TEST_DATA = Path(__file__).parent / 'test_data'


@pytest.fixture(scope='module')
def ctrl() -> "TEMController":
    from instamatic.TEMController import initialize
    ctrl = initialize()

    # set instant stage movement for testing
    ctrl.tem._set_instant_stage_movement()

    return ctrl
