"""Sierra Peaks clustering toolkit.

Cluster Sierra Peaks Section (SPS) summits into efficient 1-3 day peak-bagging
trips, order each trip with a TSP solver, and export ranked itineraries.
"""

from .model import Peak, Cluster
from .data_loader import load_peaks
from .distances import (
    haversine_miles,
    naismith_effective_miles,
    leg_metrics,
    build_distance_matrix,
)
from .clustering import cluster_peaks, ClusterConfig
from .tsp import solve_tsp, route_metrics
from .pipeline import build_itineraries, rank_clusters

__all__ = [
    "Peak",
    "Cluster",
    "load_peaks",
    "haversine_miles",
    "naismith_effective_miles",
    "leg_metrics",
    "build_distance_matrix",
    "cluster_peaks",
    "ClusterConfig",
    "solve_tsp",
    "route_metrics",
    "build_itineraries",
    "rank_clusters",
]

__version__ = "0.1.0"
