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
    return {"value": 123, "string": "test"}


@pytest.fixture(scope="session")
def temp_data_file(tmp_path_factory) -> str:
    return str(tmp_path_factory.mktemp("data", numbered=True) / "out.")


@pytest.mark.parametrize(
    ["format", "write_func", "with_header"],
    [
        ("tiff", formats.write_tiff, True),
        ("img", formats.write_cbf, True),
        ("cbf", formats.write_cbf, True),
        ("mrc", formats.write_mrc, False),
        ("smv", formats.write_adsc, True),
        ("img", formats.write_adsc, True),
        ("h5", formats.write_hdf5, True),
    ],
)
def test_write(format, write_func, with_header, data, header, temp_data_file):
    out = temp_data_file + format

    write_func(out, data, header if with_header else None)

    assert os.path.exists(out)


@pytest.mark.parametrize(
    ["format", "write_func", "alt"],
    [
        ("tif", formats.write_tiff, "tiff"),
        ("hdf5", formats.write_hdf5, "h5"),
    ],
)
def test_write_rename_ext(format, write_func, alt, data, header, temp_data_file):
    out = temp_data_file + "alt." + format
    out_alt = temp_data_file + "alt." + alt

    write_func(out, data, header)

    assert os.path.exists(out_alt)


@pytest.mark.depends(on=["test_write"])
@pytest.mark.parametrize(
    ["format", "raises"],
    [
        ("tiff", does_not_raise()),
        ("smv", does_not_raise()),
        ("img", does_not_raise()),
        ("h5", does_not_raise()),
        # Header is not supported
        ("mrc", pytest.raises(ValueError, match="Header mismatch")),
        ("cbf", pytest.raises(NotImplementedError)),
        ("invalid_extension", pytest.raises(OSError)),
        ("does_not_exist.h5", pytest.raises(FileNotFoundError)),
    ],
)
def test_read(format, raises, data, header, temp_data_file):
    with raises:
        out = temp_data_file + format

        img, h = formats.read_image(out)

        assert np.allclose(img, data)
        assert isinstance(h, dict)
        if not all(str(v) == str(h.get(k)) for k, v in header.items()):
            raise ValueError("Header mismatch")
