from __future__ import annotations

from collections import Counter
from typing import Optional, Sequence, Union

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import expit

from instamatic._typing import float_nm
from instamatic.grid.grid import WindowType


class ScanProfile:
    """Find x or y intersections of windows and yield their properties."""

    def __init__(
        self,
        windows: Sequence[WindowType],
        *,
        x: Optional[float_nm] = None,
        y: Optional[float_nm] = None,
    ) -> None:
        assert Counter([x, y])[None] == 1, 'Exactly one of x or y must be given'
        self.var = x if y is None else y
        self.method = 'x_intersections' if y is None else 'y_intersections'
        self.windows = windows

        self.intersections = [getattr(w, self.method)(self.var) for w in windows]
        self.minimum = min(i[0] for i in self.intersections if i is not None)
        self.maximum = max(i[1] for i in self.intersections if i is not None)

    def envelope(self, margin: float_nm = 0) -> tuple[float, float]:
        return self.minimum - margin, self.maximum + margin

    @staticmethod
    def sigmoid(
        x: Union[float_nm, np.ndarray],
        x0: Union[float_nm, np.ndarray],
        width: float = 100.0,
    ) -> float:
        """Grows (from 0 to 1) by .24/46/99 across 1/2/10 widths around x0."""
        return expit((x - x0) / width)

    def window_model(
        self,
        x: Union[float_nm, np.ndarray],
        offset: float_nm,
        scale: float,
    ) -> Union[float_nm, np.ndarray]:
        """Return a model of light at x given y-scaling and x-offset in nm."""
        x_arr = np.atleast_1d(np.asarray(x, dtype=float))
        starts = np.array([i[0] for i in self.intersections if i is not None])
        ends = np.array([i[1] for i in self.intersections if i is not None])

        s1 = self.sigmoid(x_arr[None, :] - offset, starts[:, None])
        s2 = self.sigmoid(x_arr[None, :] - offset, ends[:, None])
        result = scale * np.sum(s1 - s2, axis=0)
        return result.item() if np.isscalar(x) else result

    def fit(self, x: np.ndarray, light: np.ndarray) -> tuple[float_nm, float]:
        """X-offset and y-scale that best fit (x, y) data to scan profile."""
        p0 = [x[np.argmax(light)] - self.var, np.percentile(light, 99)]
        popt, _ = curve_fit(self.window_model, x, light, p0=p0)  # noqa unpacking
        return popt[0], popt[1]
