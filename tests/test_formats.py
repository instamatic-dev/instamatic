from __future__ import annotations

import os
from contextlib import nullcontext as does_not_raise

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


@pytest.fixture(scope='module')
def temp_data_file(tmp_path_factory) -> str:
    return str(tmp_path_factory.mktemp('data', numbered=True) / 'out.')


@pytest.mark.parametrize(
    ['format', 'write_func', 'with_header'],
    [
        ('tiff', formats.write_tiff, True),
        ('cbf', formats.write_cbf, True),
        ('mrc', formats.write_mrc, False),
        ('smv', formats.write_adsc, True),
        ('img', formats.write_adsc, True),
        ('h5', formats.write_hdf5, True),
    ],
)
def test_write(format, write_func, with_header, data, header, temp_data_file):
    out = temp_data_file + format

    write_func(out, data, header if with_header else None)

    assert os.path.exists(out)


@pytest.mark.parametrize(
    ['format', 'write_func', 'alt'],
    [
        ('tif', formats.write_tiff, 'tiff'),
        ('hdf5', formats.write_hdf5, 'h5'),
    ],
)
def test_write_rename_ext(format, write_func, alt, data, header, temp_data_file):
    out = temp_data_file + 'alt.' + format
    out_alt = temp_data_file + 'alt.' + alt

    write_func(out, data, header)

    assert os.path.exists(out_alt)


@pytest.mark.parametrize(
    ['format', 'write_func', 'with_header', 'raises'],
    [
        ('tiff', formats.write_tiff, True, does_not_raise()),
        ('smv', formats.write_adsc, True, does_not_raise()),
        ('img', formats.write_adsc, True, does_not_raise()),
        ('h5', formats.write_hdf5, True, does_not_raise()),
        # Header is not supported
        ('mrc', formats.write_mrc, False, pytest.raises(ValueError, match='Header mismatch')),
        ('cbf', formats.write_cbf, True, pytest.raises(NotImplementedError)),
        ('invalid_extension', lambda *args: None, False, pytest.raises(OSError)),
        ('does_not_exist.h5', lambda *args: None, False, pytest.raises(FileNotFoundError)),
    ],
)
def test_read(format, write_func, with_header, raises, data, header, temp_data_file):
    # Generate file
    out = temp_data_file + format
    write_func(out, data, header if with_header else None)

    with raises:
        out = temp_data_file + format

        img, h = formats.read_image(out)

        assert np.allclose(img, data)
        assert isinstance(h, dict)

        # Check if the header we want is in the header we read
        if not all(str(v) == str(h.get(k)) for k, v in header.items()):
            raise ValueError('Header mismatch')
