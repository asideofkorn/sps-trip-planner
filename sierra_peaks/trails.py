"""Trail-network distances sourced from OpenStreetMap.

Peaks are typically off-trail summits; the trail-network graph only covers the
walkable path/track network. A route between two peaks is therefore modeled
as: a straight-line "snap" from the peak to its nearest trail node, a shortest
path along the trail graph, then a straight-line "snap" to the destination
peak. The snap portions stay straight-line by design -- that matches the
existing off-trail assumption in :mod:`sierra_peaks.distances`; only the
on-trail middle portion switches to real trail geometry.

The graph itself (``data/trails.graphml``) is fetched once, offline, by
``scripts/fetch_osm_trails.py`` and committed as a static artifact -- this
module never touches the network.

Ascent is still the plain peak-to-peak elevation delta (not summed along the
trail path); see the README's "elevation gain is a lower bound" note, which
this compounds rather than fixes.

Everything here is opt-in: the clustering/pipeline default to no router and
behave exactly as before (see :mod:`sierra_peaks.distances`). Build one with
:func:`build_router`. Coverage is uneven across OSM, so degradation is
per-leg: a peak/trailhead too far from any mapped trail (or stranded in a
disconnected graph component) falls back to the same direct haversine +
Naismith computation used when no router is given at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np

from .distances import haversine_miles, naismith_effective_miles

# (lat_min, lat_max, lon_min, lon_max) -- matches scripts/merge_passes.py and
# scripts/build_gnis_gaps.py's SIERRA_BBOX, comfortably covering
# data/sps_peaks.csv and data/trailheads.csv with margin.
SIERRA_BBOX = (35.0, 41.5, -121.0, -117.0)

# Beyond this straight-line distance from the nearest mapped trail node, a
# peak/trailhead is considered off the covered trail network and the leg
# falls back to direct routing.
DEFAULT_MAX_SNAP_MI = 1.5


@dataclass
class LegResult:
    horizontal_mi: float
    ascent_ft: float
    effective_mi: float
    on_trail: bool
    snap_a_mi: float = 0.0
    snap_b_mi: float = 0.0


class TrailRouter:
    """Leg costs computed as snap-to-trail + shortest-path-on-trail + snap-off.

    Falls back to the direct straight-line leg (identical to no-router
    behaviour) when either endpoint is farther than ``max_snap_mi`` from the
    trail graph, or when no path exists between the two snapped nodes (e.g.
    disconnected trail components near the edge of the fetched bounding box).
    """

    def __init__(self, graph: nx.Graph, max_snap_mi: float = DEFAULT_MAX_SNAP_MI):
        self.graph = graph
        self.max_snap_mi = max_snap_mi
        self._node_ids = list(graph.nodes)
        self._tree = None
        if self._node_ids:
            from sklearn.neighbors import BallTree

            coords = np.radians(
                [[graph.nodes[n]["y"], graph.nodes[n]["x"]] for n in self._node_ids]
            )
            self._tree = BallTree(coords, metric="haversine")

    @property
    def usable(self) -> bool:
        return self.graph.number_of_nodes() > 0

    def nearest_node(self, lat: float, lon: float):
        """Return ``(node_id, snap_distance_mi)`` for the nearest trail node."""
        if self._tree is None:
            return None, float("inf")
        query = np.radians([[lat, lon]])
        dist_rad, idx = self._tree.query(query, k=1)
        node = self._node_ids[int(idx[0][0])]
        snap_mi = float(dist_rad[0][0]) * 3958.7613  # EARTH_RADIUS_MI
        return node, snap_mi

    def leg(self, a, b, by: str = "effective") -> LegResult:
        """Cost of travelling from peak-like ``a`` to ``b`` (objects with
        ``latitude``/``longitude``/``elevation_ft``)."""
        h = haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude)
        asc = max(0.0, b.elevation_ft - a.elevation_ft)
        direct = LegResult(h, asc, naismith_effective_miles(h, asc), on_trail=False)

        if not self.usable:
            return direct

        node_a, snap_a = self.nearest_node(a.latitude, a.longitude)
        node_b, snap_b = self.nearest_node(b.latitude, b.longitude)
        if snap_a > self.max_snap_mi or snap_b > self.max_snap_mi:
            return direct

        try:
            on_trail_mi = nx.shortest_path_length(
                self.graph, node_a, node_b, weight="length_mi"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return direct

        horizontal = snap_a + on_trail_mi + snap_b
        effective = naismith_effective_miles(horizontal, asc)
        return LegResult(horizontal, asc, effective, on_trail=True,
                          snap_a_mi=snap_a, snap_b_mi=snap_b)

    # Convenience accessors matching PassRouter's duck-typed interface, used
    # by build_distance_matrix / route_metrics.
    def horizontal(self, a, b) -> float:
        return self.leg(a, b, by="horizontal").horizontal_mi

    def effective_directional(self, a, b) -> float:
        return self.leg(a, b, by="effective").effective_mi


def load_trail_graph(path) -> nx.Graph:
    """Load the committed trail network (``data/trails.graphml``).

    Node ``y``/``x`` (lat/lon) and edge ``length_mi`` attributes are cast to
    float on load -- GraphML round-trips attributes as strings unless typed
    ``<key>`` declarations are present, and coercing here keeps the fetch
    script simple (see ``scripts/fetch_osm_trails.py``).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Trail graph not found: {path}")
    graph = nx.read_graphml(path)
    for _, data in graph.nodes(data=True):
        data["y"] = float(data["y"])
        data["x"] = float(data["x"])
    for _, _, data in graph.edges(data=True):
        data["length_mi"] = float(data["length_mi"])
    return graph


def build_router(graph_path, max_snap_mi: float = DEFAULT_MAX_SNAP_MI) -> TrailRouter:
    """Convenience: load the trail graph and build a :class:`TrailRouter`."""
    graph = load_trail_graph(graph_path)
    return TrailRouter(graph, max_snap_mi=max_snap_mi)
