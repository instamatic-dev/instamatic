from __future__ import annotations

import pytest

from instamatic.simulation.sample import Sample


def test_init():
    s = Sample(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert isinstance(s, Sample)


def test_range_might_contain_crystal():
    s = Sample(0, 0, 1, 0, 0, 0, 0)
    assert s.range_might_contain_crystal(-1, 1, -1, 1)
    assert not s.range_might_contain_crystal(9, 10, 9, 10)
    assert not s.range_might_contain_crystal(-10, -9, -10, -9)
    assert not s.range_might_contain_crystal(-10, -9, -10, 10)
    assert not s.range_might_contain_crystal(-10, 10, -10, -9)
    assert s.range_might_contain_crystal(0, 1, 0, 1)
    # TODO expand


@pytest.mark.xfail(reason='TODO')
def test_pixel_contains_crystal():
    assert False, 'TODO'


def test_range_might_contain_crystal_false_positive():
    s = Sample(0, 0, 1, 0, 0, 0, 0)
    x_min = 0.9
    x_max = 1
    y_min = 0.9
    y_max = 1
    assert s.range_might_contain_crystal(x_min, x_max, y_min, y_max)
    assert not s.pixel_contains_crystal(x_min, y_min)
    # TODO expand


@pytest.mark.xfail(reason='Need to figure out how this can be done')
def test_range_might_contain_crystal_false_negative():
    assert False, 'TODO'
