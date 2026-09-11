"""Tests for the plan module (sierra_peaks.plan).

Run with:  python -m pytest tests/test_plan.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sierra_peaks.access import load_approaches
from sierra_peaks.data_loader import load_peaks, load_trailheads
from sierra_peaks.permits import load_permits
from sierra_peaks.plan import resolve_plan, format_plan_summary

PEAKS = os.path.join(os.path.dirname(__file__), "..", "data", "sps_peaks.csv")
TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")
PERMITS = os.path.join(os.path.dirname(__file__), "..", "data", "permits.csv")
RELEASE_POLICIES = os.path.join(os.path.dirname(__file__), "..", "data", "release_policies.csv")
APPROACHES = os.path.join(os.path.dirname(__file__), "..", "data", "approaches.csv")


def _inputs():
    # SPS-only, matching plan.py's default -- the full dataset (list_filter=None)
    # currently has a couple of known cross-list name collisions (see the
    # "Fix duplicate peak names" follow-up), which is exactly why that's a
    # default a caller opts into, not the default itself.
    peaks = load_peaks(PEAKS, list_filter="SPS")
    trailheads = load_trailheads(TRAILHEADS)
    permits = load_permits(PERMITS, RELEASE_POLICIES)
    approaches = load_approaches(APPROACHES)
    return peaks, trailheads, permits, approaches


def test_resolve_plan_single_objective_matches_case_insensitively():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["mount whitney"], date(2027, 7, 15), peaks, trailheads,
                           permits, approaches=approaches)
    assert not result.not_found
    assert [p.name for p in result.objectives] == ["MOUNT WHITNEY"]
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
    assert [p.name for p in result.objectives] == ["MOUNT WHITNEY"]
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
    assert "MOUNT WHITNEY" in summary
    assert "mi round trip" in summary
    assert "not a computed combined route" in summary.lower()


def test_full_dataset_has_known_cross_list_name_collisions():
    # Documents a known, pre-existing data issue (tracked separately): loading
    # the unfiltered dataset currently raises on a couple of names that exist
    # under both list=SPS and list=non-SPS with conflicting elevations. This
    # is exactly why plan.py defaults --list to "SPS" rather than "all".
    import pytest
    with pytest.raises(ValueError, match="Duplicate peak name"):
        load_peaks(PEAKS, list_filter=None)


def test_plan_result_to_dict_is_json_serializable():
    peaks, trailheads, permits, approaches = _inputs()
    result = resolve_plan(["Mount Whitney", "Mount Russell"], date(2027, 7, 1),
                           peaks, trailheads, permits, approaches=approaches)
    payload = result.to_dict()
    serialized = json.dumps(payload)  # must not raise
    assert "MOUNT WHITNEY" in serialized
    assert payload["trailhead"]["name"] == "Whitney Portal"
    assert len(payload["permits"]) == 2
