"""Core data structures: Peak, Trailhead, and candidate Cluster."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Peak:
    """A single summit objective.

    Conceptually, ``Peak`` is one *type* of place-based objective this
    project can plan around; a named list like the Sierra Peaks Section is
    one **collection** of such objectives (see :attr:`collection`), not the
    ontology of the whole project. Loop routes, traverses, and multi-peak
    objectives that aren't a single summit are a natural extension of this
    same idea, not modeled here yet.

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
        Surfaced in the JSON export but not used by the geometry/grouping.
    """

    name: str
    latitude: float
    longitude: float
    elevation_ft: float
    region: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def collection(self) -> str:
        """The named collection this objective belongs to (e.g. ``"SPS"``).

        Read from ``meta["list"]``, the same field ``--list`` filters on.
        Blank if the source data didn't tag a list/collection.
        """
        return str(self.meta.get("list", "") or "")

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
class Trailhead:
    """A road-accessible trip start/end point.

    Loaded from ``data/trailheads.csv``. Used to model the approach hike from
    the car to the first summit (and the descent from the last summit back).
    """

    name: str
    latitude: float
    longitude: float
    elevation_ft: float = 0.0
    side: str = ""          # "east", "west", or "crest"
    notes: str = ""
    wilderness_area: str = ""
    land_agency: str = ""
    permit_group: str = ""  # key into data/permits.csv; "" if unclassified


@dataclass
class Cluster:
    """A candidate peak grouping plus a computed sequence.

    The geometry fields (order, distances, gain, days) are filled in by the
    pipeline once a TSP sequence has been solved. ``score`` is assigned during
    ranking; higher means denser by the project's effort heuristic.

    The ``approach_*`` / ``trailhead*`` fields are populated only when approach
    modeling is enabled (see :class:`~wayproof.clustering.ClusterConfig`).
    They cover the walk from the trailhead to the first summit and back from the
    last; the ``total_*`` figures then include that approach.
    """

    cluster_id: int
    peaks: List[Peak]
    order: List[str] = field(default_factory=list)
    total_distance_mi: float = 0.0
    total_effective_mi: float = 0.0
    total_elevation_gain_ft: float = 0.0
    estimated_days: int = 0
    score: float = 0.0
    passes: List[str] = field(default_factory=list)  # crest passes crossed by the candidate sequence
    # Approach (trailhead <-> sequence endpoints); zero/empty when not modeled.
    trailhead: str = ""
    trailhead_side: str = ""
    approach_distance_mi: float = 0.0
    approach_effective_mi: float = 0.0
    approach_gain_ft: float = 0.0

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
        if self.passes:
            # Ordered, de-duplicated list of crest passes the sequence crosses.
            seen: dict = {}
            d["passes_crossed"] = [seen.setdefault(p, p) for p in self.passes
                                   if p not in seen]
        if self.trailhead:
            d["trailhead"] = self.trailhead
            d["trailhead_side"] = self.trailhead_side
            d["approach_distance_mi"] = round(self.approach_distance_mi, 2)
            d["approach_effective_mi"] = round(self.approach_effective_mi, 2)
            d["approach_gain_ft"] = round(self.approach_gain_ft, 0)
        emblem = sum(1 for p in self.peaks if p.meta.get("emblem"))
        mountaineers = sum(1 for p in self.peaks if p.meta.get("mountaineers"))
        if emblem or mountaineers:
            d["emblem_peaks"] = emblem
            d["mountaineers_peaks"] = mountaineers
        return d
