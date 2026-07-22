"""Tests for the permit-lookup module.

Run with:  python -m pytest tests/test_permits.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sierra_peaks.data_loader import load_trailheads
from sierra_peaks.model import Cluster, Peak
from sierra_peaks.permits import (
    load_permits,
    permit_status,
    clusters_permit_info,
    format_permit_report,
)

TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")
PERMITS = os.path.join(os.path.dirname(__file__), "..", "data", "permits.csv")


def test_load_permits_covers_every_trailhead_group():
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    groups = {t.permit_group for t in trailheads if t.permit_group}
    assert groups <= set(permits)


def test_free_group_never_needs_reservation():
    permits = load_permits(PERMITS)
    rule = permits["stanislaus_free"]
    assert not rule.quota_required
    assert "self-issue" in permit_status(rule, date(2027, 7, 4)).lower()


def test_none_group_has_no_permit():
    permits = load_permits(PERMITS)
    rule = permits["none"]
    assert permit_status(rule, date(2027, 7, 4)) == "No wilderness permit required."


def test_inyo_quota_season_reservation_window():
    permits = load_permits(PERMITS)
    rule = permits["inyo_jmw_aaw"]
    trip = date(2027, 7, 15)
    assert rule.in_quota_season(trip)
    opens = trip - __import__("datetime").timedelta(days=rule.reservation_window_days)
    # Before the window opens: told to wait.
    status_before = permit_status(rule, trip, today=opens - __import__("datetime").timedelta(days=1))
    assert "reservations open" in status_before.lower()
    # After the window opens: told it's open.
    status_after = permit_status(rule, trip, today=opens)
    assert "open" in status_after.lower()


def test_inyo_outside_quota_season_is_self_issue():
    permits = load_permits(PERMITS)
    rule = permits["inyo_jmw_aaw"]
    trip = date(2027, 12, 15)  # outside May 1 - Nov 1
    assert not rule.in_quota_season(trip)
    assert "outside" in permit_status(rule, trip).lower()


def test_whitney_zone_lottery_phases():
    permits = load_permits(PERMITS)
    rule = permits["whitney_zone"]
    trip = date(2027, 8, 1)
    before_open = permit_status(rule, trip, today=date(2027, 1, 15))
    assert "opens" in before_open.lower()
    during_lottery = permit_status(rule, trip, today=date(2027, 2, 15))
    assert "open now" in during_lottery.lower()
    after_results = permit_status(rule, trip, today=date(2027, 4, 1))
    assert "claim" in after_results.lower()
    after_release = permit_status(rule, trip, today=date(2027, 5, 1))
    assert "first-come" in after_release.lower()


def test_cpma_is_day_of_only():
    permits = load_permits(PERMITS)
    rule = permits["cpma"]
    trip = date(2027, 7, 15)
    assert rule.in_quota_season(trip)
    assert "first-come" in permit_status(rule, trip).lower()


def test_clusters_permit_info_needs_trailhead():
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    c = Cluster(cluster_id=0, peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505)])
    assert clusters_permit_info([c], trailheads, permits, date(2027, 7, 1)) == []

    c.trailhead = "Whitney Portal"
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1))
    assert len(rows) == 1
    assert rows[0].agency == "Inyo National Forest"
    assert "Whitney" in rows[0].permit_type
    assert format_permit_report(rows)


def test_format_permit_report_empty():
    assert "no permit info" in format_permit_report([]).lower()
