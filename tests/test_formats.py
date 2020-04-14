import os

import numpy as np
import pytest

from instamatic import formats


@pytest.fixture()
def data():
    x, y = 64, 64
    arr = np.arange(x * y).reshape(x, y)
    return arr


@pytest.fixture()
def header():
    return {'value': 123, 'string': 'test'}


def test_tiff(data, header):
    out = 'out.tiff'

    formats.write_tiff(out, data, header)

    assert os.path.exists(out)

    img, h = formats.read_image(out)

    assert np.allclose(img, data)
    assert header == h


def test_cbf(data, header):
    out = 'out.cbf'

    formats.write_cbf(out, data, header)

    assert os.path.exists(out)

    # Reader Not implemented:
    with pytest.raises(NotImplementedError):
        img, h = formats.read_image(out)


def test_mrc(data, header):
    out = 'out.mrc'

    # Header not supported
    formats.write_mrc(out, data)

    assert os.path.exists(out)

    img, h = formats.read_image(out)

    assert np.allclose(img, data)
    assert isinstance(header, dict)


def test_smv(data, header):
    out = 'out.smv'

    formats.write_adsc(out, data, header)

    assert os.path.exists(out)

    img, h = formats.read_image(out)

    assert np.allclose(img, data)
    assert 'value' in h  # changes type to str
    assert h['string'] == header['string']


def test_hdf5(data, header):
    out = 'out.h5'

    formats.write_hdf5(out, data, header)

    assert os.path.exists(out)

    img, h = formats.read_image(out)

    assert np.allclose(img, data)
    assert header == h
