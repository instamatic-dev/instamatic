from __future__ import annotations

import logging
import string
from collections import UserDict
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Iterator, TypeVar

T1 = TypeVar('T1')
T2 = TypeVar('T2')


class NoOverwriteDict(UserDict):
    """A dictionary that doesn't allow overwriting existing values."""

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self.data:
            raise KeyError(f'Key "{key}" already exists and cannot be overwritten.')
        super().__setitem__(key, value)


class NullLogger(logging.Logger):
    """A logger mock that ignores all logging, to be used in headless mode."""

    def __init__(self, name='null'):
        super().__init__(name)
        self.addHandler(logging.NullHandler())
        self.propagate = False


class PartialFormatter(string.Formatter):
    """`str.format` alternative, allows for partial replacement of {fields}"""

    @dataclass(frozen=True)
    class Missing:
        name: str

    def __init__(self, missing: str = '{{{}}}') -> None:
        super().__init__()
        self.missing: str = missing  # used instead of missing values

    def get_field(self, field_name: str, args, kwargs) -> tuple[Any, str]:
        """When field can't be found, return placeholder text instead."""
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError, IndexError, TypeError):
            return PartialFormatter.Missing(field_name), field_name

    def format_field(self, value: Any, format_spec: str) -> str:
        """If the field was not found, format placeholder as string instead."""
        if isinstance(value, PartialFormatter.Missing):
            if format_spec:
                return self.missing.format(f'{value.name}:{format_spec}')
            return self.missing.format(f'{value.name}')
        return super().format_field(value, format_spec)


partial_formatter = PartialFormatter()


class VersionedDict(MutableMapping[T1, T2]):
    """A dict whose version changes with every mutation; useful for caching."""

    def __init__(self, d: dict = None) -> None:
        self._d: dict[T1, T2] = d or {}
        self.version = 0

    def __getitem__(self, k: T1) -> T2:
        return self._d[k]

    def __iter__(self) -> Iterator[T1]:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __setitem__(self, k, v) -> None:
        self._d[k] = v
        self.version += 1

    def __delitem__(self, k) -> None:
        del self._d[k]
        self.version += 1
