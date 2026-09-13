"""Model the trailhead approach: the walk from the car to the first summit and
the descent from the last summit back.

The inter-peak sequence (see :mod:`wayproof.distances`) estimates direct
travel between summits, but it ignores how you reach the range from a road.
This module closes that gap using data already in the dataset:

* Each peak's official round-trip ``mileage_rt`` / ``gain_ft`` from its standard
  trailhead (authoritative *trail* numbers) are used when the chosen trailhead is
  that peak's ``nearest_trailhead``.
* Otherwise we fall back to a geometric estimate: great-circle distance inflated
  by a sinuosity factor (trails switchback and contour) with the trailhead ->
  summit elevation delta as the climb.

Both are converted to Naismith effective miles so the approach is in the same
currency as the rest of the candidate sequence.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .model import Peak, Trailhead
from .distances import haversine_miles, naismith_effective_miles

# Trails switchback and contour, so on-trail distance exceeds the straight line.
# Used only for the geometric fallback when official mileage is unavailable.
DEFAULT_SINUOSITY = 1.25



@dataclass
class EntryConflict:
    """A peak whose sourced route contradicts the trailhead geometry picked.

    ``nearest_trailhead`` is computed by ``scripts/assign_trailheads.py`` as
    great-circle distance from the summit. It is geometry, not evidence, and
    ``views.py`` already labels it "UNVERIFIED ... do not state these as this
    trailhead's approach list". The collections file carries a *sourced* route
    name for the same peak. Where the two name different places, this project
    does not know which governs, and must say so instead of preferring the one
    it can compute.
    """

    peak_name: str
    sourced_route: str
    computed_trailhead: str

    def __str__(self) -> str:
        return (f"{self.peak_name}: its sourced route is {self.sourced_route!r}, but this "
                f"plan resolved entry via {self.computed_trailhead!r} from straight-line "
                "proximity. Those may be different entry points under different agencies.")


def _tokens(value: str) -> set:
    """Comparable words, minus the noise that decorates route names."""
    noise = {"trail", "trailhead", "th", "road", "rd", "creek", "lake", "lakes",
             "canyon", "pass", "the", "via", "and", "of"}
    words = {w for w in re.split(r"[^a-z0-9]+", str(value or "").lower()) if len(w) > 2}
    stripped = words - noise
    # "Shepherd Pass Trail" vs "Shepherd Pass" must still match on "shepherd";
    # but a name made only of noise words falls back to the full set.
    return stripped or words


def names_same_place(sourced: str, trailhead_name: str) -> bool:
    """True when a sourced route name plausibly refers to this trailhead.

    Deliberately generous. A false match here hides a real conflict, but a
    false *mismatch* only produces an extra "we are not sure" -- and being
    unsure out loud is the behaviour this is protecting.
    """
    a, b = _tokens(sourced), _tokens(trailhead_name)
    return bool(a & b)


def entry_conflicts(peaks: Sequence[Peak], chosen: Optional[Trailhead]) -> List[EntryConflict]:
    """Every objective whose sourced route disagrees with the chosen trailhead.

    Returns ``[]`` when there is nothing to compare, which is not the same as
    agreement: a peak with no sourced route is unchecked, not confirmed.
    """
    if chosen is None:
        return []
    out: List[EntryConflict] = []
    for peak in peaks:
        sourced = str(peak.meta.get("trailhead") or "").strip()
        if not sourced or names_same_place(sourced, chosen.name):
            continue
        out.append(EntryConflict(peak_name=peak.name, sourced_route=sourced,
                                 computed_trailhead=chosen.name))
    return out


def choose_trailhead(
    peaks: Sequence[Peak], trailheads: Sequence[Trailhead]
) -> Optional[Trailhead]:
    """Pick the single trailhead that best serves a candidate group.

    Preference order:

    1. The most common ``nearest_trailhead`` among the group's peaks, resolved
       by name against ``trailheads`` (the access point already serving the most
       summits in the group). Ties are broken by proximity to the centroid.
    2. Failing that (no usable ``nearest_trailhead`` names), the trailhead
       closest to the group centroid.
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
    """Total approach for a loop: hike *in* to ``entry``, out from ``exit_``.

    The inbound leg ascends (Naismith penalty applies); the outbound leg descends
    (no penalty, per the standard simple form of the rule). For a single-peak
    group ``entry is exit_`` and this reduces to the official round trip.

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

    Used to anchor the candidate sequence: these become the trailhead-node edges
    so the TSP selects the entry/exit summits that minimize the overall loop.
    """
    costs = []
    for p in peaks:
        dist, gain = approach_leg(trailhead, p, sinuosity)
        costs.append(naismith_effective_miles(dist, gain))
    return costs
