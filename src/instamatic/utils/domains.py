from __future__ import annotations

from abc import ABC, abstractmethod
from bisect import bisect_left
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar, Union, overload

from typing_extensions import Self

Numeric = TypeVar('Numeric', int, float)


@dataclass(frozen=True)
class NumericDomain(Generic[Numeric], ABC):
    """Base class for numeric domains and nearest-value lookup."""

    def __new__(cls, *args, **kwargs) -> Self:
        """Init subclass based on kwargs, as needed to save/load calib@yaml."""
        if cls is not NumericDomain:
            return super().__new__(cls)  # avoids circular __new__
        if (sk := set(kwargs.keys())) == {'lower_lim', 'upper_lim'}:
            return NumericDomainConstrained(**kwargs)
        elif sk == {'options'}:
            return NumericDomainDiscrete(**kwargs)
        raise ValueError('Kwargs must be {lower_lim, upper_lim} or {options}, not ' + str(sk))

    @abstractmethod
    def nearest(self, to: Numeric) -> Union[Numeric, float]:
        """Return the nearest value in the domain to `to`."""


@dataclass(frozen=True)
class NumericDomainConstrained(NumericDomain[Numeric]):
    """Continuous numeric domain limited to [lower_lim, upper_lim]."""

    lower_lim: Numeric
    upper_lim: Numeric

    @overload
    def nearest(self, to: int) -> Numeric: ...

    @overload
    def nearest(self, to: float) -> float: ...

    def nearest(self, to: float) -> Union[Numeric, float]:
        return max(self.lower_lim, min(self.upper_lim, to))


@dataclass(frozen=True)
class NumericDomainDiscrete(NumericDomain[Numeric]):
    """Discrete numeric domain with a finite sequence of allowed values."""

    options: Sequence[Numeric]

    def __post_init__(self):
        object.__setattr__(self, 'options', tuple(sorted(self.options)))

    def nearest(self, to: float) -> Numeric:
        i = bisect_left(self.options, to)
        if i == 0:
            return self.options[0]
        if i == len(self.options):
            return self.options[-1]
        smaller, larger = self.options[i - 1], self.options[i]
        return smaller if (to - smaller) <= (larger - to) else larger
