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
    load_permit_overrides,
    permit_status,
    clusters_permit_info,
    format_permit_report,
)

TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")
PERMITS = os.path.join(os.path.dirname(__file__), "..", "data", "permits.csv")
OVERRIDES = os.path.join(os.path.dirname(__file__), "..", "data", "permit_overrides.csv")


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


def test_cpma_off_season_is_not_self_issue():
    # Unlike the generic free/self-issue off-season assumption, CPMA's winter
    # permits require contacting the Amador Ranger District directly.
    permits = load_permits(PERMITS)
    rule = permits["cpma"]
    trip = date(2027, 12, 15)
    assert not rule.in_quota_season(trip)
    status = permit_status(rule, trip).lower()
    assert "should be free/self-issue" not in status  # generic fallback phrasing
    assert "amador" in status


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


def test_sierra_nf_quota_is_year_round():
    # fs.usda.gov/r05/sierra: quotas apply year-round, no off-season exemption.
    permits = load_permits(PERMITS)
    rule = permits["sierra_nf"]
    assert rule.quota_season_start is None
    assert rule.in_quota_season(date(2027, 1, 15))   # winter
    assert rule.in_quota_season(date(2027, 7, 15))   # summer
    winter_status = permit_status(rule, date(2027, 1, 15), today=date(2026, 7, 22))
    assert "outside" not in winter_status.lower()
    assert "open" in winter_status.lower()


def test_interagency_reciprocity_surfaces_for_boundary_trailheads():
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    th_by_name = {t.name: t for t in trailheads}

    # Sierra NF permit at Isberg/Clover Meadow covers the Yosemite-side leg.
    isberg = th_by_name["Isberg (Clover Meadow)"]
    rule = permits[isberg.permit_group]
    assert "yosemite" in rule.interagency_note.lower()

    c = Cluster(cluster_id=0, peaks=[Peak("Foerster Peak", 37.63, -119.34, 12058)],
                trailhead="Isberg (Clover Meadow)")
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1))
    assert "yosemite" in rows[0].interagency_note.lower()
    assert "crosses into other land" in format_permit_report(rows).lower()


def test_format_permit_report_empty():
    assert "no permit info" in format_permit_report([]).lower()


def test_inyo_gtw_has_different_season_than_general_inyo():
    # Cottonwood (GT-coded trails) uses a shorter season than the JM/AA
    # May 1 - Nov 1 window -- confirmed against Inyo NF's own trail table.
    permits = load_permits(PERMITS)
    general = permits["inyo_jmw_aaw"]
    gtw = permits["inyo_gtw"]
    assert gtw.quota_season_start != general.quota_season_start
    assert gtw.in_quota_season(date(2027, 7, 15))       # within Jun 26 - Sep 15
    assert not gtw.in_quota_season(date(2027, 5, 15))   # before season, unlike general Inyo
    assert not gtw.in_quota_season(date(2027, 10, 15))  # after season, unlike general Inyo


def test_horseshoe_meadows_uses_gtw_season_not_general():
    trailheads = load_trailheads(TRAILHEADS)
    th = next(t for t in trailheads if t.name == "Horseshoe Meadows (Cottonwood)")
    assert th.permit_group == "inyo_gtw"


def test_inyo_hoover_portion_is_non_quota():
    # Lundy Canyon and Saddlebag Lake are Inyo NF (not Humboldt-Toiyabe) and
    # non-quota, per Inyo NF's own official trail/quota table (HH01, HH04).
    trailheads = load_trailheads(TRAILHEADS)
    th_by_name = {t.name: t for t in trailheads}
    permits = load_permits(PERMITS)

    lundy = th_by_name["Lundy Canyon"]
    assert lundy.land_agency == "Inyo NF"
    assert lundy.permit_group == "inyo_hoover_nonquota"

    saddlebag = th_by_name["Saddlebag Lake"]
    assert saddlebag.land_agency == "Inyo NF"
    assert saddlebag.permit_group == "inyo_hoover_nonquota"

    rule = permits["inyo_hoover_nonquota"]
    assert not rule.quota_required
    assert "self-issue" in permit_status(rule, date(2027, 7, 15)).lower()


def test_mount_russell_override_surfaces_second_permit():
    # Whitney Portal defaults to the Whitney Zone lottery, but Mount Russell
    # (Mountaineers Route / North Fork of Lone Pine Creek) needs the regular
    # Inyo NF permit instead -- both should show up for a mixed trip.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    overrides = load_permit_overrides(OVERRIDES)
    assert overrides.get("Mount Russell") == "inyo_jmw_aaw"

    c = Cluster(
        cluster_id=0,
        peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505),
               Peak("Mount Russell", 36.595, -118.303, 14094)],
        trailhead="Whitney Portal",
    )
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 overrides=overrides)
    assert len(rows) == 2
    assert any("Whitney" in r.permit_type and not r.peak_note for r in rows)
    assert any(r.peak_note and "Mount Russell" in r.peak_note for r in rows)
    report = format_permit_report(rows)
    assert "Mount Russell" in report


def test_override_skipped_when_peak_absent_or_matches_default():
    # A cluster with only Mount Whitney (no override target) gets one entry.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    overrides = load_permit_overrides(OVERRIDES)
    c = Cluster(cluster_id=0, peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505)],
                trailhead="Whitney Portal")
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 overrides=overrides)
    assert len(rows) == 1


def test_load_permit_overrides_missing_file_returns_empty():
    assert load_permit_overrides("data/does_not_exist.csv") == {}
