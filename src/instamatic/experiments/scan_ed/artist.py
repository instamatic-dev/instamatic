from __future__ import annotations

import traceback

import numpy as np
import pandas as pd
from matplotlib.axes import Axes


def overlay_scan_hits(
    ax: Axes, lines: pd.DataFrame, scans: pd.DataFrame, steps: pd.DataFrame
) -> None:
    """Overlay a heatmap of scan hits onto an existing Axes object."""

    if any(x is None or x.empty for x in [lines, scans, steps]):
        return

    try:
        slow_idx = 'y0' if (lines['axis'] == 0).all() else 'x0'
        fast_idx = 'x0' if (lines['axis'] == 0).all() else 'y0'

        max_offset = scans['offset'].abs().max()

        if (fast_step := lines['step'].abs().mean()) == 0:
            raise ValueError(f'{fast_step=}: scan data missing or corrupt')

        fast_start = lines[fast_idx]
        fast_end = lines[fast_idx] + lines['step'] * lines['n_steps']
        fast_min = np.minimum(fast_start, fast_end).min() - max_offset
        fast_max = np.maximum(fast_start, fast_end).max() + max_offset
        fast_count = np.ceil((fast_max - fast_min) / fast_step).astype(int)

        slows = lines[slow_idx]
        try:
            slow_step = (np.max(slows) - np.min(slows)) / (len(slows) - 1)
        except ZeroDivisionError:
            slow_step = fast_step  # fallback in case of a single scan

        slow_min = np.min(slows) - 0.5 * slow_step
        slow_max = np.max(slows) + 0.5 * slow_step
        slow_count = len(slows)

        level = ['region', 'line', 'scan']
        hits = {k: g['hits'].to_numpy(dtype=float) for k, g in steps.groupby(level=level)}

        hits_matrix = np.zeros(shape=(slow_count, fast_count), dtype=float)
        for (region, line), line_row in lines.iterrows():
            slow = line_row[slow_idx]
            step = int(line_row['step'])
            n_steps = int(line_row['n_steps'])
            fast0 = float(line_row[fast_idx])
            i = int((slow - slow_min) // slow_step)

            sc = scans.loc[(region, line)]
            offsets = sc['offset'].to_numpy()
            hits_array = np.stack([hits[(region, line, s)] for s in sc.index], axis=0)
            if step < 0:  # reverse dir: flip hit matrix and recalculate fast0
                hits_array = hits_array[:, ::-1]
                fast0 = fast0 + step * (n_steps - 1)
            j0s = np.floor((fast0 - fast_min + offsets) / fast_step).astype(int)

            for k in range(len(j0s)):
                j0 = j0s[k]
                j0c = max(0, j0)
                j1c = min(fast_count, j0 + n_steps)
                if j0c < j1c:
                    hits_matrix[i, j0c:j1c] += hits_array[k][j0c - j0 : j1c - j0]

        if fast_idx == 'x0':
            x0, x1, y0, y1 = fast_min, fast_max, slow_min, slow_max
        else:
            x0, x1, y0, y1 = slow_min, slow_max, fast_min, fast_max
            hits_matrix = hits_matrix.T

        rgba = np.zeros((*hits_matrix.shape, 4), dtype=np.float32)
        if (hits_max := hits_matrix.max()) > 0:
            rgba[..., 0] = 1.0  # red square with opacity ~ hit density
            rgba[..., 3] = hits_matrix / hits_max

        ax.imshow(rgba, origin='lower', extent=(x0, x1, y0, y1), aspect='auto', zorder=3)
        ax.set_aspect('equal', adjustable='box')

    except (KeyError, ValueError):
        traceback.print_exc()
