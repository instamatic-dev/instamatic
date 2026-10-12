from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional, Type, Union

import numpy as np
import pytest

from instamatic.utils.domains import NumericDomain
from instamatic.utils.native import AnyNumber, NativeNumber, native
from instamatic.utils.pairing import hulam2uv, ij2ulam, ulam2ij, uv2hulam
from tests.utils import InstanceAutoTracker


@dataclass
class NumericDomainTestCase(InstanceAutoTracker):
    kwargs: dict[str, Union[float, tuple[float, ...]]]
    raises: Optional[Type[Exception]] = None
    returns: Optional[float] = None


NumericDomainTestCase(kwargs=dict(options=(31, 32, 33)), returns=33)
NumericDomainTestCase(kwargs=dict(options=(41, 42, 43)), returns=42)
NumericDomainTestCase(kwargs=dict(options=(51, 52, 53)), returns=51)
NumericDomainTestCase(kwargs=dict(options=(41, 43, 44)), returns=41)
NumericDomainTestCase(kwargs=dict(options=(44, 43, 40)), returns=43)
NumericDomainTestCase(kwargs=dict(lower_lim=31, upper_lim=34), returns=34)
NumericDomainTestCase(kwargs=dict(lower_lim=41, upper_lim=44), returns=42)
NumericDomainTestCase(kwargs=dict(lower_lim=51, upper_lim=54), returns=51)
NumericDomainTestCase(kwargs=dict(lower_lim=51, options=(31, 32)), raises=ValueError)
NumericDomainTestCase(kwargs=dict(), raises=ValueError)


@pytest.mark.parametrize('test_case', NumericDomainTestCase.INSTANCES)
def test_float_domain(test_case) -> None:
    """Assert a `FloatDomain` subclass is initialized and works correctly."""
    c = test_case
    with pytest.raises(r) if (r := c.raises) else nullcontext():
        assert NumericDomain(**c.kwargs).nearest(to=42) == c.returns


@dataclass
class NativeTestCase(InstanceAutoTracker):
    input_value: AnyNumber
    output_type: Type[NativeNumber]


NativeTestCase(input_value=np.float64(1.23), output_type=float)
NativeTestCase(input_value=np.int64(1), output_type=int)
NativeTestCase(input_value=float(1.23), output_type=float)
NativeTestCase(input_value=int(1), output_type=int)


@pytest.mark.parametrize('test_case', NativeTestCase.INSTANCES)
def test_native(test_case) -> None:
    """Assert `native` always returns numpy native NativeNumber types."""
    assert isinstance(native(test_case.input_value), test_case.output_type)


# 2D coordinates of the first nine Ulam (u9) and hexagonal Ulam (h9) points:
u9 = [(0, 0), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
h9 = [(0, 0), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1), (2, -1), (2, 0)]


def test_ulam_regular():
    for ulam_index, ij_coords in enumerate(u9):
        assert ulam_index == ij2ulam(*ij_coords)
        assert ij_coords == ulam2ij(ulam_index)
    for ulam_index in range(100):
        assert ij2ulam(*ulam2ij(ulam_index)) == ulam_index


def test_ulam_hexagonal():
    for hulam_index, uv_coords in enumerate(h9):
        assert hulam_index == uv2hulam(*uv_coords)
        assert uv_coords == hulam2uv(hulam_index)
    for hulam_index in range(100):
        assert uv2hulam(*hulam2uv(hulam_index)) == hulam_index
