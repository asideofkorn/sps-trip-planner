"""Serialize ranked clusters to the JSON export schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

from .model import Cluster
from .clustering import ClusterConfig


def clusters_to_payload(
    clusters: Sequence[Cluster], config: Optional[ClusterConfig] = None
) -> dict:
    """Build the full export dict: summary + per-cluster itineraries."""
    total_peaks = sum(c.num_peaks for c in clusters)
    total_days = sum(c.estimated_days for c in clusters)
    payload = {
        "summary": {
            "num_clusters": len(clusters),
            "total_peaks": total_peaks,
            "total_estimated_days": total_days,
            "total_distance_mi": round(sum(c.total_distance_mi for c in clusters), 2),
            "total_elevation_gain_ft": round(
                sum(c.total_elevation_gain_ft for c in clusters), 0
            ),
        },
        "clusters": [c.to_dict() for c in clusters],
    }
    if config is not None:
        payload["config"] = {
            "eps_mi": config.eps_mi,
            "miles_per_day": config.miles_per_day,
            "max_days": config.max_days,
            "max_effective_mi": config.max_effective_mi,
            "method": config.method,
            "exclude": config.exclude,
            "force_together": config.force_together,
        }
    return payload


def save_json(
    clusters: Sequence[Cluster],
    path: str | Path,
    config: Optional[ClusterConfig] = None,
) -> None:
    payload = clusters_to_payload(clusters, config)
    Path(path).write_text(json.dumps(payload, indent=2))
