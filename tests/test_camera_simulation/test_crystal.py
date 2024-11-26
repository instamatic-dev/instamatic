from __future__ import annotations

from typing import Type

import pytest

from instamatic.camera.simulate.crystal import (
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
    crystal.default()


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


def main():
    c = CubicCrystal(1)
    x, y, z = c.reciprocal_space_lattice(4).T

    import matplotlib
    from matplotlib import pyplot as plt

    matplotlib.use('QtAgg')

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_zlim(-5, 5)
    ax.set_aspect('equal')
    ax.scatter(x, y, z)
    ax.scatter(*c.a_star_vec, c='red', label='a', zorder=2)
    ax.scatter(*c.b_star_vec, c='green', label='b', zorder=2)
    ax.scatter(*c.c_star_vec, c='blue', label='c', zorder=2)
    plt.legend()
    plt.show()


if __name__ == '__main__':
    main()
