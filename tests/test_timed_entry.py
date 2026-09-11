"""Tests for the year-scoped timed-entry module (wayproof.timed_entry).

Run with:  python -m pytest tests/test_timed_entry.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.timed_entry import (
    TimedEntryPolicy,
    load_timed_entry,
    policy_for_year,
    latest_policy,
)

TIMED_ENTRY = os.path.join(os.path.dirname(__file__), "..", "data", "timed_entry.csv")


def test_load_timed_entry_reads_committed_data():
    by_park = load_timed_entry(TIMED_ENTRY)
    assert "Yosemite National Park" in by_park
    years = [p.year for p in by_park["Yosemite National Park"]]
    assert years == sorted(years)
    assert 2020 in years and 2026 in years


def test_load_timed_entry_missing_file_returns_empty_dict(tmp_path):
    assert load_timed_entry(tmp_path / "nope.csv") == {}


def test_policy_for_year_finds_exact_year():
    by_park = load_timed_entry(TIMED_ENTRY)
    p2025 = policy_for_year(by_park, "Yosemite National Park", 2025)
    assert p2025 is not None
    assert p2025.required is True
    assert "Jun 15" in p2025.date_range


def test_policy_for_year_returns_none_for_unrecorded_year():
    # Must not silently fall back to a neighboring year's policy -- a
    # reservation requirement is a decision made fresh each year.
    by_park = load_timed_entry(TIMED_ENTRY)
    assert policy_for_year(by_park, "Yosemite National Park", 2019) is None
    assert policy_for_year(by_park, "Yosemite National Park", 2030) is None


def test_year_to_year_policy_actually_varies():
    # Guards against someone "simplifying" this into a single current-state
    # field -- the whole point is that it's genuinely not stable year to year.
    by_park = load_timed_entry(TIMED_ENTRY)
    required_by_year = {p.year: p.required for p in by_park["Yosemite National Park"]}
    assert required_by_year[2022] is True
    assert required_by_year[2023] is False
    assert required_by_year[2024] is True
    assert required_by_year[2026] is False


def test_latest_policy_is_most_recent_year():
    by_park = load_timed_entry(TIMED_ENTRY)
    latest = latest_policy(by_park, "Yosemite National Park")
    assert latest.year == 2026
    assert latest.required is False


def test_latest_policy_missing_park_returns_none():
    by_park = load_timed_entry(TIMED_ENTRY)
    assert latest_policy(by_park, "Some Park Not On File") is None


def test_dataclass_defaults():
    p = TimedEntryPolicy(park="Test Park", year=2027, required=True)
    assert p.date_range == ""
    assert p.hours == ""
    assert p.mechanism == ""
