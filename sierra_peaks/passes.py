"""Mountain passes as crest-crossing routing waypoints.

The Sierra crest is a topographic barrier: a straight-line leg between two points
on opposite sides of it is not walkable except where a pass breaches the crest.
This module models that.

Three pieces:

* :class:`Pass` / :func:`load_passes` -- the pass dataset (``data/passes.csv``),
  including a **tier** hierarchy: tier 1 = named passes / cols (the default
  crossing set and the points that define the crest line); tier 2 = minor
  gaps and saddles (available, but off by default).
* :class:`CrestModel` -- a data-driven approximation of the crest as a monotone
  longitude-vs-latitude line, fit (isotonic regression) over the tier-1 passes.
  ``side(lat, lon)`` returns ``"east"`` / ``"west"``.
* :class:`PassRouter` -- leg costs that force cross-crest travel through the
  cheapest qualifying pass; same-side legs stay direct (a peak is often reached
  without crossing any pass).

Everything here is opt-in: the clustering/pipeline default to no router and
behave exactly as before. Build one with :func:`build_router`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import math

from .distances import haversine_miles, naismith_effective_miles

# Trailing noun in a pass name -> (kind, default tier). Tier 1 features are the
# real crest crossings climbers use and define the crest line; tier 2 are the
# many minor saddles GNIS also files under feature_class "Gap".
_KIND_WORDS = {
    "pass": ("pass", 1),
    "col": ("col", 1),
    "summit": ("pass", 1),    # road summits: Echo Summit, etc.
    "divide": ("pass", 1),
    "saddle": ("saddle", 2),
    "notch": ("notch", 2),
    "gap": ("gap", 2),
}


def classify(name: str, coord_source: str = "") -> tuple[int, str]:
    """Return ``(tier, kind)`` for a pass name.

    Curated seed rows are always tier 1 regardless of their trailing noun.
    """
    last = str(name).strip().split()[-1].lower() if str(name).strip() else ""
    kind, tier = _KIND_WORDS.get(last, ("gap", 2))
    if str(coord_source).strip().lower() == "seed":
        tier = 1
    return tier, kind


@dataclass
class Pass:
    name: str
    latitude: float
    longitude: float
    elevation_ft: Optional[float] = None
    tier: int = 1
    kind: str = "pass"
    meta: dict = field(default_factory=dict)


def load_passes(path: str | Path, max_tier: Optional[int] = None) -> List[Pass]:
    """Load passes from ``data/passes.csv`` (or JSON).

    Rows missing coordinates are skipped. ``tier``/``kind`` are derived from the
    name when absent. ``max_tier`` keeps only passes at or below that tier.
    """
    import pandas as pd

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Passes file not found: {path}")
    df = pd.read_csv(path)
    passes: List[Pass] = []
    for _, r in df.iterrows():
        if pd.isna(r.get("latitude")) or pd.isna(r.get("longitude")):
            continue
        name = str(r["name"]).strip()
        if not name or name.lower() == "nan":
            continue
        src = "" if pd.isna(r.get("coord_source")) else str(r.get("coord_source"))
        tier = int(r["tier"]) if "tier" in df.columns and not pd.isna(r.get("tier")) \
            else classify(name, src)[0]
        kind = str(r["kind"]) if "kind" in df.columns and not pd.isna(r.get("kind")) \
            else classify(name, src)[1]
        elev = None if pd.isna(r.get("elevation_ft")) else float(r["elevation_ft"])
        if max_tier is not None and tier > max_tier:
            continue
        meta = {}
        for c in ("quad", "coord_source", "notes"):
            if c in df.columns and not pd.isna(r.get(c)):
                meta[c] = r[c]
        passes.append(Pass(name, float(r["latitude"]), float(r["longitude"]),
                           elev, tier, kind, meta))
    return passes


class CrestModel:
    """Monotone longitude-vs-latitude approximation of the Sierra crest.

    The crest trends west as it runs north, so longitude is a (noisy) monotone
    decreasing function of latitude. Fitting that with isotonic regression over
    the tier-1 passes yields a smooth crest line that is robust to a few passes
    sitting on interior divides. A point is ``"east"`` of the crest when its
    longitude is >= the crest longitude at its latitude, else ``"west"``.
    """

    def __init__(self, passes: Sequence[Pass], crest_tier: int = 1):
        pts = sorted(
            ((p.latitude, p.longitude) for p in passes
             if p.tier <= crest_tier and math.isfinite(p.latitude)
             and math.isfinite(p.longitude)),
            key=lambda t: t[0],
        )
        # De-duplicate identical latitudes (isotonic needs increasing x); average.
        lats: list[float] = []
        lons: list[float] = []
        for lat, lon in pts:
            if lats and abs(lat - lats[-1]) < 1e-9:
                lons[-1] = (lons[-1] + lon) / 2.0
            else:
                lats.append(lat); lons.append(lon)
        self._lats = lats
        self._lons = lons
        self._iso = None
        if len(lats) >= 2:
            from sklearn.isotonic import IsotonicRegression
            self._iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            self._iso.fit(lats, lons)

    @property
    def usable(self) -> bool:
        return self._iso is not None

    def crest_longitude(self, lat: float) -> float:
        if self._iso is None:
            return float("nan")
        return float(self._iso.predict([lat])[0])

    def side(self, lat: float, lon: float) -> str:
        if self._iso is None:
            return "unknown"
        return "east" if lon >= self.crest_longitude(lat) else "west"


@dataclass
class LegResult:
    horizontal_mi: float
    ascent_ft: float
    effective_mi: float
    via_pass: Optional[str] = None


class PassRouter:
    """Leg costs that route cross-crest travel through the cheapest pass.

    A leg between two same-side points (or when the crest model is unusable) is
    direct. A leg between opposite-side points is forced through one of the
    candidate passes (tier <= ``candidate_tier``), choosing the pass that
    minimizes the requested cost (``by="effective"`` Naismith miles, or
    ``by="horizontal"`` plain miles).
    """

    def __init__(self, passes: Sequence[Pass], crest: Optional[CrestModel] = None,
                 candidate_tier: int = 1, crest_tier: int = 1):
        self.passes = list(passes)
        self.crest = crest or CrestModel(self.passes, crest_tier=crest_tier)
        self.waypoints = [p for p in self.passes if p.tier <= candidate_tier]

    def leg(self, a, b, by: str = "effective") -> LegResult:
        """Cost of travelling from peak-like ``a`` to ``b`` (objects with
        ``latitude``/``longitude``/``elevation_ft``)."""
        h = haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude)
        asc = max(0.0, b.elevation_ft - a.elevation_ft)
        direct = LegResult(h, asc, naismith_effective_miles(h, asc), None)

        if not self.crest.usable or not self.waypoints:
            return direct
        if self.crest.side(a.latitude, a.longitude) == \
           self.crest.side(b.latitude, b.longitude):
            return direct

        best: Optional[LegResult] = None
        best_key = float("inf")
        for p in self.waypoints:
            h1 = haversine_miles(a.latitude, a.longitude, p.latitude, p.longitude)
            h2 = haversine_miles(p.latitude, p.longitude, b.latitude, b.longitude)
            hh = h1 + h2
            pelev = p.elevation_ft
            if pelev is None or not math.isfinite(pelev):
                asc_path = asc  # no pass elevation yet: fall back to endpoint gain
            else:
                asc_path = max(0.0, pelev - a.elevation_ft) + max(0.0, b.elevation_ft - pelev)
            eff = naismith_effective_miles(hh, asc_path)
            key = hh if by == "horizontal" else eff
            if key < best_key:
                best_key = key
                best = LegResult(hh, asc_path, eff, p.name)
        return best if best is not None else direct

    # Convenience accessors used by the distance matrix / route metrics.
    def horizontal(self, a, b) -> float:
        return self.leg(a, b, by="horizontal").horizontal_mi

    def effective_directional(self, a, b) -> float:
        return self.leg(a, b, by="effective").effective_mi


def build_router(
    passes_path: str | Path,
    candidate_tier: int = 1,
    crest_tier: int = 1,
) -> PassRouter:
    """Convenience: load passes and build a :class:`PassRouter`.

    ``candidate_tier`` controls which passes may be used as crossings (1 = named
    passes only; 2 = also minor gaps/saddles). ``crest_tier`` controls which
    passes define the crest line (kept at 1 so minor saddles don't distort it).
    """
    passes = load_passes(passes_path, max_tier=max(candidate_tier, crest_tier))
    crest = CrestModel(passes, crest_tier=crest_tier)
    return PassRouter(passes, crest, candidate_tier=candidate_tier, crest_tier=crest_tier)
