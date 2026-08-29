from __future__ import annotations

import itertools
from typing import Iterable, Iterator, TypeVar

T = TypeVar('T')


def pairwise(iterable: Iterable[T], closed: bool = False) -> Iterator[tuple[T, T]]:
    """Yield pairs of subsequent iterable elements: 'abc' -> (a, b), (b, c)"""
    iterator = iter(iterable)
    first = left = next(iterator, None)
    for right in iterator:
        yield left, right
        left = right
    if closed and first is not None:
        yield left, first


def sawtooth(iterator: Iterable[T]) -> Iterator[T]:
    """Iterate elements of input sequence back and forth, repeating edges."""
    yield from itertools.cycle((seq := list(iterator)) + list(reversed(seq)))
