"""Order peaks within a cluster by solving an open-path TSP.

We solve an *open* Hamiltonian path (no forced return to the start) because a
peak-bagging trip generally enters the range, tags summits in sequence, and
exits — minimizing on-route backtracking rather than closing a loop.

Small clusters (<= ``BRUTE_FORCE_MAX`` peaks) are solved exactly by brute force.
Larger clusters use nearest-neighbor construction refined with 2-opt.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Sequence

import numpy as np

from .model import Peak
from .distances import haversine_miles, naismith_effective_miles

BRUTE_FORCE_MAX = 8


def _path_cost(order: Sequence[int], cost: np.ndarray) -> float:
    return float(sum(cost[order[i], order[i + 1]] for i in range(len(order) - 1)))


def _brute_force(cost: np.ndarray) -> List[int]:
    n = cost.shape[0]
    nodes = list(range(n))
    best_order = nodes
    best = float("inf")
    # Fix the first node and reverse-dedupe by only keeping perms whose first
    # endpoint index is <= last, halving the search for symmetric costs.
    for perm in itertools.permutations(nodes[1:]):
        order = [nodes[0], *perm]
        c = _path_cost(order, cost)
        if c < best:
            best, best_order = c, order
    # Also consider permutations where node 0 is not the start, by trying every
    # node as a fixed start (cheap for the small n we brute force).
    for start in nodes[1:]:
        rest = [x for x in nodes if x != start]
        for perm in itertools.permutations(rest):
            order = [start, *perm]
            c = _path_cost(order, cost)
            if c < best:
                best, best_order = c, order
    return list(best_order)


def _nearest_neighbor(cost: np.ndarray, start: int) -> List[int]:
    n = cost.shape[0]
    unvisited = set(range(n))
    unvisited.discard(start)
    order = [start]
    cur = start
    while unvisited:
        nxt = min(unvisited, key=lambda j: cost[cur, j])
        order.append(nxt)
        unvisited.discard(nxt)
        cur = nxt
    return order


def _two_opt(order: List[int], cost: np.ndarray) -> List[int]:
    improved = True
    best = order[:]
    best_cost = _path_cost(best, cost)
    while improved:
        improved = False
        n = len(best)
        for i in range(n - 1):
            for k in range(i + 1, n):
                if i == 0 and k == n - 1:
                    continue
                candidate = best[:i] + best[i : k + 1][::-1] + best[k + 1 :]
                c = _path_cost(candidate, cost)
                if c + 1e-9 < best_cost:
                    best, best_cost = candidate, c
                    improved = True
    return best


def solve_tsp(cost: np.ndarray) -> List[int]:
    """Return the peak index order minimizing total open-path travel cost."""
    n = cost.shape[0]
    if n <= 1:
        return list(range(n))
    if n <= 2:
        return [0, 1]
    if n <= BRUTE_FORCE_MAX:
        return _brute_force(cost)
    # Heuristic: best nearest-neighbor seed, refined with 2-opt.
    best_order, best_cost = None, float("inf")
    for start in range(n):
        order = _two_opt(_nearest_neighbor(cost, start), cost)
        c = _path_cost(order, cost)
        if c < best_cost:
            best_order, best_cost = order, c
    return best_order


def route_metrics(ordered_peaks: Sequence[Peak]) -> Dict[str, float]:
    """Compute travel totals for a fixed sequence of peaks.

    Returns horizontal miles, Naismith effective miles, and cumulative ascent
    (positive elevation gain summed leg-by-leg along the route).
    """
    horizontal = 0.0
    ascent = 0.0
    effective = 0.0
    for a, b in zip(ordered_peaks, ordered_peaks[1:]):
        h = haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude)
        asc = max(0.0, b.elevation_ft - a.elevation_ft)
        horizontal += h
        ascent += asc
        effective += naismith_effective_miles(h, asc)
    return {
        "horizontal_mi": horizontal,
        "effective_mi": effective,
        "elevation_gain_ft": ascent,
    }
