"""Sierra Peaks clustering toolkit.

Cluster Sierra Peaks Section (SPS) summits into efficient 1-3 day peak-bagging
trips, order each trip with a TSP solver, and export ranked itineraries.
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
    "build_itineraries",
    "rank_clusters",
    "plan_trips",
]

__version__ = "0.1.0"
