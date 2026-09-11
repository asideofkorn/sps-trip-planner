"""Tests for the permit-lookup module.

Run with:  python -m pytest tests/test_permits.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.access import ApproachRoute, load_approaches
from wayproof.data_loader import load_trailheads
from wayproof.model import Cluster, Peak
from wayproof.permits import (
    load_permits,
    load_source_log,
    unresolved_conflicts,
    format_source_log,
    permit_status,
    clusters_permit_info,
    format_permit_report,
)

TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")
PERMITS = os.path.join(os.path.dirname(__file__), "..", "data", "permits.csv")
APPROACHES = os.path.join(os.path.dirname(__file__), "..", "data", "approaches.csv")
SOURCE_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "permit_source_log.csv")
RELEASE_POLICIES = os.path.join(os.path.dirname(__file__), "..", "data", "release_policies.csv")


def _permits():
    return load_permits(PERMITS, RELEASE_POLICIES)


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


def test_mount_russell_approach_surfaces_second_permit():
    # Whitney Portal defaults to the Whitney Zone lottery, but Mount Russell
    # (Mountaineers Route / North Fork of Lone Pine Creek) needs the regular
    # Inyo NF permit instead -- both should show up for a mixed trip.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    approaches = load_approaches(APPROACHES)
    russell = next(a for a in approaches if a.peak_name == "Mount Russell")
    assert russell.confirmed
    assert russell.permit_group == "inyo_jmw_aaw"

    c = Cluster(
        cluster_id=0,
        peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505),
               Peak("Mount Russell", 36.595, -118.303, 14094)],
        trailhead="Whitney Portal",
    )
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 approaches=approaches)
    assert len(rows) == 2
    assert any("Whitney" in r.permit_type and not r.peak_note for r in rows)
    russell_row = next(r for r in rows if r.peak_note and "Mount Russell" in r.peak_note)
    assert russell_row.approach_status == "confirmed"
    assert "North Fork" in russell_row.approach_name
    report = format_permit_report(rows)
    assert "Mount Russell" in report
    assert "North Fork" in report


def test_unconfirmed_approach_flags_caution_without_asserting_new_permit():
    # Mount Irvine's source-listed trailhead names a different trail (Meysan
    # Lake Trail) than Whitney Portal's main trail, but no source confirms
    # which permit actually governs it -- this should surface as a caution,
    # not a silently-assumed default or an invented permit.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    approaches = load_approaches(APPROACHES)
    irvine = next(a for a in approaches if a.peak_name == "Mount Irvine")
    assert not irvine.confirmed
    assert irvine.permit_group == ""

    c = Cluster(
        cluster_id=0,
        peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505),
               Peak("Mount Irvine", 36.556, -118.264, 13780)],
        trailhead="Whitney Portal",
    )
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 approaches=approaches)
    assert len(rows) == 2
    default_row = next(r for r in rows if not r.peak_note)
    caution_row = next(r for r in rows if r.peak_note)
    # The caution reuses the trailhead's default permit type -- it flags
    # uncertainty rather than asserting a different (unverified) permit.
    assert caution_row.permit_type == default_row.permit_type
    assert caution_row.approach_status == "unconfirmed"
    assert "UNCERTAIN" in caution_row.peak_note
    assert "Mount Irvine" in caution_row.peak_note
    report = format_permit_report(rows)
    assert "UNCERTAIN" in report


def test_approach_skipped_when_peak_absent_or_matches_default():
    # A cluster with only Mount Whitney (no approach-specific peak) gets one entry.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    approaches = load_approaches(APPROACHES)
    c = Cluster(cluster_id=0, peaks=[Peak("Mount Whitney", 36.578, -118.292, 14505)],
                trailhead="Whitney Portal")
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 approaches=approaches)
    assert len(rows) == 1


def test_approach_from_different_trailhead_is_skipped():
    # A known approach naming a different trailhead than the one the cluster
    # actually used shouldn't apply -- it describes access from elsewhere.
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)
    approaches = [ApproachRoute(
        peak_name="Mount Russell", trailhead="Some Other Trailhead",
        approach_name="A different route", permit_group="inyo_jmw_aaw",
        status="confirmed",
    )]
    c = Cluster(cluster_id=0, peaks=[Peak("Mount Russell", 36.595, -118.303, 14094)],
                trailhead="Whitney Portal")
    rows = clusters_permit_info([c], trailheads, permits, date(2027, 7, 1),
                                 approaches=approaches)
    assert len(rows) == 1
    assert not rows[0].peak_note


def test_load_approaches_missing_file_returns_empty():
    assert load_approaches("data/does_not_exist.csv") == []


def test_load_approaches_rejects_invalid_status():
    import pytest
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("peak_name,trailhead,approach_name,permit_group,status\n")
        f.write("Test Peak,Test Trailhead,Test Route,none,bogus\n")
        path = f.name
    try:
        with pytest.raises(ValueError):
            load_approaches(path)
    finally:
        os.unlink(path)


def test_provenance_fields_load_and_flag_dated_sources():
    permits = load_permits(PERMITS)
    # inyo_hoover_nonquota and inyo_gtw trace to a 2021 PDF -- should be
    # loadable and clearly distinguishable from a freshly-checked row.
    dated = permits["inyo_hoover_nonquota"]
    assert dated.source_last_updated == "2021-06-13"
    assert dated.verified_date == "2026-07-23"
    # Rows never independently verified (web-search only) have no verified_date.
    unverified = permits["toiyabe_free"]
    assert unverified.verified_date == ""


def test_report_shows_provenance_and_flags_unverified_rows():
    permits = load_permits(PERMITS)
    trailheads = load_trailheads(TRAILHEADS)

    verified = Cluster(cluster_id=0, peaks=[Peak("P", 36.45, -118.17, 12000)],
                        trailhead="Horseshoe Meadows (Cottonwood)")
    rows = clusters_permit_info([verified], trailheads, permits, date(2027, 7, 1))
    report = format_permit_report(rows)
    assert "source last updated 2021-06-13" in report
    assert "we last checked this against the source on 2026-07-23" in report

    unverified = Cluster(cluster_id=1, peaks=[Peak("Highland Peak", 38.55, -119.81, 10934)],
                          trailhead="Ebbetts Pass")
    rows = clusters_permit_info([unverified], trailheads, permits, date(2027, 7, 1))
    report = format_permit_report(rows)
    assert "not independently verified" in report.lower()


def test_load_source_log_missing_file_returns_empty():
    assert load_source_log("data/does_not_exist.csv") == []


def test_source_log_loads_every_permit_group():
    log = load_source_log(SOURCE_LOG)
    permits = load_permits(PERMITS)
    logged_groups = {e.permit_group for e in log}
    assert set(permits) <= logged_groups


def test_resolved_conflict_does_not_show_as_unresolved():
    # whitney_zone had a real ambiguous-screenshot entry that a later,
    # cleaner source resolved -- the log preserves both, but the group
    # should NOT show up as a live unresolved conflict.
    log = load_source_log(SOURCE_LOG)
    assert "whitney_zone" not in unresolved_conflicts(log)
    report = format_source_log(log, permit_group="whitney_zone")
    assert "CONFLICT" in report  # the historical entry is still visible
    assert "CORRECTS" in report  # ...followed by its resolution


def test_unresolved_conflict_is_detected():
    # A synthetic log where the LATEST entry for a group is a conflict
    # (never followed by a resolving entry) must be flagged.
    from wayproof.permits import SourceLogEntry
    log = [
        SourceLogEntry("2026-01-01", "test_group", "https://a.example", "", "websearch",
                        "new-group", "initial"),
        SourceLogEntry("2026-02-01", "test_group", "https://b.example", "", "user-screenshot",
                        "unresolved-conflict", "b disagrees with a, not yet reconciled"),
    ]
    assert unresolved_conflicts(log) == ["test_group"]
    assert "UNRESOLVED CONFLICTS: test_group" in format_source_log(log)


def test_format_source_log_empty():
    assert "no source log entries" in format_source_log([]).lower()
    assert "no source log entries for made_up_group" in format_source_log(
        [], permit_group="made_up_group").lower()


def test_yosemite_uses_lottery_language_not_simple_booking():
    # Yosemite's 60% portion is a weekly lottery, not a simple first-come
    # reservation window like Inyo/SEKI -- the status message must say so.
    permits = load_permits(PERMITS)
    rule = permits["yosemite"]
    trip = date(2027, 7, 15)
    opens = trip - __import__("datetime").timedelta(days=rule.reservation_window_days)

    before = permit_status(rule, trip, today=opens - __import__("datetime").timedelta(days=1))
    assert "lottery" in before.lower()
    assert "book now" not in before.lower()

    after = permit_status(rule, trip, today=opens)
    assert "lottery" in after.lower()
    assert "book now" not in after.lower()


def test_yosemite_provenance_reflects_nps_source():
    permits = load_permits(PERMITS)
    rule = permits["yosemite"]
    assert rule.source_last_updated == "2025-11-13"
    assert rule.verified_date  # now independently verified, not web-search-only


def test_ebbetts_pass_is_toiyabe_not_stanislaus():
    # Stanislaus NF's own permit page states outright that Ebbetts Pass is
    # Humboldt-Toiyabe NF jurisdiction -- this project had it wrong.
    trailheads = load_trailheads(TRAILHEADS)
    ebbetts = next(t for t in trailheads if t.name == "Ebbetts Pass")
    assert ebbetts.land_agency == "Humboldt-Toiyabe NF"
    assert ebbetts.permit_group == "toiyabe_free"

    permits = load_permits(PERMITS)
    assert "toiyabe_free" in permits
    assert not permits["toiyabe_free"].verified_date  # explicitly unconfirmed placeholder

    # Sonora Pass, on the same source page, is confirmed correct as-is.
    sonora = next(t for t in trailheads if t.name == "Sonora Pass")
    assert sonora.land_agency == "Stanislaus NF"


# --- Structured, computable release rules (data/release_policies.csv) -----

def test_release_phases_load_and_attach_to_rule():
    permits = _permits()
    rule = permits["inyo_jmw_aaw"]
    assert [p.offset_days for p in rule.release_phases] == [182, 14]
    assert [p.allocation_pct for p in rule.release_phases] == [60, 40]


def test_split_release_surfaces_both_phase_dates():
    # Previously only the 60% first-release date was ever computed; the 40%
    # second release existed only as prose in reservation_method. Both should
    # now be surfaced as real dates.
    permits = _permits()
    rule = permits["inyo_jmw_aaw"]
    trip = date(2027, 7, 15)
    status = permit_status(rule, trip, today=date(2027, 7, 2))
    assert "2027-01-14" in status  # 60% release, 182 days before
    assert "2027-07-01" in status  # 40% release, 14 days before
    assert "40%" in status


def test_hoover_split_release_dates():
    permits = _permits()
    rule = permits["hoover"]
    trip = date(2027, 7, 15)
    status = permit_status(rule, trip, today=date(2027, 1, 1))
    assert "2027-01-14" in status  # 50% release, 182 days before
    assert "2027-07-12" in status  # 50% release, 3 days before
    assert "50%" in status


def test_sierra_nf_second_phase_has_no_fabricated_date():
    # The source states a ~40% second allocation but not its exact release
    # offset -- the tool must not invent a specific date for it.
    permits = _permits()
    rule = permits["sierra_nf"]
    trip = date(2027, 7, 15)
    status = permit_status(rule, trip, today=date(2027, 7, 10))
    assert "exact release offset not stated" in status


def test_whitney_annual_lottery_still_works_via_structured_phases():
    permits = _permits()
    rule = permits["whitney_zone"]
    trip = date(2027, 8, 1)
    assert rule.release_phases  # migrated, not on the legacy fallback

    before_open = permit_status(rule, trip, today=date(2027, 1, 15))
    assert "opens" in before_open.lower()
    during_lottery = permit_status(rule, trip, today=date(2027, 2, 15))
    assert "open now" in during_lottery.lower()
    after_results = permit_status(rule, trip, today=date(2027, 4, 1))
    assert "claim" in after_results.lower()
    after_release = permit_status(rule, trip, today=date(2027, 5, 1))
    assert "first-come" in after_release.lower()


def test_whitney_off_season_uses_reservation_not_lottery_language():
    # A winter trip date is a genuinely different, simpler mechanism per the
    # source -- it must not trigger lottery wording at all.
    permits = _permits()
    rule = permits["whitney_zone"]
    trip = date(2027, 1, 20)  # outside May 1 - Nov 1
    assert not rule.in_quota_season(trip)
    status = permit_status(rule, trip, today=date(2027, 1, 1)).lower()
    assert "lottery" not in status
    assert "open" in status


def test_cpma_mechanisms_are_data_driven():
    permits = _permits()
    rule = permits["cpma"]
    mechanisms = {p.mechanism for p in rule.release_phases}
    assert mechanisms == {"walkup", "contact_required"}

    trip = date(2027, 7, 15)
    assert "first-come" in permit_status(rule, trip).lower()

    winter = date(2027, 12, 15)
    status = permit_status(rule, winter).lower()
    assert "should be free/self-issue" not in status
    assert "amador" in status


def test_yosemite_still_uses_legacy_special_case():
    # Yosemite's weekly lottery is deliberately left unmigrated -- see
    # wayproof/release_policy.py's module docstring for why.
    permits = _permits()
    rule = permits["yosemite"]
    assert rule.release_phases == []


def test_load_release_policies_missing_file_returns_empty():
    from wayproof.release_policy import load_release_policies
    assert load_release_policies("data/does_not_exist.csv") == {}


def test_load_release_policies_rejects_invalid_mechanism():
    import pytest
    import tempfile
    from wayproof.release_policy import load_release_policies

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("permit_group,phase_order,mechanism,season,offset_days\n")
        f.write("test_group,1,bogus,,10\n")
        path = f.name
    try:
        with pytest.raises(ValueError):
            load_release_policies(path)
    finally:
        os.unlink(path)


def test_load_release_policies_rejects_invalid_season():
    import pytest
    import tempfile
    from wayproof.release_policy import load_release_policies

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("permit_group,phase_order,mechanism,season,offset_days\n")
        f.write("test_group,1,reservation,bogus_season,10\n")
        path = f.name
    try:
        with pytest.raises(ValueError):
            load_release_policies(path)
    finally:
        os.unlink(path)
