"""Manual cluster editing: merge, split, exclude, and re-plan.

These operate on a list of already-built :class:`Cluster` objects and return a
fresh list of peak groups, which the caller re-runs through the pipeline so that
TSP order, metrics, and ranking stay consistent after every edit.
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from .model import Peak, Cluster
from .distances import build_distance_matrix


def clusters_to_groups(clusters: Sequence[Cluster]) -> List[List[Peak]]:
    """Extract the raw peak groups from a list of clusters."""
    return [list(c.peaks) for c in clusters]


def merge_clusters(
    clusters: Sequence[Cluster], cluster_ids: Sequence[int]
) -> List[List[Peak]]:
    """Merge the clusters with the given IDs into a single group."""
    ids = set(cluster_ids)
    merged: List[Peak] = []
    groups: List[List[Peak]] = []
    for c in clusters:
        if c.cluster_id in ids:
            merged.extend(c.peaks)
        else:
            groups.append(list(c.peaks))
    if merged:
        groups.append(merged)
    return groups


def split_cluster(
    clusters: Sequence[Cluster], cluster_id: int, k: int = 2
) -> List[List[Peak]]:
    """Split one cluster into ``k`` sub-groups by geographic proximity."""
    groups: List[List[Peak]] = []
    for c in clusters:
        if c.cluster_id != cluster_id:
            groups.append(list(c.peaks))
            continue
        peaks = list(c.peaks)
        if k >= len(peaks):
            groups.extend([[p] for p in peaks])
            continue
        coords = np.array([[p.latitude, p.longitude] for p in peaks])
        labels = AgglomerativeClustering(n_clusters=k).fit_predict(coords)
        for lbl in range(k):
            sub = [p for p, l in zip(peaks, labels) if l == lbl]
            if sub:
                groups.append(sub)
    return groups


def exclude_peaks(
    clusters: Sequence[Cluster], peak_names: Sequence[str]
) -> List[List[Peak]]:
    """Drop the named peaks from all clusters."""
    drop = set(peak_names)
    groups: List[List[Peak]] = []
    for c in clusters:
        kept = [p for p in c.peaks if p.name not in drop]
        if kept:
            groups.append(kept)
    return groups


def force_together(
    clusters: Sequence[Cluster], peak_names: Sequence[str]
) -> List[List[Peak]]:
    """Pull the named peaks out of their clusters and into one shared group."""
    want = set(peak_names)
    pulled: List[Peak] = []
    groups: List[List[Peak]] = []
    for c in clusters:
        kept = [p for p in c.peaks if p.name not in want]
        pulled.extend([p for p in c.peaks if p.name in want])
        if kept:
            groups.append(kept)
    if pulled:
        groups.append(pulled)
    return groups
