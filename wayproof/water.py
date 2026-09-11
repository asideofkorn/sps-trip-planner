"""Backcountry water sources and their append-only availability ledger.

Unlike a coordinate or an elevation, "is this water source currently
running" is not a fact that stays true once recorded -- a spigot fed by a
spring can run dry (or start running again) with no announcement. Treating
that as a single mutable field would silently discard the previous answer
every time it's rechecked, and would flatten "an official source says it's
running" and "a hiker says it looked dry last week" into the same kind of
claim.

``data/water_sources.csv`` holds the static facts (name, type, associated
trailhead/campground). ``data/water_source_log.csv`` is the append-only
ledger of dated checks against it -- the same confirms/conflicts pattern as
:mod:`wayproof.permits`'s ``SourceLogEntry``, generalized to a fact that
isn't a permit at all. A source can accumulate an official check and a
firsthand field report on different dates, and a later check never erases an
earlier one -- see :func:`latest_status_by_source` for reducing the ledger
down to the newest entry per source. ``observed_status`` is free text rather
than a controlled vocabulary (unlike :mod:`wayproof.permits`'s
``SourceLogEntry.verdict``), so a genuine disagreement between two entries --
e.g. an official source saying a spigot is available while this project's own
trip notes say otherwise -- is something a human records explicitly in
``notes`` rather than something this module detects automatically.
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


def _float_or_none(val):
    if val is None or pd.isna(val) or (isinstance(val, str) and not val.strip()):
        return None
    return float(val)


@dataclass
class WaterSource:
    """One row of ``data/water_sources.csv``: a named backcountry water source."""

    name: str
    type: str = ""
    potable: bool = False
    location: str = ""  # name of the associated trailhead or campground
    latitude: float | None = None
    longitude: float | None = None
    notes: str = ""


@dataclass
class WaterSourceLogEntry:
    """One row of ``data/water_source_log.csv``: a dated check of a water source."""

    water_source_name: str
    checked_date: str
    source: str
    observed_status: str
    notes: str = ""


def load_water_sources(path: str | Path = "data/water_sources.csv") -> List[WaterSource]:
    """Load water sources. Returns an empty list if the file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    sources: List[WaterSource] = []
    for _, row in df.iterrows():
        name = _str_field(row, "name")
        if not name:
            continue
        potable = row.get("potable")
        sources.append(WaterSource(
            name=name,
            type=_str_field(row, "type"),
            potable=bool(potable) if potable is not None and not pd.isna(potable) else False,
            location=_str_field(row, "location"),
            latitude=_float_or_none(row.get("latitude")),
            longitude=_float_or_none(row.get("longitude")),
            notes=_str_field(row, "notes"),
        ))
    return sources


def load_water_source_log(
    path: str | Path = "data/water_source_log.csv",
) -> List[WaterSourceLogEntry]:
    """Load the append-only water-source check ledger, oldest first as stored.

    Returns an empty list if the file doesn't exist -- the ledger is optional
    context layered on top of ``water_sources.csv``, not required input.
    """
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    entries: List[WaterSourceLogEntry] = []
    for _, row in df.iterrows():
        name = _str_field(row, "water_source_name")
        if not name:
            continue
        entries.append(WaterSourceLogEntry(
            water_source_name=name,
            checked_date=_str_field(row, "checked_date"),
            source=_str_field(row, "source"),
            observed_status=_str_field(row, "observed_status"),
            notes=_str_field(row, "notes"),
        ))
    return entries


def log_by_source(
    entries: List[WaterSourceLogEntry],
) -> Dict[str, List[WaterSourceLogEntry]]:
    """Index log entries by water source name, ordered oldest to newest."""
    by_source: Dict[str, List[WaterSourceLogEntry]] = {}
    for e in entries:
        by_source.setdefault(e.water_source_name, []).append(e)
    for group in by_source.values():
        group.sort(key=lambda e: e.checked_date)
    return by_source


def latest_status_by_source(
    entries: List[WaterSourceLogEntry],
) -> Dict[str, WaterSourceLogEntry]:
    """The most recently checked-date entry per water source."""
    return {name: group[-1] for name, group in log_by_source(entries).items()}
