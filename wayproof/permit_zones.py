"""Destination zones: quota attached to where you *go*, not where you enter.

Most permit groups in this dataset quota the entry point -- Inyo NF and
Hoover count people per trailhead, so knowing your trailhead is enough to
know which quota you're competing for. Desolation Wilderness doesn't work
that way. Its quota is assigned per *destination zone*, and the booking
question is which zone you'll spend your **first night** in; after that
night you're free to move (as long as you exit by the last date booked).

That makes the zone a genuinely separate entity from both the trailhead and
the objective. A single trailhead reaches many zones, one zone is reachable
from several trailheads, and a peak climbed as a day hike needs no zone at
all. Hanging zones off ``trailheads.csv`` or ``peaks.csv`` would encode a
one-to-one relationship that doesn't exist, so they live in their own file
keyed by ``permit_group``, the same way ``release_policies.csv`` holds the
release phases that used to be prose in ``permits.csv``.

What this file deliberately does **not** claim is which zone any given
objective or trailhead sits in. The zone names are strongly suggestive --
many match a lake or peak name -- but a zone is an area with a mapped
boundary, and a name is not a boundary. The official zone map
(fs.usda.gov, Eldorado NF) shows the numbered zones as geometry, not as a
lookup table; until that geometry is actually read, "which zone do I book
for X" stays an open question rather than a guess. See ``open_questions()``
in :mod:`wayproof.reports`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

DESTINATION_ZONE = "destination_zone"
THRU_HIKE = "thru_hike"


@dataclass
class PermitZone:
    """One row of ``data/permit_zones.csv``: one bookable zone for a permit group."""

    permit_group: str
    zone_name: str
    zone_type: str = DESTINATION_ZONE
    zone_code: Optional[int] = None
    source_url: str = ""
    verified_date: str = ""
    notes: str = ""

    @property
    def label(self) -> str:
        """How the zone appears in the agency's own booking UI."""
        if self.zone_code is None:
            return self.zone_name
        return f"{self.zone_code:02d} {self.zone_name}"


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _int_or_none(value) -> Optional[int]:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return int(value)


def load_permit_zones(
    path: str | Path = "data/permit_zones.csv",
) -> Dict[str, List[PermitZone]]:
    """Load bookable permit zones, grouped by permit_group and ordered by code.

    Returns an empty dict if the file doesn't exist -- zones are extra detail
    for the minority of permit groups that quota by destination, not required
    input for a permit lookup. A group absent from this file simply isn't
    zone-quota'd (or hasn't been researched yet).
    """
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)

    by_group: Dict[str, List[PermitZone]] = {}
    for _, row in df.iterrows():
        group = _str_field(row, "permit_group")
        name = _str_field(row, "zone_name")
        if not group or not name:
            continue
        by_group.setdefault(group, []).append(PermitZone(
            permit_group=group,
            zone_name=name,
            zone_type=_str_field(row, "zone_type") or DESTINATION_ZONE,
            zone_code=_int_or_none(row.get("zone_code")),
            source_url=_str_field(row, "source_url"),
            verified_date=_str_field(row, "verified_date"),
            notes=_str_field(row, "notes"),
        ))

    # Numbered zones first in code order, then unnumbered ones (e.g. a
    # thru-hike option) alphabetically -- matching how the booking UI lists them.
    for zones in by_group.values():
        zones.sort(key=lambda z: (z.zone_code is None, z.zone_code or 0, z.zone_name))
    return by_group
