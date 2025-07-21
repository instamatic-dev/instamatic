from __future__ import annotations

import contextlib
import string
import time
from collections import UserDict
from typing import Any, Callable, Tuple


class NoOverwriteDict(UserDict):
    """A dictionary that doesn't allow overwriting existing values."""

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self.data:
            raise KeyError(f'Key "{key}" already exists and cannot be overwritten.')
        super().__setitem__(key, value)


class PartialFormatter(string.Formatter):
    """`str.format` alternative, allows for partial replacement of {fields}"""

    def __init__(self, missing: str = '{{{}}}') -> None:
        super().__init__()
        self.missing: str = missing  # used instead of missing values

    def get_field(self, field_name: str, args, kwargs) -> Tuple[Any, str]:
        """When field can't be found, return placeholder text instead."""
        try:
            obj, used_key = super().get_field(field_name, args, kwargs)
            return obj, used_key
        except (KeyError, AttributeError, IndexError, TypeError):
            return self.missing.format(field_name), field_name

    def format_field(self, value: Any, format_spec: str) -> str:
        """If the field was not found, format placeholder as string instead."""
        try:
            return super().format_field(value, format_spec)
        except (ValueError, TypeError):
            return str(value)


partial_formatter = PartialFormatter()


@contextlib.contextmanager
def timer() -> Callable[[], float]:
    """Returns a callable with time it took to run wrapped code in seconds."""
    t1 = t2 = time.perf_counter()
    yield lambda: t2 - t1
    t2 = time.perf_counter()
