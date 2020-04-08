import pytest


def test_stage(ctrl):
    pos = ctrl.stage.get()
    assert isinstance(pos, tuple)
    assert len(pos) == 5

    ctrl.stage.neutral()
    assert ctrl.stage.xy == (0, 0)
    assert ctrl.stage.z == 0
    assert ctrl.stage.a == 0
    assert ctrl.stage.b == 0


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
        deflector.xy = (0, 0)
        assert deflector.get() == (0, 0)


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
    lens.min()  # set to 0
    val = lens.get()
    assert isinstance(val, int)
    assert val == 0


if __name__ == '__main__':
    test_ctrl()

    from IPython import embed
    embed(banner1='')
