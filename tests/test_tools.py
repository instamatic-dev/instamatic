from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional, Type

import numpy as np
import pytest

import instamatic.tools as it
from tests.utils import InstanceAutoTracker


def test_prepare_grid_coordinates() -> None:
    g1 = [[-1, -1], [0, -1], [1, -1], [-1, 0], [0, 0], [1, 0], [-1, 1], [0, 1], [1, 1]]
    g2 = it.prepare_grid_coordinates(3, 3, 1)
    np.testing.assert_array_equal(np.array(g1), g2)


@dataclass
class XdsUntrustedAreaTestCase(InstanceAutoTracker):
    kind: str
    coords: list
    output_len: Optional[int] = None
    raises: Optional[Type[Exception]] = None


XdsUntrustedAreaTestCase('quadrilateral', [[1, 2]], output_len=28)
XdsUntrustedAreaTestCase('rectangle', [[1, 2], [3, 4]], output_len=28)
XdsUntrustedAreaTestCase('ellipse', [[1, 2], [3, 4]], output_len=26)
XdsUntrustedAreaTestCase('bollocks', [[[1, 2], [3, 4]]], raises=ValueError)


@pytest.mark.parametrize('test_case', XdsUntrustedAreaTestCase.INSTANCES)
def test_to_xds_untrusted_area(test_case: XdsUntrustedAreaTestCase) -> None:
    """Simple test, just confirm if runs and the output has correct size."""
    with pytest.raises(e) if (e := test_case.raises) else nullcontext():
        output = it.to_xds_untrusted_area(test_case.kind, test_case.coords)
        assert len(output) == test_case.output_len


def test_find_subranges() -> None:
    """Test for sub-ranges from consecutive numbers, pairs, and singletons."""
    input_list = [1, 2, 3, 7, 8, 10]
    output_list = list(it.find_subranges(input_list))
    assert output_list == [(1, 3), (7, 8), (10, 10)]


def test_relativistic_wavelength() -> None:
    assert it.relativistic_wavelength(voltage=120_000) == 0.033492
    assert it.relativistic_wavelength(voltage=200_000) == 0.025079
    assert it.relativistic_wavelength(voltage=300_000) == 0.019687
