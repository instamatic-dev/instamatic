from __future__ import annotations

import re
from collections import UserString
from dataclasses import dataclass
from typing import Any, Literal

from typing_extensions import Self, TypeAlias

FieldKind: TypeAlias = Literal['region', 'line', 'scan', 'frame']


class SaveName(UserString):
    """Handles frame/buffer naming conventions throughout the ScanED module."""

    @dataclass
    class Field:
        name: FieldKind
        prefix: str
        format: str
        typ: type

    fields = [
        Field(name='region', prefix='r', format=':02d', typ=int),
        Field(name='line', prefix='l', format=':04d', typ=int),
        Field(name='scan', prefix='s', format=':02d', typ=int),
        Field(name='frame', prefix='f', format=':04d', typ=int),
    ]

    def __init__(self, seq: Any = ''):
        super().__init__(seq)

    def append(self, *args, **kwargs) -> Self:
        """Append new '_{prefix}{format} fields from args & kwargs to self."""
        if not args and not kwargs:
            return self
        fields = {f.name: f for f in self.fields if f.name not in self.as_dict()}
        if kwargs:
            key, value = kwargs.popitem()
            field = fields[key]  # noqa - field names must be FieldKind literals
        else:  # if args:
            field = list(fields.values())[0]  # first unused field
            value, args = args[0], args[1:]
        return self._append(field, value).append(*args, **kwargs)

    def _append(self, field: Field, value: Any) -> Self:
        """Append."""
        suffix = '_' + field.prefix + '{' + field.format + '}'
        return self.__class__(self + suffix.format(field.typ(value)))

    def as_dict(self) -> dict[FieldKind, Any]:
        """Parse self and return as a {field.name: field.value} dictionary."""
        fields = {f.prefix: f for f in self.fields}
        d = {}
        for g1, g2 in re.findall(r'([a-z])(\d+)', self.data):
            field = fields[g1]
            d[field.name] = field.typ(g2)
        return d

    def as_list(self) -> Any:
        """Parse self and return as a list of present field values in order."""
        d = self.as_dict()
        return [d[f.name] for f in self.fields if f.name in d]
