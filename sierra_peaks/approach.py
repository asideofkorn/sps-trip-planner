"""Model the trailhead approach: the walk from the car to the first summit and
the descent from the last summit back.

The inter-peak route (see :mod:`sierra_peaks.distances`) models off-trail class
1-2 travel between summits, but it ignores how you reach the range from a road.
This module closes that gap using data already in the dataset:

* Each peak's official round-trip ``mileage_rt`` / ``gain_ft`` from its standard
  trailhead (authoritative *trail* numbers) are used when the chosen trailhead is
  that peak's ``nearest_trailhead``.
* Otherwise we fall back to a geometric estimate: great-circle distance inflated
  by a sinuosity factor (trails switchback and contour) with the trailhead ->
  summit elevation delta as the climb.

Both are converted to Naismith effective miles so the approach is in the same
currency as the rest of the route.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional, Sequence, Tuple

from .model import Peak, Trailhead
from .distances import haversine_miles, naismith_effective_miles

# Trails switchback and contour, so on-trail distance exceeds the straight line.
# Used only for the geometric fallback when official mileage is unavailable.
DEFAULT_SINUOSITY = 1.25


def choose_trailhead(
    peaks: Sequence[Peak], trailheads: Sequence[Trailhead]
) -> Optional[Trailhead]:
    """Pick the single trailhead that best serves a cluster.

    Preference order:

    1. The most common ``nearest_trailhead`` among the cluster's peaks, resolved
       by name against ``trailheads`` (the access point already serving the most
       summits in the group). Ties are broken by proximity to the centroid.
    2. Failing that (no usable ``nearest_trailhead`` names), the trailhead
       closest to the cluster centroid.
    """
    if not trailheads:
        return None
    by_name = {th.name: th for th in trailheads}

    clat = sum(p.latitude for p in peaks) / len(peaks)
    clon = sum(p.longitude for p in peaks) / len(peaks)

    counts = Counter(
        str(p.meta["nearest_trailhead"]).strip()
        for p in peaks
        if p.meta.get("nearest_trailhead") and str(p.meta["nearest_trailhead"]).strip() in by_name
    )
    if counts:
        best_n = max(counts.values())
        candidates = [by_name[name] for name, n in counts.items() if n == best_n]
        return min(
            candidates,
            key=lambda th: haversine_miles(clat, clon, th.latitude, th.longitude),
        )

    return min(
        trailheads,
        key=lambda th: haversine_miles(clat, clon, th.latitude, th.longitude),
    )


def approach_leg(
    trailhead: Trailhead, peak: Peak, sinuosity: float = DEFAULT_SINUOSITY
) -> Tuple[float, float]:
    """One-way trailhead -> summit approach as ``(distance_mi, ascent_ft)``.

    Uses the peak's authoritative round-trip numbers when the chosen trailhead is
    that peak's standard ``nearest_trailhead``; otherwise estimates geometrically.
    The returned ascent is the climb on the way *in*; the caller decides whether a
    given leg is ascending (entry) or descending (exit).
    """
    mileage_rt = peak.meta.get("mileage_rt")
    gain_ft = peak.meta.get("gain_ft")
    nearest = peak.meta.get("nearest_trailhead")
    matches = nearest is not None and str(nearest).strip() == trailhead.name

    if matches and mileage_rt:
        distance = float(mileage_rt) / 2.0
        ascent = float(gain_ft) if gain_ft else max(0.0, peak.elevation_ft - trailhead.elevation_ft)
    else:
        distance = haversine_miles(
            trailhead.latitude, trailhead.longitude, peak.latitude, peak.longitude
        ) * sinuosity
        ascent = max(0.0, peak.elevation_ft - trailhead.elevation_ft)
    return distance, ascent


def approach_metrics(
    trailhead: Trailhead,
    entry: Peak,
    exit_: Peak,
    sinuosity: float = DEFAULT_SINUOSITY,
) -> dict:
    """Total approach for a loop trip: hike *in* to ``entry``, out from ``exit_``.

    The inbound leg ascends (Naismith penalty applies); the outbound leg descends
    (no penalty, per the standard simple form of the rule). For a single-peak
    trip ``entry is exit_`` and this reduces to the official round trip.

    Returns ``horizontal_mi``, ``effective_mi`` and ``elevation_gain_ft``.
    """
    in_dist, in_gain = approach_leg(trailhead, entry, sinuosity)
    out_dist, _ = approach_leg(trailhead, exit_, sinuosity)
    return {
        "horizontal_mi": in_dist + out_dist,
        "effective_mi": naismith_effective_miles(in_dist, in_gain) + out_dist,
        "elevation_gain_ft": in_gain,
    }


def approach_costs_to_peaks(
    trailhead: Trailhead, peaks: Sequence[Peak], sinuosity: float = DEFAULT_SINUOSITY
) -> List[float]:
    """Inbound (ascending) approach effective miles from ``trailhead`` to each peak.

    Used to anchor the route: these become the trailhead-node edges so the TSP
    selects the entry/exit summits that minimize the overall loop.
    """
    costs = []
    for p in peaks:
        dist, gain = approach_leg(trailhead, p, sinuosity)
        costs.append(naismith_effective_miles(dist, gain))
    return costs
