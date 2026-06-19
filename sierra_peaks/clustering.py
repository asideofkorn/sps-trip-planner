"""Group peaks into capacity-constrained, geographically tight clusters.

Two-stage strategy:

1. **Spatial grouping** — DBSCAN over the haversine distance matrix finds
   natural geographic clusters at a chosen reachability radius (``eps_mi``).
   Outliers become their own singleton trips.
2. **Capacity splitting** — any group whose optimal TSP route exceeds the trip
   budget (``max_effective_mi``, i.e. up to ``max_days`` of hiking) is
   recursively split with agglomerative clustering until every trip fits.

Must-link constraints (``force_together``) are honored by treating linked peaks
as a single atomic unit that is never separated during grouping or splitting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from sklearn.cluster import DBSCAN, AgglomerativeClustering

from .model import Peak
from .distances import build_distance_matrix, haversine_miles
from .tsp import solve_tsp, route_metrics


@dataclass
class ClusterConfig:
    """Tunable parameters for clustering and the trip budget."""

    eps_mi: float = 6.0           # DBSCAN reachability radius (horizontal miles)
    min_samples: int = 1          # DBSCAN core-point threshold
    miles_per_day: float = 15.0   # daily hiking budget (effective miles)
    max_days: int = 3             # cap on trip length
    method: str = "dbscan"        # "dbscan" or "agglomerative"
    exclude: List[str] = field(default_factory=list)
    force_together: List[List[str]] = field(default_factory=list)
    by_trailhead: bool = False    # keep peaks sharing a trailhead in one trip
    trailhead_field: str = "trailhead"      # meta key to group on when by_trailhead
    trailhead_max_mi: Optional[float] = None  # cap: only link same-TH peaks within this

    @property
    def max_effective_mi(self) -> float:
        return self.miles_per_day * self.max_days


def _route_effective_mi(peaks: Sequence[Peak]) -> float:
    """Nearest-neighbor estimate of the open-path effective length, in miles.

    Used only for capacity-feasibility checks during splitting. Nearest-neighbor
    yields a path no shorter than the optimal, so it is a valid upper bound: if
    this estimate fits the budget, the optimal route fits too. Much faster than a
    full TSP solve, which keeps statewide (~250 peak) clustering tractable.
    """
    n = len(peaks)
    if n <= 1:
        return 0.0
    cost = build_distance_matrix(peaks, metric="effective")
    visited = [False] * n
    visited[0] = True
    cur, total = 0, 0.0
    for _ in range(n - 1):
        nxt, best = -1, float("inf")
        for j in range(n):
            if not visited[j] and cost[cur, j] < best:
                best, nxt = cost[cur, j], j
        total += best
        visited[nxt] = True
        cur = nxt
    return total


def _build_units(
    peaks: Sequence[Peak], force_together: Sequence[Sequence[str]]
) -> List[List[Peak]]:
    """Collapse must-link groups into atomic units (lists of peaks)."""
    by_name = {p.name: p for p in peaks}

    # Union-find over names that must stay together.
    parent: Dict[str, str] = {p.name: p.name for p in peaks}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for group in force_together:
        members = [m for m in group if m in by_name]
        for other in members[1:]:
            union(members[0], other)

    buckets: Dict[str, List[Peak]] = {}
    for p in peaks:
        buckets.setdefault(find(p.name), []).append(p)
    return list(buckets.values())


def _split_by_proximity(unit: Sequence[Peak], max_mi: float) -> List[List[Peak]]:
    """Connected components of ``unit`` where edges join peaks within ``max_mi``.

    Used to keep trailhead grouping from lumping together peaks that merely share
    a (sometimes very long) trail name, e.g. the PCT.
    """
    n = len(unit)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if haversine_miles(unit[i].latitude, unit[i].longitude,
                               unit[j].latitude, unit[j].longitude) <= max_mi:
                parent[find(i)] = find(j)

    comps: Dict[int, List[Peak]] = {}
    for i, p in enumerate(unit):
        comps.setdefault(find(i), []).append(p)
    return list(comps.values())


def _trailhead_groups(
    peaks: Sequence[Peak], field_name: str = "trailhead",
    max_mi: Optional[float] = None,
) -> List[List[str]]:
    """Group peak names by their trailhead metadata.

    Peaks reached from the same trailhead form a must-link group, so they end up
    in the same trip. Peaks with no trailhead are left ungrouped. When ``max_mi``
    is given, a trailhead's peaks are further split so only peaks within that
    straight-line distance of each other are linked.
    """
    buckets: Dict[str, List[Peak]] = {}
    for p in peaks:
        th = p.meta.get(field_name)
        if th is None:
            continue
        key = str(th).strip()
        if key:
            buckets.setdefault(key, []).append(p)

    groups: List[List[str]] = []
    for members in buckets.values():
        subunits = ([members] if max_mi is None
                    else _split_by_proximity(members, max_mi))
        for su in subunits:
            if len(su) > 1:
                groups.append([p.name for p in su])
    return groups


def _unit_centroid(unit: Sequence[Peak]) -> Tuple[float, float]:
    return (
        float(np.mean([p.latitude for p in unit])),
        float(np.mean([p.longitude for p in unit])),
    )


def _split_to_budget(
    units: List[List[Peak]], max_effective_mi: float
) -> List[List[List[Peak]]]:
    """Split a list of units into sub-groups that each fit the trip budget.

    Returns a list of sub-groups, where each sub-group is itself a list of units.
    """
    flat_peaks = [p for u in units for p in u]
    if len(units) <= 1 or _route_effective_mi(flat_peaks) <= max_effective_mi:
        return [units]

    centroids = np.array([_unit_centroid(u) for u in units])
    n = len(units)
    # Start near the obvious lower bound (total effort / budget) instead of 2,
    # so we don't waste time on small k that cannot possibly fit a big cluster.
    k0 = max(2, int(_route_effective_mi(flat_peaks) // max_effective_mi) + 1)
    for k in range(min(k0, n), n + 1):
        labels = AgglomerativeClustering(n_clusters=k).fit_predict(centroids)
        subgroups: List[List[List[Peak]]] = [[] for _ in range(k)]
        for unit, lbl in zip(units, labels):
            subgroups[int(lbl)].append(unit)
        subgroups = [sg for sg in subgroups if sg]
        if all(
            _route_effective_mi([p for u in sg for p in u]) <= max_effective_mi
            for sg in subgroups
        ):
            return subgroups
    # Could not satisfy the budget even fully split: one unit per group.
    return [[u] for u in units]


def cluster_peaks(
    peaks: Sequence[Peak], config: Optional[ClusterConfig] = None
) -> List[List[Peak]]:
    """Cluster peaks into budget-respecting trips.

    Returns a list of clusters, each a list of :class:`Peak`. Ordering and
    metrics are computed later by the pipeline.
    """
    config = config or ClusterConfig()

    excluded = {name for name in config.exclude}
    active = [p for p in peaks if p.name not in excluded]
    if not active:
        return []

    link_groups = list(config.force_together)
    if config.by_trailhead:
        link_groups += _trailhead_groups(
            active, config.trailhead_field, config.trailhead_max_mi
        )
    units = _build_units(active, link_groups)

    # Stage 1: spatial grouping over unit centroids.
    if len(units) == 1:
        groups: List[List[List[Peak]]] = [units]
    else:
        centroids = [
            Peak(name=f"u{i}", latitude=c[0], longitude=c[1], elevation_ft=0.0)
            for i, c in enumerate(_unit_centroid(u) for u in units)
        ]
        dist = build_distance_matrix(centroids, metric="haversine")
        if config.method == "agglomerative":
            # Distance-threshold agglomerative grouping (no fixed k).
            labels = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=config.eps_mi,
                metric="precomputed",
                linkage="average",
            ).fit_predict(dist)
        else:
            labels = DBSCAN(
                eps=config.eps_mi,
                min_samples=config.min_samples,
                metric="precomputed",
            ).fit_predict(dist)

        grouped: Dict[int, List[List[Peak]]] = {}
        noise_id = -1
        for unit, lbl in zip(units, labels):
            key = lbl
            if lbl == -1:  # DBSCAN noise -> unique singleton group
                key = noise_id
                noise_id -= 1
            grouped.setdefault(key, []).append(unit)
        groups = list(grouped.values())

    # Stage 2: enforce trip budget.
    final: List[List[Peak]] = []
    for group in groups:
        for subgroup in _split_to_budget(group, config.max_effective_mi):
            final.append([p for u in subgroup for p in u])

    # Stable ordering: north-to-south by mean latitude.
    final.sort(key=lambda c: -np.mean([p.latitude for p in c]))
    return final
