"""Diagnostics over a planned set of trips.

Currently: an *approach-amortization* report. The trailhead approach is a fixed
cost paid once per trip (you walk in and out regardless of how many summits you
bag), so when several trips share one trailhead that cost is paid several times
over. This report surfaces those trailheads and estimates how much approach
effort could be recovered by repacking their trips within the day budget.

It is a *signal*, not a solver: it ranks where amortization opportunities are
biggest. The honest cap is the day budget -- a trailhead whose peaks genuinely
need N full-length trips (e.g. Mineral King) shows little or no recoverable
effort, which is the correct answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

from .model import Cluster
from .clustering import ClusterConfig


@dataclass
class TrailheadAmortization:
    """Per-trailhead approach-amortization summary (trailheads with >1 trip)."""

    trailhead: str
    side: str
    num_trips: int
    num_peaks: int
    approach_paid_mi: float        # total approach effort paid across the trips
    avg_walk_in_mi: float          # approach per trip (one walk in + out)
    min_trips_by_budget: int       # fewest trips the shared effort could repack into
    recoverable_mi: float          # est. approach saved if repacked to that minimum


def approach_amortization(
    clusters: Sequence[Cluster], config: ClusterConfig
) -> List[TrailheadAmortization]:
    """Rank trailheads that serve more than one trip by recoverable approach.

    For each such trailhead we compare the current trip count with the fewest
    trips its combined effort could occupy at the configured day budget
    (``miles_per_day × max_days``). Each trip removed saves roughly one average
    walk-in/out, so ``recoverable_mi = removable_trips × avg_walk_in``.
    """
    by_th: dict[str, List[Cluster]] = {}
    for c in clusters:
        if c.trailhead:
            by_th.setdefault(c.trailhead, []).append(c)

    budget = config.max_effective_mi  # miles_per_day * max_days
    rows: List[TrailheadAmortization] = []
    for th, trips in by_th.items():
        if len(trips) <= 1:
            continue
        total_eff = sum(c.total_effective_mi for c in trips)
        approach_paid = sum(c.approach_effective_mi for c in trips)
        n = len(trips)
        avg_walk_in = approach_paid / n
        min_trips = max(1, math.ceil(total_eff / budget)) if budget > 0 else n
        removable = max(0, n - min_trips)
        rows.append(
            TrailheadAmortization(
                trailhead=th,
                side=trips[0].trailhead_side,
                num_trips=n,
                num_peaks=sum(c.num_peaks for c in trips),
                approach_paid_mi=approach_paid,
                avg_walk_in_mi=avg_walk_in,
                min_trips_by_budget=min_trips,
                recoverable_mi=removable * avg_walk_in,
            )
        )

    # Biggest opportunity first: recoverable effort, then sheer approach paid.
    rows.sort(key=lambda r: (r.recoverable_mi, r.approach_paid_mi), reverse=True)
    return rows


def format_approach_report(rows: Sequence[TrailheadAmortization]) -> str:
    """Render the amortization rows as a readable text table."""
    if not rows:
        return ("No trailhead serves more than one trip — no approach to "
                "amortize at this day budget.")

    lines = []
    header = (f"{'trailhead':28} {'side':5} {'trips':>5} {'peaks':>5} "
              f"{'appr_mi':>8} {'per_trip':>8} {'min_trips':>9} {'save_mi':>8}")
    lines.append(header)
    lines.append("-" * len(header))
    for r in rows:
        lines.append(
            f"{r.trailhead[:28]:28} {r.side[:5]:5} {r.num_trips:>5} {r.num_peaks:>5} "
            f"{r.approach_paid_mi:>8.1f} {r.avg_walk_in_mi:>8.1f} "
            f"{r.min_trips_by_budget:>9} {r.recoverable_mi:>8.1f}"
        )
    total_recoverable = sum(r.recoverable_mi for r in rows)
    lines.append("-" * len(header))
    lines.append(
        f"{len(rows)} trailheads serve multiple trips; "
        f"~{total_recoverable:.1f} effective approach-mi potentially recoverable "
        f"by repacking within the day budget."
    )
    return "\n".join(lines)
