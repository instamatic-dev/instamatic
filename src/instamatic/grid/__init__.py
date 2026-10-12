from __future__ import annotations

from typing import Optional, Union

import numpy as np

Intercepts = dict[int, np.ndarray]


def cross2d(a: np.ndarray, b: np.ndarray) -> float:
    """A scalar 2d cross product between two arrays of length 2."""
    return (a[0] * b[1] - a[1] * b[0]).item()


def versor(
    *,
    deg: Optional[Union[float, np.ndarray]] = None,
    rad: Optional[Union[float, np.ndarray]] = None,
) -> np.ndarray:
    """A versor in the direction of angle expressed in radians or degrees."""
    radians = np.deg2rad(deg) if rad is None else rad
    return np.array([np.cos(radians), np.sin(radians)], dtype=float)
