from __future__ import annotations

from typing import Type

import pytest

from instamatic.simulation.crystal import (
    Crystal,
    CubicCrystal,
    HexagonalCrystal,
    MonoclinicCrystal,
    OrthorhombicCrystal,
    TetragonalCrystal,
    TriclinicCrystal,
    TrigonalCrystal,
)


def test_crystal_init():
    Crystal(1, 1, 1, 1, 1, 1)


@pytest.mark.parametrize(
    'crystal',
    [
        Crystal,
        CubicCrystal,
        HexagonalCrystal,
        TrigonalCrystal,
        TetragonalCrystal,
        OrthorhombicCrystal,
        MonoclinicCrystal,
        TriclinicCrystal,
    ],
)
def test_crystal_default(crystal: Type[Crystal]):
    c = crystal.default()
    assert isinstance(c, Crystal)


def test_get_lattice_cubic():
    c = CubicCrystal.default()
    lat = c.real_space_lattice(1)
    assert pytest.approx(lat) == [
        (-1, -1, -1),
        (-1, -1, 0),
        (-1, -1, 1),
        (-1, 0, -1),
        (-1, 0, 0),
        (-1, 0, 1),
        (-1, 1, -1),
        (-1, 1, 0),
        (-1, 1, 1),
        (0, -1, -1),
        (0, -1, 0),
        (0, -1, 1),
        (0, 0, -1),
        (0, 0, 0),
        (0, 0, 1),
        (0, 1, -1),
        (0, 1, 0),
        (0, 1, 1),
        (1, -1, -1),
        (1, -1, 0),
        (1, -1, 1),
        (1, 0, -1),
        (1, 0, 0),
        (1, 0, 1),
        (1, 1, -1),
        (1, 1, 0),
        (1, 1, 1),
    ]
    lat = c.reciprocal_space_lattice(1)
    assert pytest.approx(lat) == [
        (-1, -1, -1),
        (-1, -1, 0),
        (-1, -1, 1),
        (-1, 0, -1),
        (-1, 0, 0),
        (-1, 0, 1),
        (-1, 1, -1),
        (-1, 1, 0),
        (-1, 1, 1),
        (0, -1, -1),
        (0, -1, 0),
        (0, -1, 1),
        (0, 0, -1),
        (0, 0, 0),
        (0, 0, 1),
        (0, 1, -1),
        (0, 1, 0),
        (0, 1, 1),
        (1, -1, -1),
        (1, -1, 0),
        (1, -1, 1),
        (1, 0, -1),
        (1, 0, 0),
        (1, 0, 1),
        (1, 1, -1),
        (1, 1, 0),
        (1, 1, 1),
    ]
