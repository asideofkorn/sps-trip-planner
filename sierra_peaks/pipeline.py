"""End-to-end pipeline: cluster -> order (TSP) -> score -> rank."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

from .model import Peak, Cluster
from .clustering import ClusterConfig, cluster_peaks
from .distances import build_distance_matrix
from .tsp import solve_tsp, route_metrics


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


def build_itinerary(cluster_id: int, peaks: Sequence[Peak], config: ClusterConfig) -> Cluster:
    """Solve the TSP for one cluster and populate its metrics."""
    peaks = list(peaks)
    if len(peaks) == 1:
        order = [peaks[0].name]
        metrics = {"horizontal_mi": 0.0, "effective_mi": 0.0, "elevation_gain_ft": 0.0}
        ordered = peaks
    else:
        cost = build_distance_matrix(peaks, metric="effective")
        idx_order = solve_tsp(cost)
        ordered = [peaks[i] for i in idx_order]
        order = [p.name for p in ordered]
        metrics = route_metrics(ordered)

    days = _estimate_days(
        metrics["effective_mi"], config.miles_per_day, config.max_days
    )
    cluster = Cluster(
        cluster_id=cluster_id,
        peaks=ordered,
        order=order,
        total_distance_mi=metrics["horizontal_mi"],
        total_effective_mi=metrics["effective_mi"],
        total_elevation_gain_ft=metrics["elevation_gain_ft"],
        estimated_days=days,
    )
    cluster.score = _efficiency_score(cluster.num_peaks, metrics["effective_mi"])
    return cluster


def build_itineraries(
    peak_groups: Sequence[Sequence[Peak]], config: ClusterConfig
) -> List[Cluster]:
    """Build a :class:`Cluster` (with TSP order + metrics) for each group."""
    return [
        build_itinerary(i, peaks, config) for i, peaks in enumerate(peak_groups)
    ]


def rank_clusters(clusters: Sequence[Cluster]) -> List[Cluster]:
    """Return clusters sorted by efficiency (best first) and renumber IDs."""
    ranked = sorted(clusters, key=lambda c: c.score, reverse=True)
    for new_id, cluster in enumerate(ranked):
        cluster.cluster_id = new_id
    return ranked


def plan_trips(
    peaks: Sequence[Peak], config: Optional[ClusterConfig] = None
) -> List[Cluster]:
    """Full pipeline: cluster the peaks, order each trip, rank by efficiency."""
    config = config or ClusterConfig()
    groups = cluster_peaks(peaks, config)
    clusters = build_itineraries(groups, config)
    return rank_clusters(clusters)
