from __future__ import annotations

import pytest

from instamatic.simulation.stage import Stage
from instamatic.simulation.warnings import NotImplementedWarning


def test_init_default():
    s = Stage()
    assert isinstance(s, Stage)


def test_set_position():
    s = Stage()
    s.set_position(x=10)
    assert s.x == 10
    s.set_position(z=10)
    assert s.x == 10
    assert s.z == 10
    with pytest.warns(NotImplementedWarning):
        s.set_position(alpha_tilt=1)
    with pytest.warns(NotImplementedWarning):
        s.set_position(beta_tilt=1)
    with pytest.warns(NotImplementedWarning):
        s.set_position(x=1, y=1, z=1, alpha_tilt=1, beta_tilt=1)


@pytest.mark.xfail(reason='TODO')
def test_tilt():
    # Somehow check that the projected coordinates using stage.image_extent_to_sample_coordinates are correct
    assert False, 'TODO'


@pytest.mark.xfail(reason='TODO')
def test_image_rotation():
    # Image rotates with focus ect.
    assert False, 'TODO'
