from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Optional, Type

import pytest

import instamatic._collections as ic
from tests.utils import InstanceAutoTracker


def test_no_overwrite_dict() -> None:
    """Should work as normal dict unless key exists, in which case raises."""
    nod = ic.NoOverwriteDict({1: 2})
    nod.update({3: 4})
    nod[5] = 6
    del nod[1]
    nod[1] = 6
    assert nod == {1: 6, 3: 4, 5: 6}
    with pytest.raises(KeyError):
        nod[1] = 2
    with pytest.raises(KeyError):
        nod.update({3: 4})


def test_null_logger(caplog) -> None:
    """NullLogger should void and not propagate messages to root logger."""

    messages = []
    handler = logging.StreamHandler()
    handler.emit = lambda record: messages.append(record.getMessage())
    null_logger = ic.NullLogger()
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    with caplog.at_level(logging.DEBUG):
        null_logger.debug('debug message that should be ignored')
        null_logger.info('info message that should be ignored')
        null_logger.warning('warning message that should be ignored')
        null_logger.error('error message that should be ignored')
        null_logger.critical('critical message that should be ignored')

    # Nothing should have been captured by pytest's caplog
    root_logger.removeHandler(handler)
    assert caplog.records == []
    assert caplog.text == ''
    assert messages == []


@dataclass
class PartialFormatterTestCase(InstanceAutoTracker):
    template: str = '{s} & {f:06.2f}'
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    returns: str = ''
    raises: Optional[Type[Exception]] = None


PartialFormatterTestCase(returns='{s} & {f:06.2f}')
PartialFormatterTestCase(kwargs={'s': 'Text'}, returns='Text & {f:06.2f}')
PartialFormatterTestCase(kwargs={'f': 3.1415}, returns='{s} & 003.14')
PartialFormatterTestCase(kwargs={'x': 'test'}, returns='{s} & {f:06.2f}')
PartialFormatterTestCase(kwargs={'f': 'Text'}, raises=ValueError)
PartialFormatterTestCase(template='{0}{1}', args=[5], returns='5{1}')
PartialFormatterTestCase(template='{0}{1}', args=[5, 6], returns='56')
PartialFormatterTestCase(template='{0}{1}', args=[5, 6, 7], returns='56')


@pytest.mark.parametrize('test_case', PartialFormatterTestCase.INSTANCES)
def test_partial_formatter(test_case) -> None:
    """Should replace only some {words}, but still fail if format is wrong."""
    c = test_case
    with pytest.raises(r) if (r := c.raises) else nullcontext():
        assert ic.partial_formatter.format(c.template, *c.args, **c.kwargs) == c.returns
