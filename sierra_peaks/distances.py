"""Distance, elevation, and effort models.

Travel between peaks is assumed off-trail over class 1-2 terrain, so horizontal
distance is modeled with the great-circle (haversine) distance. Effort is then
adjusted for climbing via Naismith's Rule, which converts vertical ascent into
an equivalent amount of flat-mile effort.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .model import Peak

EARTH_RADIUS_MI = 3958.7613

# Naismith's Rule: 1 hour per 3 horizontal miles, plus 1 hour per 2000 ft of
# ascent. So 2000 ft of climbing costs roughly the same time as 3 flat miles.
NAISMITH_FT_PER_EQUIV_HOUR = 2000.0
NAISMITH_MILES_PER_HOUR = 3.0
# Equivalent flat miles added per foot of ascent.
NAISMITH_MILES_PER_FT = NAISMITH_MILES_PER_HOUR / NAISMITH_FT_PER_EQUIV_HOUR


def haversine_miles(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance between two lat/lon points, in statute miles."""
    rlat1, rlon1, rlat2, rlon2 = np.radians([lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0) ** 2
    return float(2.0 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a)))


def naismith_effective_miles(horizontal_mi: float, ascent_ft: float) -> float:
    """Convert horizontal distance + ascent into Naismith effective flat miles."""
    return horizontal_mi + max(0.0, ascent_ft) * NAISMITH_MILES_PER_FT


def leg_metrics(a: Peak, b: Peak, router=None) -> Tuple[float, float, float]:
    """Metrics for travelling from peak ``a`` to peak ``b``.

    Returns ``(horizontal_mi, ascent_ft, effective_mi)``.

    Ascent is the positive elevation difference; descending to a lower peak
    contributes no Naismith penalty (the standard, simple form of the rule).
    When a ``router`` (``sierra_peaks.passes.PassRouter``) is supplied, a leg that
    crosses the Sierra crest is routed through the cheapest pass instead of
    tunnelling straight through the ridge.
    """
    if router is not None:
        r = router.leg(a, b, by="effective")
        return r.horizontal_mi, r.ascent_ft, r.effective_mi
    horizontal = haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude)
    ascent = max(0.0, b.elevation_ft - a.elevation_ft)
    effective = naismith_effective_miles(horizontal, ascent)
    return horizontal, ascent, effective


def build_distance_matrix(
    peaks: Sequence[Peak], metric: str = "haversine", router=None
) -> np.ndarray:
    """Symmetric pairwise distance matrix over ``peaks``.

    Parameters
    ----------
    metric : {"haversine", "effective"}
        ``"haversine"`` gives plain horizontal miles (symmetric).
        ``"effective"`` gives Naismith effort miles, symmetrized as the mean of
        the two directional legs so it can be used by distance-based clustering.
    router : PassRouter, optional
        If given, cross-crest legs are routed through the cheapest pass (see
        :mod:`sierra_peaks.passes`). When ``None`` the original straight-line
        behaviour is used.
    """
    n = len(peaks)
    mat = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            if router is not None:
                if metric == "haversine":
                    d = router.horizontal(peaks[i], peaks[j])
                elif metric == "effective":
                    d = 0.5 * (
                        router.effective_directional(peaks[i], peaks[j])
                        + router.effective_directional(peaks[j], peaks[i])
                    )
                else:
                    raise ValueError(f"Unknown metric: {metric!r}")
                mat[i, j] = mat[j, i] = d
                continue
            horiz = haversine_miles(
                peaks[i].latitude,
                peaks[i].longitude,
                peaks[j].latitude,
                peaks[j].longitude,
            )
            if metric == "haversine":
                d = horiz
            elif metric == "effective":
                asc_ij = max(0.0, peaks[j].elevation_ft - peaks[i].elevation_ft)
                asc_ji = max(0.0, peaks[i].elevation_ft - peaks[j].elevation_ft)
                d = 0.5 * (
                    naismith_effective_miles(horiz, asc_ij)
                    + naismith_effective_miles(horiz, asc_ji)
                )
            else:
                raise ValueError(f"Unknown metric: {metric!r}")
            mat[i, j] = mat[j, i] = d
    return mat
