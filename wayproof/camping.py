"""Backpack campgrounds and their individually-bookable campsites.

A campground is a physical cluster with shared infrastructure (a restroom, a
water source, one reservation contact) at one location. Some campgrounds --
Boyd Camp, Stewart's Camp -- are effectively a single bookable site; others,
like Sunol Backpack Camp, contain several individually-named sites (Cathedral,
Eagles Aerie, Hawks Nest...) that share the campground's facilities but have
their own capacity and, sometimes, a genuinely different proximity to those
shared facilities (e.g. Hawks Nest is closer to both water and the restroom
than Sunol Backpack Camp's other sites).

That's why this is two files, not one: ``data/campgrounds.csv`` (the shared,
physical facts -- location, restroom, water source, how to reserve) and
``data/campsites.csv`` (the individually-bookable units within a campground).
A campground with no differentiated sub-sites simply has no rows in
``campsites.csv`` -- don't invent a placeholder row that just repeats the
campground's own name.
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


def _bool_field(row, col: str) -> bool:
    val = row.get(col)
    if val is None or pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


@dataclass
class Campground:
    """One row of ``data/campgrounds.csv``: a physical camping cluster."""

    name: str
    park: str
    land_agency: str = ""
    has_restroom: bool = False
    restroom_type: str = ""
    reservation_method: str = ""
    reservation_contact: str = ""
    checkin_time: str = ""
    checkout_time: str = ""
    nightly_entry_cutoff: str = ""
    fee_notes: str = ""
    notes: str = ""


@dataclass
class Campsite:
    """One row of ``data/campsites.csv``: an individually-bookable site
    within a :class:`Campground`."""

    name: str
    campground: str
    capacity: int = 0
    water_proximity: str = ""
    restroom_proximity: str = ""
    notes: str = ""


def load_campgrounds(path: str | Path = "data/campgrounds.csv") -> List[Campground]:
    """Load campgrounds. Returns an empty list if the file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    campgrounds: List[Campground] = []
    for _, row in df.iterrows():
        name = _str_field(row, "name")
        if not name:
            continue
        campgrounds.append(Campground(
            name=name,
            park=_str_field(row, "park"),
            land_agency=_str_field(row, "land_agency"),
            has_restroom=_bool_field(row, "has_restroom"),
            restroom_type=_str_field(row, "restroom_type"),
            reservation_method=_str_field(row, "reservation_method"),
            reservation_contact=_str_field(row, "reservation_contact"),
            checkin_time=_str_field(row, "checkin_time"),
            checkout_time=_str_field(row, "checkout_time"),
            nightly_entry_cutoff=_str_field(row, "nightly_entry_cutoff"),
            fee_notes=_str_field(row, "fee_notes"),
            notes=_str_field(row, "notes"),
        ))
    return campgrounds


def load_campsites(path: str | Path = "data/campsites.csv") -> List[Campsite]:
    """Load campsites. Returns an empty list if the file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    campsites: List[Campsite] = []
    for _, row in df.iterrows():
        name = _str_field(row, "name")
        if not name:
            continue
        capacity = row.get("capacity")
        campsites.append(Campsite(
            name=name,
            campground=_str_field(row, "campground"),
            capacity=int(capacity) if capacity is not None and not pd.isna(capacity) else 0,
            water_proximity=_str_field(row, "water_proximity"),
            restroom_proximity=_str_field(row, "restroom_proximity"),
            notes=_str_field(row, "notes"),
        ))
    return campsites


def campsites_by_campground(sites: List[Campsite]) -> Dict[str, List[Campsite]]:
    """Index campsites by their campground's name."""
    by_campground: Dict[str, List[Campsite]] = {}
    for s in sites:
        by_campground.setdefault(s.campground, []).append(s)
    return by_campground
