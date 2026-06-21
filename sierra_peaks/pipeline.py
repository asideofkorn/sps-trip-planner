"""End-to-end pipeline: cluster -> order (TSP) -> score -> rank."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

from .model import Peak, Cluster, Trailhead
from .clustering import ClusterConfig, cluster_peaks
from .distances import build_distance_matrix
from .tsp import solve_tsp, solve_tsp_cycle, route_metrics
from .approach import (
    choose_trailhead,
    approach_metrics,
    approach_costs_to_peaks,
)


def _estimate_days(effective_mi: float, miles_per_day: float, max_days: int) -> int:
    if effective_mi <= 0:
        return 1
    return min(max_days, max(1, math.ceil(effective_mi / miles_per_day)))


def _efficiency_score(num_peaks: int, effective_mi: float) -> float:
    """Peaks bagged per unit of travel effort.

    Rewards bagging more summits while penalizing longer / higher routes.
    Normalized so a zero-travel singleton scores 1.0 and denser multi-peak
    trips score above it; long sprawling trips score below it.
    """
    return num_peaks / (1.0 + effective_mi / 10.0)


def _order_peaks(peaks: List[Peak], trailhead: Optional[Trailhead],
                 config: ClusterConfig) -> List[Peak]:
    """Return the peaks in route order.

    Without a trailhead this is the open-path TSP (today's behavior). With one,
    the trailhead is added as a fixed start/end node and we solve a closed tour,
    so the entry/exit summits are chosen to minimize the whole loop (inter-peak
    travel plus the walk in and out).
    """
    if len(peaks) == 1:
        return peaks
    cost = build_distance_matrix(peaks, metric="effective", router=config.router)
    if trailhead is None:
        return [peaks[i] for i in solve_tsp(cost)]

    # Augment with a trailhead node (last index) whose edges are the inbound
    # approach effort to each peak; routing picks the best entry/exit summits.
    n = len(peaks)
    approach = approach_costs_to_peaks(trailhead, peaks, config.sinuosity)
    aug = np.zeros((n + 1, n + 1), dtype=float)
    aug[:n, :n] = cost
    aug[n, :n] = approach
    aug[:n, n] = approach
    tour = solve_tsp_cycle(aug, start=n)  # [trailhead, entry, ..., exit]
    return [peaks[i] for i in tour[1:]]


def build_itinerary(
    cluster_id: int,
    peaks: Sequence[Peak],
    config: ClusterConfig,
    trailheads: Optional[Sequence[Trailhead]] = None,
) -> Cluster:
    """Solve the TSP for one cluster and populate its metrics."""
    peaks = list(peaks)
    router = config.router

    trailhead = None
    if config.include_approach and trailheads:
        trailhead = choose_trailhead(peaks, trailheads)

    ordered = _order_peaks(peaks, trailhead, config)
    order = [p.name for p in ordered]
    if len(ordered) == 1:
        metrics = {"horizontal_mi": 0.0, "effective_mi": 0.0,
                   "elevation_gain_ft": 0.0, "passes": []}
    else:
        metrics = route_metrics(ordered, router=router)

    cluster = Cluster(
        cluster_id=cluster_id,
        peaks=ordered,
        order=order,
        total_distance_mi=metrics["horizontal_mi"],
        total_effective_mi=metrics["effective_mi"],
        total_elevation_gain_ft=metrics["elevation_gain_ft"],
        passes=list(metrics.get("passes", [])),
    )

    if trailhead is not None:
        appr = approach_metrics(trailhead, ordered[0], ordered[-1], config.sinuosity)
        cluster.trailhead = trailhead.name
        cluster.trailhead_side = trailhead.side
        cluster.approach_distance_mi = appr["horizontal_mi"]
        cluster.approach_effective_mi = appr["effective_mi"]
        cluster.approach_gain_ft = appr["elevation_gain_ft"]
        cluster.total_distance_mi += appr["horizontal_mi"]
        cluster.total_effective_mi += appr["effective_mi"]
        cluster.total_elevation_gain_ft += appr["elevation_gain_ft"]

    cluster.estimated_days = _estimate_days(
        cluster.total_effective_mi, config.miles_per_day, config.max_days
    )
    cluster.score = _efficiency_score(cluster.num_peaks, cluster.total_effective_mi)
    return cluster


def build_itineraries(
    peak_groups: Sequence[Sequence[Peak]],
    config: ClusterConfig,
    trailheads: Optional[Sequence[Trailhead]] = None,
) -> List[Cluster]:
    """Build a :class:`Cluster` (with TSP order + metrics) for each group."""
    return [
        build_itinerary(i, peaks, config, trailheads)
        for i, peaks in enumerate(peak_groups)
    ]


def rank_clusters(clusters: Sequence[Cluster]) -> List[Cluster]:
    """Return clusters sorted by efficiency (best first) and renumber IDs."""
    ranked = sorted(clusters, key=lambda c: c.score, reverse=True)
    for new_id, cluster in enumerate(ranked):
        cluster.cluster_id = new_id
    return ranked


def plan_trips(
    peaks: Sequence[Peak],
    config: Optional[ClusterConfig] = None,
    trailheads: Optional[Sequence[Trailhead]] = None,
) -> List[Cluster]:
    """Full pipeline: cluster the peaks, order each trip, rank by efficiency."""
    config = config or ClusterConfig()
    groups = cluster_peaks(peaks, config, trailheads)
    clusters = build_itineraries(groups, config, trailheads)
    return rank_clusters(clusters)
