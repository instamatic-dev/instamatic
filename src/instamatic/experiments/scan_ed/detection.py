"""This module collects functions responsible for identifying diffraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from scipy import ndimage as ndi


def make_cross_mask():
    c = 511 / 2
    yy, xx = np.indices((512, 512))
    vertical = np.abs(xx - c) <= 1.9
    horizontal = np.abs(yy - c) <= 1.9
    cross = vertical | horizontal
    return ~cross


HARD_CODED_MASK = make_cross_mask()


@dataclass
class DiffHuntResults:
    """Stores and normalizes basic results of diffraction detection."""

    success: bool
    bin_center: Optional[tuple[float, float]] = None
    bin_edges: Optional[Sequence[float]] = None
    peaks: Optional[np.ndarray] = None
    mask: Optional[np.ndarray] = None
    light: int = 0


def ring_percentile_detection(
    frame: np.ndarray,
    min_radius: int = 40,
    percentile: float = 99.0,
    threshold_mult: float = 2.0,
    min_peak_count: int = 10,
    min_peak_sep: int = 5,
    mask: np.ndarray | None = None,
    n_bins: int = 10,
    gaussian_sigma: float = 1.2,
) -> DiffHuntResults:
    """Radial-binned detector with thresholds computed on a *locally averaged*
    image.

    This suppresses single-pixel spikes (stray electrons / hot pixels),
    while keeping multi-pixel reflection profiles detectable.
    """

    # Build a locally-averaged "score" image for candidate selection.
    score = frame.astype(np.float32, copy=False)
    if mask is not None:
        m = mask.astype(np.float32, copy=False)
        numer = ndi.gaussian_filter(score * m, sigma=gaussian_sigma, mode='mirror')
        denom = ndi.gaussian_filter(m, sigma=gaussian_sigma, mode='mirror')
        score = np.divide(numer, denom, out=np.zeros_like(numer), where=denom > 0)
    else:
        score = ndi.gaussian_filter(score, sigma=gaussian_sigma, mode='mirror')
    if gaussian_sigma and gaussian_sigma > 0:
        score = ndi.gaussian_filter(score, sigma=float(gaussian_sigma), mode='mirror')

    cy, cx = estimate_beam_center(frame, sigma=3.0)
    ys, xs = np.indices(frame.shape)
    rr = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    valid = mask.astype(bool) if mask is not None else np.ones(frame.shape, dtype=bool)
    valid &= rr > min_radius

    valid_idx = np.flatnonzero(valid)
    if valid_idx.size == 0:
        return DiffHuntResults(success=False, bin_center=(cy, cx), mask=valid)

    vals = score.flat[valid_idx]  # (N,) float32
    rr_vals = rr.flat[valid_idx].astype(np.float32, copy=False)

    r_max = float(rr_vals.max())
    bin_edges = np.linspace(min_radius, r_max, n_bins + 1).astype(np.float32)

    bin_ids = np.digitize(rr_vals, bin_edges) - 1
    np.clip(bin_ids, 0, n_bins - 1, out=bin_ids)

    backgrounds = np.zeros(n_bins, dtype=np.float32)
    thresholds = np.full(n_bins, np.inf, dtype=np.float32)

    for b in range(n_bins):
        sel = bin_ids == b
        if not np.any(sel):
            continue
        v = vals[sel]
        bg = float(np.median(v))
        backgrounds[b] = bg

        # Threshold in "score" units: (percentile - bg) times multiplier, with a small floor.
        threshold_perc = max(1.0, float(np.percentile(v, percentile) - bg))
        thresholds[b] = threshold_mult * threshold_perc

    # Candidate selection purely in 1D on the locally averaged image
    keep = vals >= (thresholds[bin_ids] + backgrounds[bin_ids])

    peak_mask = np.zeros(frame.shape, dtype=bool)
    peak_mask.flat[valid_idx[keep]] = True

    # Pick peak positions using the *raw* frame intensities (not the averaged score)
    peaks = cluster_peak_mask(peak_mask, frame, min_dist=min_peak_sep)
    n_peaks = int(peaks.shape[0])

    return DiffHuntResults(
        success=n_peaks >= min_peak_count,
        bin_center=(cy, cx),
        bin_edges=bin_edges,
        peaks=peaks,
        mask=valid,
        light=int(np.sum(frame, axis=None)),
    )


def estimate_beam_center(frame: np.ndarray, sigma: float = 10.0) -> tuple[int, int]:
    """Estimate beam center by Gaussian-blurring a small ROI and taking max."""
    h, w = frame.shape
    cy0, cx0 = np.unravel_index(np.argmax(frame), frame.shape)

    y0 = max(0, cy0 - h // 8)
    y1 = min(h, cy0 + h // 8)
    x0 = max(0, cx0 - w // 8)
    x1 = min(w, cx0 + w // 8)

    roi = frame[y0:y1, x0:x1].astype(np.float32)
    roi_blur = ndi.gaussian_filter(roi, sigma=sigma, mode='nearest')
    iy, ix = np.unravel_index(np.argmax(roi_blur), roi_blur.shape)
    return y0 + int(iy), x0 + int(ix)


NEIGHBOUR_PLUS = ndi.generate_binary_structure(2, 1)


def cluster_peak_mask(peak_mask: np.ndarray, frame: np.ndarray, min_dist: int = 5):
    """
    peak_mask: boolean mask of all peak-candidate pixels (True = candidate)
    frame: image used to pick the representative (processed)
    min_dist: merge radius (pixels). Pixels within ~min_dist get clustered.
    Returns: (K,2) array of (y,x) peak positions (one per cluster @ peak_mask)
    """

    if not peak_mask.any():
        return np.empty((0, 2), dtype=int)

    # define a region around each peak found on peak_mask and label them
    dilated = ndi.binary_dilation(peak_mask, iterations=min_dist, structure=NEIGHBOUR_PLUS)
    lbl, n = ndi.label(dilated, structure=NEIGHBOUR_PLUS)
    if n == 0:
        return np.empty((0, 2), dtype=int)

    # limit the view to only regions with candidate pixels (not entire frame)
    ys, xs = np.nonzero(peak_mask)
    labs = lbl[ys, xs]  # label per candidate pixel (1..n)
    vals = frame[ys, xs]  # raw intensity per candidate pixel

    # drop candidates that somehow map to background (shouldn't happen)
    keep = labs > 0
    ys, xs, labs, vals = ys[keep], xs[keep], labs[keep], vals[keep]

    # for each label, choose index of max intensity
    order = np.argsort(labs, kind='stable')
    ys, xs, labs, vals = ys[order], xs[order], labs[order], vals[order]

    # find segment boundaries and for each segment, find max within that segment
    boundaries = np.flatnonzero(np.r_[True, labs[1:] != labs[:-1]])
    peaks = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(labs)
        j = start + int(np.argmax(vals[start:end]))
        peaks.append((int(ys[j]), int(xs[j])))

    return np.array(peaks, dtype=int)


def plot_diffraction_debug(
    frame: np.ndarray,
    results: DiffHuntResults,
) -> None:
    """Visualize detection results: log-scale image, dots @ peaks & center."""

    fig, ax = plt.subplots(figsize=(6, 6))
    h, w = frame.shape
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_title('Diffraction detection debug')
    ax.axis('off')

    img_log = np.log10(np.maximum(frame.astype(np.float32), 0) + 1.0)
    ax.imshow(img_log, cmap='gray')

    if (mask := results.mask) is not None:  # False == excluded areas = red tint
        overlay = np.zeros((*mask.shape, 4), dtype=np.float32)
        overlay[~mask] = (1.0, 0.0, 0.0, 0.25)  # RGBA
        ax.imshow(overlay)

    if (center := results.bin_center) is not None:  # bin center and edges
        cy, cx = center
        ax.scatter(center[1], center[0], s=4, c='cyan', marker='s', label='center')
        if (edges := results.bin_edges) is not None:
            for r in edges:
                p = Circle((cx, cy), float(r), fill=False, linewidth=0.5, clip_on=True)
                ax.add_patch(p)

    if (peaks := results.peaks) is not None:
        ax.scatter(peaks[:, 1], peaks[:, 0], s=2, c='lime', marker='o', label='peaks')

    ax.legend(loc='lower right', fontsize=8)
    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    from glob import glob

    from PIL import Image

    mask = make_cross_mask()
    paths = glob(
        r'C:\Users\tchon\x\2026-02-06-SPED_test\experiment_5\tiff\w000000_s000031_0000*.tiff'
    )
    # paths = glob(r'C:\Users\tchon\x\Instamatic_RATS_cRED_benchmark\instamatic_19\tiff\0000*')
    for path in paths:
        tiff = Image.open(path)
        image = np.array(tiff)
        results = ring_percentile_detection(image, mask=mask)
        print(Path(path).stem, results.success, len(results.peaks))
        plot_diffraction_debug(image, results)
