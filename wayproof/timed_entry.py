"""Year-scoped vehicle timed-entry / reservation requirements.

Unlike a permit_group's release rules (:mod:`wayproof.release_policy`) or a
park's flat entrance fee and gate hours (:mod:`wayproof.park_access`),
whether a park requires a timed-entry vehicle reservation at all is a
decision some land agencies re-make every year based on the prior season's
traffic data -- not a standing policy. Yosemite has flipped between
requiring one, not requiring one, and requiring one only for specific date
windows in nearly every year since 2020 (see ``data/timed_entry.csv`` for
the recorded history).

Flattening that into a single "current state" field on
``data/park_access.csv`` would silently overwrite history every time the
policy changes -- exactly the failure mode ``data/water_source_log.csv`` and
``data/permit_source_log.csv`` already exist to avoid. ``data/timed_entry.csv``
instead keeps one row per ``(park, year)``, so a given year's actual policy
is a permanent historical record, never overwritten by the next year's
decision.

This intentionally is not itself a computable release-phase model like
:mod:`wayproof.release_policy` -- ``date_range``/``hours`` are free text,
since a given year's actual windows (e.g. 2024's separate Horsetail Fall
reservation on top of its general peak-hours program) haven't shown enough
of a stable pattern across years to justify structured phases yet. That's a
natural extension once (and if) a clearer recurring shape emerges.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _bool_field(row, col: str) -> bool:
    val = row.get(col)
    if val is None or pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


@dataclass
class TimedEntryPolicy:
    """One row of ``data/timed_entry.csv``: one park's reservation
    requirement for one specific year."""

    park: str
    year: int
    required: bool
    date_range: str = ""
    hours: str = ""
    mechanism: str = ""
    source_url: str = ""
    notes: str = ""


def load_timed_entry(
    path: str | Path = "data/timed_entry.csv",
) -> Dict[str, List[TimedEntryPolicy]]:
    """Load timed-entry history, grouped by park and ordered oldest to newest.

    Returns an empty dict if the file doesn't exist -- most of this
    project's coverage (national forest trailheads, EBRPD land) has no such
    vehicle-reservation program at all.
    """
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)

    by_park: Dict[str, List[TimedEntryPolicy]] = {}
    for _, row in df.iterrows():
        park = _str_field(row, "park")
        if not park:
            continue
        by_park.setdefault(park, []).append(TimedEntryPolicy(
            park=park,
            year=int(row["year"]),
            required=_bool_field(row, "required"),
            date_range=_str_field(row, "date_range"),
            hours=_str_field(row, "hours"),
            mechanism=_str_field(row, "mechanism"),
            source_url=_str_field(row, "source_url"),
            notes=_str_field(row, "notes"),
        ))
    for policies in by_park.values():
        policies.sort(key=lambda p: p.year)
    return by_park


def policy_for_year(
    by_park: Dict[str, List[TimedEntryPolicy]], park: str, year: int,
) -> Optional[TimedEntryPolicy]:
    """The recorded policy for a specific park and year, or ``None`` if that
    year isn't on file yet -- callers must not assume the most recent known
    year's policy still applies to an un-recorded year."""
    for p in by_park.get(park, []):
        if p.year == year:
            return p
    return None


def latest_policy(
    by_park: Dict[str, List[TimedEntryPolicy]], park: str,
) -> Optional[TimedEntryPolicy]:
    """The most recently recorded year's policy for a park, or ``None``."""
    policies = by_park.get(park)
    return policies[-1] if policies else None
