"""Tests for the campground/campsite, water-source, and park-access modules.

Run with:  python -m pytest tests/test_facilities.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.camping import (
    Campground,
    Campsite,
    load_campgrounds,
    load_campsites,
    campsites_by_campground,
)
from wayproof.water import (
    WaterSource,
    WaterSourceLogEntry,
    load_water_sources,
    load_water_source_log,
    log_by_source,
    latest_status_by_source,
)
from wayproof.park_access import ParkAccess, load_park_access

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CAMPGROUNDS = os.path.join(DATA, "campgrounds.csv")
CAMPSITES = os.path.join(DATA, "campsites.csv")
WATER_SOURCES = os.path.join(DATA, "water_sources.csv")
WATER_SOURCE_LOG = os.path.join(DATA, "water_source_log.csv")
PARK_ACCESS = os.path.join(DATA, "park_access.csv")


# --- campgrounds / campsites -------------------------------------------------

def test_load_campgrounds_reads_committed_data():
    campgrounds = load_campgrounds(CAMPGROUNDS)
    by_name = {c.name: c for c in campgrounds}
    assert "Sunol Backpack Camp" in by_name
    sunol = by_name["Sunol Backpack Camp"]
    assert sunol.has_restroom is True
    assert sunol.restroom_type == "pit toilet"
    assert "ReserveAmerica" in sunol.reservation_method


def test_load_campgrounds_missing_file_returns_empty(tmp_path):
    assert load_campgrounds(tmp_path / "nope.csv") == []


def test_del_valle_family_campground_has_nightly_cutoff_caveat():
    campgrounds = load_campgrounds(CAMPGROUNDS)
    by_name = {c.name: c for c in campgrounds}
    del_valle = by_name["Del Valle Family Campground"]
    assert "10:00 PM" in del_valle.nightly_entry_cutoff
    assert "approximate" in del_valle.nightly_entry_cutoff.lower()


def test_load_campsites_reads_committed_data():
    sites = load_campsites(CAMPSITES)
    by_name = {s.name: s for s in sites}
    assert by_name["Eagles Aerie"].capacity == 10
    assert by_name["Hawks Nest"].water_proximity == "closest to water"
    assert by_name["Hawks Nest"].restroom_proximity == "near-ish"
    # Sites with no noted proximity difference stay blank rather than guessed.
    assert by_name["Cathedral"].water_proximity == ""


def test_load_campsites_missing_file_returns_empty(tmp_path):
    assert load_campsites(tmp_path / "nope.csv") == []


def test_campsites_by_campground_groups_all_seven_sunol_sites():
    sites = load_campsites(CAMPSITES)
    grouped = campsites_by_campground(sites)
    assert len(grouped["Sunol Backpack Camp"]) == 7


def test_single_site_campgrounds_have_no_campsites_rows():
    # Boyd Camp etc. aren't split into named sub-sites -- no placeholder rows
    # that just repeat the campground's own name.
    sites = load_campsites(CAMPSITES)
    names = {s.campground for s in sites}
    assert names == {"Sunol Backpack Camp"}


# --- water sources / ledger ---------------------------------------------------

def test_load_water_sources_reads_committed_data():
    sources = load_water_sources(WATER_SOURCES)
    by_name = {s.name: s for s in sources}
    assert "Sunol Backpack Camp" in by_name
    stromer = by_name["Stromer Springs"]
    assert stromer.potable is False
    assert stromer.type == "spigot (spring-fed)"


def test_load_water_sources_missing_file_returns_empty(tmp_path):
    assert load_water_sources(tmp_path / "nope.csv") == []


def test_load_water_source_log_reads_committed_data():
    entries = load_water_source_log(WATER_SOURCE_LOG)
    assert len(entries) > 0
    assert all(isinstance(e, WaterSourceLogEntry) for e in entries)


def test_boyd_camp_has_official_and_conflicting_field_entries():
    entries = load_water_source_log(WATER_SOURCE_LOG)
    boyd = [e for e in entries if e.water_source_name == "Boyd Camp"]
    assert len(boyd) == 2
    official = [e for e in boyd if "EBRPD" in e.source]
    assert official and official[0].observed_status == "running"
    conflicting = [e for e in boyd if "contradicts" in e.observed_status]
    assert conflicting


def test_latest_status_by_source_picks_newest_dated_entry():
    entries = [
        WaterSourceLogEntry("Test Spring", "2026-01-01", "official", "running"),
        WaterSourceLogEntry("Test Spring", "2026-06-01", "field report", "dry"),
    ]
    latest = latest_status_by_source(entries)
    assert latest["Test Spring"].observed_status == "dry"
    assert latest["Test Spring"].checked_date == "2026-06-01"


def test_log_by_source_orders_oldest_to_newest():
    entries = [
        WaterSourceLogEntry("Test Spring", "2026-06-01", "b", "dry"),
        WaterSourceLogEntry("Test Spring", "2026-01-01", "a", "running"),
    ]
    grouped = log_by_source(entries)
    dates = [e.checked_date for e in grouped["Test Spring"]]
    assert dates == ["2026-01-01", "2026-06-01"]


# --- park access ---------------------------------------------------------------

def test_load_park_access_reads_committed_data():
    by_park = load_park_access(PARK_ACCESS)
    assert "Del Valle Regional Park" in by_park
    del_valle = by_park["Del Valle Regional Park"]
    assert del_valle.entrance_fee == "$10"
    assert del_valle.gate_open == "6:00 AM"
    assert "shuttled car" in del_valle.fee_exemptions


def test_park_access_fee_exemption_confidence_is_documented_separately():
    by_park = load_park_access(PARK_ACCESS)
    del_valle = by_park["Del Valle Regional Park"]
    # The exemption is a verbal staff confirmation, not an independently
    # published fact -- that distinction must survive into the data, not be
    # silently flattened to the same confidence as the fee/hours.
    assert "verbal" in del_valle.fee_exemptions.lower() or "verbal" in del_valle.notes.lower()


def test_load_park_access_missing_file_returns_empty_dict(tmp_path):
    assert load_park_access(tmp_path / "nope.csv") == {}
