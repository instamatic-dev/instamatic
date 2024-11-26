from __future__ import annotations

import numpy as np
import pytest

from instamatic.camera.simulate.grid import Grid


def test_init():
    Grid()


def test_get_array():
    g = Grid(
        hole_width=9,
        bar_width=1,
    )
    arr = g.array(
        shape=(40, 40),
        x_min=g.grid_width_nm,
        x_max=3 * g.grid_width_nm,
        y_min=-4 * g.grid_width_nm,
        y_max=-2 * g.grid_width_nm,
    )

    # Grid
    assert np.all(arr[:, 0])
    assert np.all(arr[:, -1])
    assert np.all(arr[0, :])
    assert np.all(arr[-1, :])
    assert np.all(arr[:, 19])
    assert np.all(arr[:, 20])
    assert np.all(arr[19, :])
    assert np.all(arr[20, :])

    # Holes
    assert np.sum(arr[1:19, 1:19]) == 0
    assert np.sum(arr[1:19, 21:-1]) == 0
    assert np.sum(arr[21:-1, 1:19]) == 0
    assert np.sum(arr[21:-1, 21:-1]) == 0


@pytest.mark.xfail(reason='TODO')
def test_get_array_including_center():
    assert False, 'TODO'


@pytest.mark.xfail(reason='TODO')
def test_get_array_including_rim():
    assert False, 'TODO'
