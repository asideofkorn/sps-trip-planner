"""Core data structures: Peak and Cluster."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Peak:
    """A single summit on the SPS list.

    Attributes
    ----------
    name : str
        Human-readable peak name (used as the unique key throughout the tool).
    latitude, longitude : float
        Decimal degrees (WGS84). Longitude is negative in the western hemisphere.
    elevation_ft : float
        Summit elevation in feet.
    region : str
        Optional grouping label (e.g. "Palisades"). Informational only.
    meta : dict
        Optional extra attributes carried from the source data (class, section,
        emblem/mountaineers flags, round-trip mileage, gain, trailhead, quad...).
        Surfaced in the JSON export but not used by the geometry/clustering.
    """

    name: str
    latitude: float
    longitude: float
    elevation_ft: float
    region: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_ft": self.elevation_ft,
        }
        if self.region:
            d["region"] = self.region
        if self.meta:
            d["attributes"] = self.meta
        return d


@dataclass
class Cluster:
    """A proposed peak-bagging trip: a set of peaks plus a computed itinerary.

    The geometry fields (order, distances, gain, days) are filled in by the
    pipeline once a TSP route has been solved. ``score`` is assigned during
    ranking; higher is more efficient.
    """

    cluster_id: int
    peaks: List[Peak]
    order: List[str] = field(default_factory=list)
    total_distance_mi: float = 0.0
    total_effective_mi: float = 0.0
    total_elevation_gain_ft: float = 0.0
    estimated_days: int = 0
    score: float = 0.0

    @property
    def peak_names(self) -> List[str]:
        return [p.name for p in self.peaks]

    @property
    def num_peaks(self) -> int:
        return len(self.peaks)

    def to_dict(self) -> dict:
        """Serialize to the export schema."""
        d = {
            "cluster_id": self.cluster_id,
            "num_peaks": self.num_peaks,
            "peaks": [p.to_dict() for p in self.peaks],
            "recommended_order": self.order,
            "total_distance_mi": round(self.total_distance_mi, 2),
            "total_effective_mi": round(self.total_effective_mi, 2),
            "total_elevation_gain_ft": round(self.total_elevation_gain_ft, 0),
            "estimated_days": self.estimated_days,
            "efficiency_score": round(self.score, 4),
        }
        emblem = sum(1 for p in self.peaks if p.meta.get("emblem"))
        mountaineers = sum(1 for p in self.peaks if p.meta.get("mountaineers"))
        if emblem or mountaineers:
            d["emblem_peaks"] = emblem
            d["mountaineers_peaks"] = mountaineers
        return d
