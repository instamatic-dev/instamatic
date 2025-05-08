from __future__ import annotations

import numpy as np
import pytest


def test_setup(ctrl):
    from instamatic import controller

    ctrl2 = controller.get_instance()
    assert ctrl2 is ctrl


def test_other(ctrl):
    ctrl.spotsize = 1
    assert ctrl.spotsize == 1

    stagematrix = ctrl.get_stagematrix()
    assert stagematrix.shape == (2, 2)

    ctrl.store('test1')
    ctrl.restore('test1')

    ctrl.mode.set('diff')
    ctrl.store_diff_beam()

    ctrl.mode.set('mag1')
    with pytest.raises(Exception):
        ctrl.store_diff()


def test_stage(ctrl):
    stage = ctrl.stage

    pos = stage.get()
    assert isinstance(pos, tuple)
    assert len(pos) == 5

    stage.neutral()
    assert stage.xy == (0, 0)

    stage.x = 100
    assert stage.x == 100
    stage.y = -100
    assert stage.y == -100
    stage.z = 10
    assert stage.z == 10
    stage.a = 1
    assert stage.a == 1
    stage.b = -1
    assert stage.b == -1

    stage.xy = (0, 0)
    assert stage.xy == (0, 0)

    stage.set_a_with_speed(45, speed=12, wait=True)
    assert not stage.is_moving()

    assert stage.a == 45

    stage.set(x=0, y=0, z=0)
    stage.move_in_projection(delta_x=1000, delta_y=1000)

    assert abs(stage.y) + abs(stage.z) == 1414  # round(np.sqrt(2) * 1000)
    assert stage.x == 1000

    stage.set(x=0, y=0, z=0)
    stage.move_along_optical_axis(delta_z=1000)
    assert abs(stage.y) + abs(stage.z) == 1414  # round(np.sqrt(2) * 1000)

    stage.xy = (0, 0)
    stage.move_xy_with_backlash_correction(shift_x=100, shift_y=100)
    assert stage.xy == (100, 100)
    stage.move_xy_with_backlash_correction(shift_x=-100, shift_y=-100)
    assert stage.xy == (0, 0)

    stage.eliminate_backlash_a()
    stage.eliminate_backlash_xy()

    with pytest.raises(TypeError):
        stage.set('rawr')


def test_deflectors(ctrl):
    for deflector in (
        ctrl.guntilt,
        ctrl.beamshift,
        ctrl.beamtilt,
        ctrl.diffshift,
        ctrl.imageshift1,
        ctrl.imageshift2,
    ):
        val = deflector.get()
        assert len(val) == 2
        assert isinstance(val, tuple)

        deflector.x = 100
        deflector.y = 200
        assert deflector.x == 100
        assert deflector.y == 200
        assert deflector.xy == (100, 200)

        deflector.xy = (10, 20)
        assert deflector.xy == (10, 20)

        deflector.neutral()

    with pytest.raises(TypeError):
        deflector.set('rawr')


def test_magnification(ctrl):
    lens = ctrl.magnification

    lens.index = 0
    assert lens.index == 0
    lens.increase()
    assert lens.index == 1
    mag = lens.value
    assert isinstance(mag, int)

    lens.decrease()
    assert lens.index == 0
    lens.set(mag)
    assert lens.index == 1

    assert isinstance(lens.absolute_index, int)

    with pytest.raises(ValueError):
        lens.set(-1)

    ranges = lens.get_ranges()
    assert isinstance(ranges, dict)
    assert 'lowmag' in ranges
    assert 'mag1' in ranges
    assert 'diff' in ranges


def test_difffocus(ctrl):
    lens = ctrl.difffocus

    ctrl.mode.set('mag1')
    with pytest.raises(ValueError):
        val = lens.get()

    ctrl.mode.set('diff')

    lens.value = 0
    val = lens.get()
    assert isinstance(val, int)
    assert val == 0

    defocus_val = 1500
    lens.defocus(defocus_val)
    assert lens.value == defocus_val
    assert lens.is_defocused
    lens.refocus()
    assert lens.value == 0
    assert not lens.is_defocused

    ctrl.mode.set('mag1')


def test_brightness(ctrl):
    lens = ctrl.brightness
    lens.max()  # set to max
    lens.min()  # set to 0
    val = lens.get()
    assert isinstance(val, int)
    assert val == 0

    lens.value = 100
    assert lens.value == 100


def test_beam(ctrl):
    beam = ctrl.beam
    unblanked = 'unblanked'

    beam.unblank()
    assert beam.get() == unblanked

    beam.blank()
    assert beam.is_blanked

    with beam.blanked():
        assert beam.is_blanked

    with beam.unblanked():
        assert not beam.is_blanked

    beam.set(unblanked)
    assert beam.state == unblanked

    with pytest.raises(ValueError):
        beam.set('rawr')


def test_mode(ctrl):
    mode = ctrl.mode

    mode.set('diff')
    assert mode == 'diff'
    mode.set('lowmag')
    assert mode == 'lowmag'

    mode.set('mag1')
    assert mode == 'mag1'

    with pytest.raises(ValueError):
        mode.set('rawr')


def test_screen(ctrl):
    screen = ctrl.screen

    screen.down()
    screen.up()
    assert screen.is_up

    screen.down()
    assert screen.get() == 'down'
    assert screen.get() != 'up'

    with pytest.raises(ValueError):
        screen.set('rawr')


def test_align_to(ctrl):
    reference = ctrl.get_raw_image()
    pos = ctrl.stage.xy

    shift = ctrl.align_to(reference, apply=True)

    assert len(shift) == 2
    assert pos != ctrl.stage.xy


if __name__ == '__main__':
    test_ctrl()

    from IPython import embed

    embed(banner1='')
