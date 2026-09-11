"""Park-level vehicle entrance fees, gate hours, and fee exemptions.

This is a distinct concept from both :mod:`wayproof.permits` (backcountry
wilderness-entry permits, keyed by ``permit_group``) and
:mod:`wayproof.camping` (individual campsite reservations): some land
agencies -- East Bay Regional Park District, unlike the Sierra's national
forests -- gate vehicle access to the park itself with a day-use fee and
posted operating hours, independent of whether any backcountry permit or
campsite reservation is involved at all. Forcing that into ``permits.csv``'s
quota-season model would leave most of its columns meaningless (there's no
quota here), so it gets its own small, flat file instead.

Confidence varies by field here more than elsewhere in this project: a park's
posted fee and hours are usually independently verifiable from the agency's
own page, but a fee *exemption* (e.g. "backpackers picking up a shuttled car
don't pay") is often something visitors are told verbally at the gate rather
than something published anywhere. Record that distinction in ``notes``
rather than implying every field here carries the same evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


@dataclass
class ParkAccess:
    """One row of ``data/park_access.csv``: a park's vehicle entrance rules."""

    park: str
    land_agency: str = ""
    entrance_fee: str = ""
    fee_conditions: str = ""
    fee_exemptions: str = ""
    gate_open: str = ""
    gate_close: str = ""
    gate_hours_conditions: str = ""
    source_url: str = ""
    verified_date: str = ""
    notes: str = ""


def load_park_access(path: str | Path = "data/park_access.csv") -> Dict[str, ParkAccess]:
    """Load park-level access rules, keyed by park name.

    Returns an empty dict if the file doesn't exist -- most of this project's
    coverage (national forest trailheads) has no such vehicle gate at all.
    """
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)

    by_park: Dict[str, ParkAccess] = {}
    for _, row in df.iterrows():
        park = _str_field(row, "park")
        if not park:
            continue
        by_park[park] = ParkAccess(
            park=park,
            land_agency=_str_field(row, "land_agency"),
            entrance_fee=_str_field(row, "entrance_fee"),
            fee_conditions=_str_field(row, "fee_conditions"),
            fee_exemptions=_str_field(row, "fee_exemptions"),
            gate_open=_str_field(row, "gate_open"),
            gate_close=_str_field(row, "gate_close"),
            gate_hours_conditions=_str_field(row, "gate_hours_conditions"),
            source_url=_str_field(row, "source_url"),
            verified_date=_str_field(row, "verified_date"),
            notes=_str_field(row, "notes"),
        )
    return by_park
