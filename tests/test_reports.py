"""Tests for wayproof.reports: open_questions() and the report queue.

Run with:  python -m pytest tests/test_reports.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from wayproof.access import ApproachRoute
from wayproof.camping import Campground, Campsite
from wayproof.model import Peak
from wayproof.reports import (
    OpenQuestion,
    Report,
    open_questions,
    pending_reports,
    resolve_report,
    submit_report,
)
from wayproof.water import WaterSource, WaterSourceLogEntry


def _peak(name, coord_source="GNIS", nearest_trailhead=""):
    meta = {"coord_source": coord_source}
    if nearest_trailhead:
        meta["nearest_trailhead"] = nearest_trailhead
    return Peak(name=name, latitude=37.0, longitude=-121.0, elevation_ft=3000, meta=meta)


# --- open_questions: approaches -------------------------------------------

def test_unconfirmed_approach_produces_a_question():
    peaks = [_peak("Mount Irvine")]
    approaches = [ApproachRoute(
        peak_name="Mount Irvine", trailhead="Whitney Portal",
        approach_name="Meysan Lake Trail", permit_group="", status="unconfirmed",
    )]
    qs = open_questions(peaks=peaks, approaches=approaches, peak_names=["Mount Irvine"])
    assert len(qs) == 1
    assert qs[0].target_file == "data/approaches.csv"
    assert "Mount Irvine" in qs[0].question


def test_confirmed_approach_produces_no_question():
    peaks = [_peak("Mount Russell")]
    approaches = [ApproachRoute(
        peak_name="Mount Russell", trailhead="Whitney Portal",
        approach_name="Mountaineers Route", permit_group="inyo_jmw_aaw", status="confirmed",
    )]
    qs = open_questions(peaks=peaks, approaches=approaches, peak_names=["Mount Russell"])
    assert qs == []


def test_peak_filter_excludes_other_peaks_unconfirmed_approach():
    peaks = [_peak("Mount Irvine"), _peak("Mount Mallory")]
    approaches = [
        ApproachRoute(peak_name="Mount Irvine", trailhead="Whitney Portal",
                      approach_name="Meysan Lake Trail", permit_group="", status="unconfirmed"),
        ApproachRoute(peak_name="Mount Mallory", trailhead="Whitney Portal",
                      approach_name="Meysan Lake Trail", permit_group="", status="unconfirmed"),
    ]
    qs = open_questions(peaks=peaks, approaches=approaches, peak_names=["Mount Irvine"])
    assert len(qs) == 1
    assert qs[0].context == "Mount Irvine"


# --- open_questions: peak coordinate source --------------------------------

def test_unconfirmed_coord_source_produces_a_question():
    peaks = [_peak("Mission Peak", coord_source="USGS topo (GNIS ID unconfirmed)")]
    qs = open_questions(peaks=peaks, peak_names=["Mission Peak"])
    assert len(qs) == 1
    assert qs[0].target_file == "data/peaks.csv"


def test_confirmed_gnis_coord_source_produces_no_question():
    peaks = [_peak("Rose Peak", coord_source="GNIS")]
    qs = open_questions(peaks=peaks, peak_names=["Rose Peak"])
    assert qs == []


# --- open_questions: water sources -----------------------------------------

def test_water_source_missing_coords_is_peak_filterable_via_trailhead():
    peaks = [_peak("Rose Peak", nearest_trailhead="Del Valle (Lichen Bark)")]
    sources = [WaterSource(name="Lichen Bark (Del Valle)", location="Del Valle (Lichen Bark)")]
    qs = open_questions(peaks=peaks, water_sources=sources, peak_names=["Rose Peak"])
    assert len(qs) == 1
    assert qs[0].target_file == "data/water_sources.csv"


def test_water_source_at_unrelated_trailhead_not_included_for_this_peak():
    peaks = [_peak("Rose Peak", nearest_trailhead="Del Valle (Lichen Bark)")]
    sources = [WaterSource(name="Stanford Ave Staging Area", location="Stanford Ave Staging Area")]
    qs = open_questions(peaks=peaks, water_sources=sources, peak_names=["Rose Peak"])
    assert qs == []


def test_water_source_with_coords_produces_no_missing_coords_question():
    peaks = [_peak("Rose Peak", nearest_trailhead="Del Valle (Lichen Bark)")]
    sources = [WaterSource(name="Lichen Bark (Del Valle)", location="Del Valle (Lichen Bark)",
                            latitude=37.6, longitude=-121.7)]
    qs = open_questions(peaks=peaks, water_sources=sources, peak_names=["Rose Peak"])
    assert qs == []


def test_conflicting_log_entries_surface_only_in_global_view():
    sources = [WaterSource(name="Boyd Camp", location="Boyd Camp")]
    log = [
        WaterSourceLogEntry("Boyd Camp", "2026-09-02", "official", "running"),
        WaterSourceLogEntry("Boyd Camp", "2026-09-04", "trip notes",
                             "unclear -- contradicts official source"),
    ]
    global_qs = open_questions(water_sources=sources, water_source_log=log, peak_names=None)
    assert any("disagree" in q.question for q in global_qs)

    # Not linkable to a specific peak's trailhead -- omitted from a filtered view.
    peaks = [_peak("Rose Peak", nearest_trailhead="Del Valle (Lichen Bark)")]
    filtered_qs = open_questions(peaks=peaks, water_sources=sources, water_source_log=log,
                                  peak_names=["Rose Peak"])
    assert filtered_qs == []


def test_no_log_at_all_flagged_in_global_view():
    sources = [WaterSource(name="Untested Spring", location="Nowhere")]
    qs = open_questions(water_sources=sources, water_source_log=[], peak_names=None)
    assert any("No availability check" in q.question for q in qs)


# --- open_questions: campsites / campgrounds (global view only) -----------

def test_campsite_missing_both_proximity_fields_flagged_globally():
    sites = [Campsite(name="Cathedral", campground="Sunol Backpack Camp", capacity=5)]
    qs = open_questions(campsites=sites, peak_names=None)
    assert len(qs) == 1
    assert qs[0].target_file == "data/campsites.csv"


def test_campsite_with_one_proximity_field_not_flagged():
    sites = [Campsite(name="Hawks Nest", campground="Sunol Backpack Camp", capacity=5,
                       water_proximity="closest to water")]
    qs = open_questions(campsites=sites, peak_names=None)
    assert qs == []


def test_campground_uncertain_note_flagged_globally():
    grounds = [Campground(name="Del Valle Family Campground", park="Del Valle Regional Park",
                           nightly_entry_cutoff="~10:00 PM (approximate, not a confirmed posted time)")]
    qs = open_questions(campgrounds=grounds, peak_names=None)
    assert len(qs) == 1
    assert "Del Valle Family Campground" in qs[0].target_key


# --- report queue -----------------------------------------------------------

def test_submit_and_read_back_report(tmp_path):
    path = tmp_path / "pending_reports.csv"
    report = submit_report("data/water_sources.csv", "Boyd Camp", "It was running when I passed",
                            evidence="saw it flowing", confidence="firsthand", path=path)
    assert report.report_id == "R0001"
    assert report.status == "pending"

    reports = pending_reports(path)
    assert len(reports) == 1
    assert reports[0].claim == "It was running when I passed"


def test_submit_report_rejects_invalid_confidence(tmp_path):
    with pytest.raises(ValueError):
        submit_report("f", "k", "claim", confidence="bogus", path=tmp_path / "r.csv")


def test_report_ids_increment(tmp_path):
    path = tmp_path / "pending_reports.csv"
    r1 = submit_report("f", "k1", "claim1", path=path)
    r2 = submit_report("f", "k2", "claim2", path=path)
    assert r1.report_id == "R0001"
    assert r2.report_id == "R0002"


def test_pending_reports_missing_file_returns_empty(tmp_path):
    assert pending_reports(tmp_path / "nope.csv") == []


def test_resolve_report_updates_status_and_notes(tmp_path):
    path = tmp_path / "pending_reports.csv"
    report = submit_report("f", "k", "claim", path=path)
    resolved = resolve_report(report.report_id, "accepted", "confirmed via a second source", path=path)
    assert resolved.status == "accepted"
    assert resolved.resolution_notes == "confirmed via a second source"

    reloaded = pending_reports(path)
    assert reloaded[0].status == "accepted"


def test_resolve_report_rejects_invalid_status(tmp_path):
    path = tmp_path / "pending_reports.csv"
    report = submit_report("f", "k", "claim", path=path)
    with pytest.raises(ValueError):
        resolve_report(report.report_id, "bogus-status", path=path)


def test_resolve_report_unknown_id_raises(tmp_path):
    path = tmp_path / "pending_reports.csv"
    submit_report("f", "k", "claim", path=path)
    with pytest.raises(ValueError):
        resolve_report("R9999", "accepted", path=path)
