from __future__ import annotations

from collections import UserDict
from typing import Any, Dict, Tuple


class KeyOverwriteError(KeyError):
    pass


class NoOverwriteDict(UserDict):
    """A dictionary that doesn't allow overwriting existing items."""

    KEY_OVERWRITE_MSG = 'Item "{key}" is already set and cannot be overwritten.'

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self.data:
            raise KeyOverwriteError(self.KEY_OVERWRITE_MSG.format(**locals()))
        super().__setitem__(key, value)


class SubclassRegistryMeta(type):
    """Metaclass which automatically registers all subclasses of its class."""

    def __init__(
        cls,
        name: str,
        bases: Tuple[type, ...],
        class_dict: Dict[str, Any],
    ) -> None:
        super().__init__(name, bases, class_dict)
        if not hasattr(cls, 'REGISTRY'):
            cls.REGISTRY = NoOverwriteDict()
        if bases:  # Avoid registering the base class itself
            cls.REGISTRY[name] = cls
