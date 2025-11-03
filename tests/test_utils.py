from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional, Type, Union

import pytest

from instamatic.utils.domains import NumericDomain
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
