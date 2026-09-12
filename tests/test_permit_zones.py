"""Tests for destination zones and the mixed-mechanism release rendering they exposed.

Run with:  python -m pytest tests/test_permit_zones.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.permit_zones import DESTINATION_ZONE, THRU_HIKE, PermitZone, load_permit_zones
from wayproof.permits import PermitRule, load_permits, permit_status
from wayproof.release_policy import (
    CONTACT_REQUIRED,
    OFF_SEASON,
    RESERVATION,
    WALKUP,
    ReleasePhase,
)
from wayproof.reports import open_questions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = date(2026, 9, 12)


def _zones_csv(tmp_path, rows):
    path = tmp_path / "permit_zones.csv"
    header = "permit_group,zone_code,zone_name,zone_type,source_url,verified_date,notes\n"
    path.write_text(header + "".join(rows))
    return path


# -- loader -----------------------------------------------------------------

def test_missing_file_is_not_an_error(tmp_path):
    # Zones are extra detail for the minority of groups quota'd by
    # destination, not required input for a permit lookup.
    assert load_permit_zones(tmp_path / "nope.csv") == {}


def test_zones_load_grouped_and_ordered_by_code(tmp_path):
    path = _zones_csv(tmp_path, [
        "desolation,3,Genevieve,destination_zone,https://example.gov,2026-09-12,\n",
        "desolation,1,Rockbound Lake,destination_zone,https://example.gov,2026-09-12,\n",
        "other,7,Somewhere,destination_zone,https://example.gov,2026-09-12,\n",
    ])
    zones = load_permit_zones(path)
    assert sorted(zones) == ["desolation", "other"]
    assert [z.zone_code for z in zones["desolation"]] == [1, 3]


def test_unnumbered_zones_sort_after_numbered_ones(tmp_path):
    # The Tahoe Rim Trail thru-hike option is selectable alongside the 45
    # numbered zones but isn't one of them, so it has no code and belongs last.
    path = _zones_csv(tmp_path, [
        "desolation,45,Ralston,destination_zone,https://example.gov,2026-09-12,\n",
        "desolation,,Tahoe Rim Trail (Thru Hike Only),thru_hike,https://example.gov,2026-09-12,\n",
        "desolation,1,Rockbound Lake,destination_zone,https://example.gov,2026-09-12,\n",
    ])
    zones = load_permit_zones(path)["desolation"]
    assert [z.zone_name for z in zones][-1] == "Tahoe Rim Trail (Thru Hike Only)"
    assert zones[-1].zone_code is None
    assert zones[-1].zone_type == THRU_HIKE


def test_label_matches_the_agencys_own_booking_ui():
    numbered = PermitZone(permit_group="desolation", zone_name="Aloha", zone_code=33)
    unnumbered = PermitZone(permit_group="desolation", zone_name="Tahoe Rim Trail (Thru Hike Only)",
                            zone_type=THRU_HIKE)
    assert numbered.label == "33 Aloha"
    assert unnumbered.label == "Tahoe Rim Trail (Thru Hike Only)"


def test_real_desolation_zone_data_is_complete_and_contiguous():
    zones = load_permit_zones(os.path.join(ROOT, "data", "permit_zones.csv"))["desolation"]
    numbered = [z for z in zones if z.zone_type == DESTINATION_ZONE]
    # Four independent sources agree on 45, and the official zone map shows
    # them numbered contiguously with no gaps.
    assert [z.zone_code for z in numbered] == list(range(1, 46))
    assert all(z.source_url for z in zones)


# -- the mixed-mechanism bug the Desolation data exposed --------------------

def _rule(phases, **kwargs):
    defaults = dict(
        permit_group="desolation", agency="Eldorado NF", permit_type="Test Permit",
        quota_required=True, quota_season_start=(5, 22), quota_season_end=(9, 30),
        release_phases=phases,
    )
    defaults.update(kwargs)
    return PermitRule(**defaults)


def test_walkup_share_alongside_reservations_does_not_hide_the_reservable_share():
    # Desolation splits ONE quota: ~2/3 reservable online, ~1/3 same-day only.
    # Before this fix, the presence of any walkup phase short-circuited the
    # whole group to "not reservable in advance" -- backwards for the 2/3.
    rule = _rule([
        ReleasePhase(permit_group="desolation", phase_order=1, mechanism=RESERVATION,
                     season="in_season", offset_days=182, allocation_pct=67, label="first_release"),
        ReleasePhase(permit_group="desolation", phase_order=2, mechanism=WALKUP,
                     season="in_season", allocation_pct=33, label="same_day_walkup"),
    ])
    status = permit_status(rule, date(2027, 7, 15), TODAY)
    assert "Reservations open" in status
    assert "not reservable in advance" not in status.lower()
    assert "33%" in status


def test_walkup_only_group_still_reports_as_not_reservable():
    rule = _rule([
        ReleasePhase(permit_group="cpma", phase_order=1, mechanism=WALKUP, label="walkup"),
    ], permit_group="cpma")
    assert "Not reservable in advance" in permit_status(rule, date(2027, 7, 15), TODAY)


def test_contact_required_only_group_is_unchanged():
    rule = _rule([
        ReleasePhase(permit_group="cpma", phase_order=1, mechanism=CONTACT_REQUIRED,
                     label="contact", notes="Call the district office."),
    ], permit_group="cpma")
    status = permit_status(rule, date(2027, 7, 15), TODAY)
    assert "contact the agency directly" in status


def test_off_season_phase_replaces_the_free_self_issue_assumption():
    # Desolation's off-season permits are still booked through recreation.gov.
    # Without an off_season phase, permit_status() asserts they're free and
    # self-issue -- an assumption already caught wrong twice against sources.
    phases = [
        ReleasePhase(permit_group="desolation", phase_order=1, mechanism=RESERVATION,
                     season="in_season", offset_days=182, label="first_release"),
        ReleasePhase(permit_group="desolation", phase_order=3, mechanism=RESERVATION,
                     season=OFF_SEASON, offset_days=0, label="off_season_release"),
    ]
    status = permit_status(_rule(phases), date(2027, 2, 10), TODAY)
    assert "self-issue" not in status.lower()
    assert "Reservations open" in status


def test_real_desolation_rule_answers_both_seasons_without_claiming_self_issue():
    rule = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                        os.path.join(ROOT, "data", "release_policies.csv"))["desolation"]
    in_season = permit_status(rule, date(2027, 7, 15), TODAY)
    off_season = permit_status(rule, date(2027, 2, 10), TODAY)
    assert "Reservations open" in in_season and "33%" in in_season
    assert "self-issue" not in off_season.lower()


# -- detecting the same latent gap in every other group ---------------------

def test_quota_group_without_an_off_season_phase_becomes_an_open_question():
    rule = _rule([
        ReleasePhase(permit_group="hoover", phase_order=1, mechanism=RESERVATION,
                     offset_days=182, label="first_release"),
    ], permit_group="hoover")
    questions = open_questions(permits=[rule])
    assert [q.target_key for q in questions] == ["hoover (off-season)"]
    assert questions[0].target_file == "data/release_policies.csv"


def test_group_with_an_off_season_phase_is_not_flagged():
    rule = _rule([
        ReleasePhase(permit_group="desolation", phase_order=1, mechanism=RESERVATION,
                     season="in_season", offset_days=182, label="first_release"),
        ReleasePhase(permit_group="desolation", phase_order=3, mechanism=RESERVATION,
                     season=OFF_SEASON, offset_days=0, label="off_season_release"),
    ])
    assert open_questions(permits=[rule]) == []


def test_unquota_d_and_unmigrated_groups_are_not_flagged():
    # A group with no quota has no off-season question to answer, and one with
    # no structured phases at all is a different, separately-tracked gap.
    free = _rule([], permit_group="gtw_free", quota_required=False)
    unmigrated = _rule([], permit_group="yosemite")
    assert open_questions(permits=[free, unmigrated]) == []


def test_off_season_gap_is_global_only_not_peak_scoped():
    # It's a dataset-wide data-quality gap, not something to surface as
    # "relevant to your trip" on a specific objective.
    rule = _rule([
        ReleasePhase(permit_group="hoover", phase_order=1, mechanism=RESERVATION,
                     offset_days=182, label="first_release"),
    ], permit_group="hoover")
    assert open_questions(permits=[rule], peak_names=["Mount Whitney"]) == []
