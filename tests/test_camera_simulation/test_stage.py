from __future__ import annotations

import pytest

from instamatic.camera.simulate.stage import Stage
from instamatic.camera.simulate.warnings import NotImplementedWarning


def test_init_default():
    s = Stage()


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
