from __future__ import annotations

import itertools
from typing import Iterable, Iterator, TypeVar

T = TypeVar('T')


def sawtooth(iterator: Iterable[T]) -> Iterator[T]:
    """Iterate elements of input sequence back and forth, repeating edges."""
    yield from itertools.cycle((seq := list(iterator)) + list(reversed(seq)))
