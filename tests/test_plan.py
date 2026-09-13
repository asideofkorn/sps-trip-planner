"""Tests for the plan module (wayproof.plan).

Run with:  python -m pytest tests/test_plan.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.access import load_approaches
from wayproof.camping import load_campgrounds, load_campsites
from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.park_access import load_park_access
from wayproof.permits import load_permits
from wayproof.plan import resolve_plan, format_plan_summary
from wayproof.water import load_water_sources, load_water_source_log

PEAKS = os.path.join(os.path.dirname(__file__), "..", "data", "peaks.csv")
COLLECTIONS = os.path.join(os.path.dirname(__file__), "..", "data", "collections", "sps.csv")
TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")
PERMITS = os.path.join(os.path.dirname(__file__), "..", "data", "permits.csv")
RELEASE_POLICIES = os.path.join(os.path.dirname(__file__), "..", "data", "release_policies.csv")
APPROACHES = os.path.join(os.path.dirname(__file__), "..", "data", "approaches.csv")
WATER_SOURCES = os.path.join(os.path.dirname(__file__), "..", "data", "water_sources.csv")
WATER_SOURCE_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "water_source_log.csv")
CAMPGROUNDS = os.path.join(os.path.dirname(__file__), "..", "data", "campgrounds.csv")
CAMPSITES = os.path.join(os.path.dirname(__file__), "..", "data", "campsites.csv")
PARK_ACCESS = os.path.join(os.path.dirname(__file__), "..", "data", "park_access.csv")


def _inputs(list_filter="SPS"):
    peaks = load_peaks(PEAKS, list_filter=list_filter, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    approaches = load_approaches(APPROACHES)
    return peaks, trailheads, permits, approaches


def test_resolve_plan_single_objective_matches_case_insensitively():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["mount whitney"], date(2027, 7, 15), peaks, trailheads,
                           permits, approaches=approaches)
    assert not result.not_found
    assert [p.name for p in result.objectives] == ["Mount Whitney"]
    assert result.trailhead is not None
    assert result.trailhead.name == "Whitney Portal"
    assert len(result.permit_entries) == 1
    assert not result.trailhead_ambiguous


def test_resolve_plan_shared_trailhead_surfaces_approach_override():
    # Mirrors test_permits.test_mount_russell_approach_surfaces_second_permit,
    # but through the plan entry point end to end.
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney", "Mount Russell"], date(2027, 7, 1),
                           peaks, trailheads, permits, approaches=approaches)
    assert not result.not_found
    assert result.trailhead.name == "Whitney Portal"
    assert not result.trailhead_ambiguous  # both default to Whitney Portal
    assert len(result.permit_entries) == 2
    default_entry = next(e for e in result.permit_entries if not e.peak_note)
    russell_entry = next(e for e in result.permit_entries if e.peak_note)
    assert "Whitney" in default_entry.permit_type
    assert "Mount Russell" in russell_entry.peak_note
    assert russell_entry.approach_status == "confirmed"


def test_resolve_plan_reports_not_found_objectives():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney", "Not A Real Peak"], date(2027, 7, 15),
                           peaks, trailheads, permits, approaches=approaches)
    assert result.not_found == ["Not A Real Peak"]
    assert any("Not A Real Peak" in w for w in result.warnings)
    # The one real objective still resolves.
    assert [p.name for p in result.objectives] == ["Mount Whitney"]
    assert result.trailhead is not None


def test_resolve_plan_flags_mismatched_default_trailheads():
    # Independence Peak defaults to Onion Valley, not Whitney Portal -- a
    # plan combining it with Mount Whitney should flag the mismatch rather
    # than silently picking one.
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney", "Independence Peak"], date(2027, 7, 15),
                           peaks, trailheads, permits, approaches=approaches)
    assert result.trailhead_ambiguous
    assert any("do not share the same default trailhead" in w for w in result.warnings)


def test_resolve_plan_no_objectives_found():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Not A Real Peak"], date(2027, 7, 15),
                           peaks, trailheads, permits, approaches=approaches)
    assert result.objectives == []
    assert result.trailhead is None
    assert result.permit_entries == []
    summary = format_plan_summary(result)
    assert "nothing to plan" in summary.lower()


def test_format_plan_summary_includes_official_mileage():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney"], date(2027, 7, 15), peaks, trailheads,
                           permits, approaches=approaches)
    summary = format_plan_summary(result)
    assert "MOUNT WHITNEY" in summary   # the title line is upper-cased by the renderer
    assert "mi round trip" in summary
    assert "not a computed combined route" in summary.lower()


def test_full_dataset_loads_without_cross_list_name_collisions():
    # A couple of names ("Mount Johnson", "Thunder Mountain") used to exist
    # under both list=SPS and list=non-SPS with conflicting elevations,
    # crashing an unfiltered load. scripts/split_collections.py now applies a
    # documented SPS-preferred tie-break when producing data/peaks.csv and
    # data/collections/sps.csv, so this should no longer raise -- this is
    # exactly why plan.py can default --list to "all" now. The underlying
    # discrepancy (which value is actually correct, not just which list to
    # prefer) is still a separate, tracked follow-up.
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    assert len({p.name for p in peaks}) == len(peaks)


def test_plan_result_to_dict_is_json_serializable():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney", "Mount Russell"], date(2027, 7, 1),
                           peaks, trailheads, permits, approaches=approaches)
    payload = result.to_dict()
    serialized = json.dumps(payload)  # must not raise
    assert "Mount Whitney" in serialized
    assert payload["trailhead"]["name"] == "Whitney Portal"
    assert len(payload["permits"]) == 2


def test_resolve_plan_surfaces_open_questions_for_rose_peak():
    # End-to-end check of the scavenger-hunt nudge, against the real
    # committed data: Rose Peak's nearest trailhead (Del Valle (Lichen Bark))
    # has two water sources with no recorded coordinates yet.
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    approaches = load_approaches(APPROACHES)
    water_sources = load_water_sources(WATER_SOURCES)
    water_source_log = load_water_source_log(WATER_SOURCE_LOG)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    campsites = load_campsites(CAMPSITES)

    result = resolve_plan(["Rose Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           approaches=approaches, water_sources=water_sources,
                           water_source_log=water_source_log, campgrounds=campgrounds,
                           campsites=campsites)

    assert result.open_questions
    targets = {q.target_key for q in result.open_questions}
    assert "Lichen Bark (Del Valle)" in targets
    assert "Stromer Springs" in targets
    # Global-only gaps (e.g. Boyd Camp's water conflict, Sunol campsite
    # proximity) must not leak into a Rose-Peak-scoped plan.
    assert "Boyd Camp" not in targets


def test_resolve_plan_without_facilities_data_has_no_open_questions():
    # The new optional params must be fully backward compatible -- an
    # existing caller that doesn't pass them still works exactly as before.
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney"], date(2027, 7, 15), peaks, trailheads,
                           permits, approaches=approaches)
    assert result.open_questions == []


def test_format_plan_summary_includes_help_us_confirm_section():
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    water_sources = load_water_sources(WATER_SOURCES)

    result = resolve_plan(["Mission Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           water_sources=water_sources)
    summary = format_plan_summary(result)
    assert "Help us confirm" in summary
    assert "GNIS" in summary


def test_resolve_plan_populates_facilities_for_rose_peak():
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    water_sources = load_water_sources(WATER_SOURCES)
    water_source_log = load_water_source_log(WATER_SOURCE_LOG)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    campsites = load_campsites(CAMPSITES)
    park_access = list(load_park_access(PARK_ACCESS).values())

    result = resolve_plan(["Rose Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           water_sources=water_sources, water_source_log=water_source_log,
                           campgrounds=campgrounds, campsites=campsites, park_access=park_access)

    assert result.facilities is not None
    water_names = {w.name for w in result.facilities.water_sources}
    assert "Stromer Springs" in water_names
    assert result.facilities.water_status["Stromer Springs"].observed_status == "running"

    campground_names = {c.name for c in result.facilities.campgrounds}
    assert "Del Valle Family Campground" in campground_names
    assert "Eagle Springs" not in campground_names  # Mission Peak's, not Rose Peak's

    assert result.facilities.park_access is not None
    assert result.facilities.park_access.park == "Del Valle Regional Park"


def test_resolve_plan_mission_peak_facilities_dont_leak_del_valle_campgrounds():
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    park_access = list(load_park_access(PARK_ACCESS).values())

    result = resolve_plan(["Mission Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           campgrounds=campgrounds, park_access=park_access)

    campground_names = {c.name for c in result.facilities.campgrounds}
    assert campground_names == {"Eagle Springs"}
    # Mission Peak Regional Preserve has no park_access.csv row -- must not
    # silently show Del Valle's fee/hours as if they applied here too.
    assert result.facilities.park_access is None


def test_resolve_plan_sierra_peak_has_no_facilities():
    # No water_sources/campgrounds/park_access data exists for Sierra
    # trailheads -- facilities must stay None, not an empty-but-present object.
    peaks, trailheads, permits, approaches = _inputs()
    water_sources = load_water_sources(WATER_SOURCES)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    park_access = list(load_park_access(PARK_ACCESS).values())

    result = resolve_plan(["Mount Whitney"], date(2027, 7, 15), peaks, trailheads, permits,
                           approaches=approaches, water_sources=water_sources,
                           campgrounds=campgrounds, park_access=park_access)
    assert result.facilities is None


def test_format_plan_summary_includes_facilities_section():
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    water_sources = load_water_sources(WATER_SOURCES)
    water_source_log = load_water_source_log(WATER_SOURCE_LOG)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    campsites = load_campsites(CAMPSITES)
    park_access = list(load_park_access(PARK_ACCESS).values())

    result = resolve_plan(["Rose Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           water_sources=water_sources, water_source_log=water_source_log,
                           campgrounds=campgrounds, campsites=campsites, park_access=park_access)
    summary = format_plan_summary(result)
    assert "Facilities" in summary
    assert "Del Valle Family Campground" in summary
    assert "Park access (Del Valle Regional Park)" in summary
    assert "Entrance fee: $10" in summary


def test_facilities_serializes_to_json():
    peaks = load_peaks(PEAKS, list_filter=None, collections_path=COLLECTIONS)
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    water_sources = load_water_sources(WATER_SOURCES)
    campgrounds = load_campgrounds(CAMPGROUNDS)
    campsites = load_campsites(CAMPSITES)
    park_access = list(load_park_access(PARK_ACCESS).values())

    result = resolve_plan(["Rose Peak"], date(2027, 6, 1), peaks, trailheads, permits,
                           water_sources=water_sources, campgrounds=campgrounds,
                           campsites=campsites, park_access=park_access)
    payload = result.to_dict()
    json.dumps(payload)  # must not raise
    assert "facilities" in payload
    assert payload["facilities"]["park_access"]["park"] == "Del Valle Regional Park"
    campground_payload = next(c for c in payload["facilities"]["campgrounds"]
                               if c["name"] == "Del Valle Family Campground")
    assert "approximate" in campground_payload["nightly_entry_cutoff"].lower()
