"""Sierra trip-logistics toolkit.

Resolve source-backed Sierra trip logistics and generate experimental SPS
candidate groupings. Geographic grouping and TSP ordering are discovery aids,
not verified mountain routes.
"""

from .model import Peak, Cluster, Trailhead
from .data_loader import load_peaks, load_trailheads
from .distances import (
    haversine_miles,
    naismith_effective_miles,
    leg_metrics,
    build_distance_matrix,
)
from .clustering import cluster_peaks, ClusterConfig
from .tsp import solve_tsp, solve_tsp_cycle, route_metrics
from .approach import choose_trailhead, approach_leg, approach_metrics
from .diagnostics import approach_amortization, format_approach_report
from .pipeline import build_itineraries, rank_clusters, plan_trips

__all__ = [
    "Peak",
    "Cluster",
    "Trailhead",
    "load_peaks",
    "load_trailheads",
    "haversine_miles",
    "naismith_effective_miles",
    "leg_metrics",
    "build_distance_matrix",
    "cluster_peaks",
    "ClusterConfig",
    "solve_tsp",
    "solve_tsp_cycle",
    "route_metrics",
    "choose_trailhead",
    "approach_leg",
    "approach_metrics",
    "approach_amortization",
    "format_approach_report",
    "build_itineraries",
    "rank_clusters",
    "plan_trips",
]

__version__ = "0.1.0"
