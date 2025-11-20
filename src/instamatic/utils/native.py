from __future__ import annotations

from typing import Union, overload

import numpy as np

AnyNumber = Union[int, float, np.floating, np.integer]
NativeNumber = Union[int, float]


@overload
def native(x: np.floating) -> float: ...
@overload
def native(x: np.integer) -> int: ...
@overload
def native(x: float) -> float: ...
@overload
def native(x: int) -> int: ...


def native(x: AnyNumber) -> NativeNumber:
    """Quickly convert AnyNumber to a respective built-in NativeNumber type.

    Benchmark results for 5 million ops on different input types shown
    below (total time in seconds) show this method is the best on average.
    ::
        Method                             int    float   np.int64  np.float64
        hasattr(x, 'item')               0.274    0.361      3.165       3.355
        isinstance(x, np.generic)        0.526    0.567      3.056       3.063
        type(x).__module__ == 'numpy'    0.310    0.329      3.369       3.430
    """
    return x.item() if hasattr(x, 'item') else x
