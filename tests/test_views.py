"""Tests for wayproof.views' page view models.

Run with:  python -m pytest tests/test_views.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.access import ApproachRoute
from wayproof.model import Peak, Trailhead
from wayproof.permits import PermitRule, SourceLogEntry
from wayproof.release_policy import (
    CONTACT_REQUIRED,
    LOTTERY_ANNUAL,
    RESERVATION,
    WALKUP,
    ReleasePhase,
)
from wayproof.reports import OpenQuestion
from wayproof.views import next_occurrence, slugify, trailhead_view, trailhead_views

TODAY = date(2026, 9, 12)


def _trailhead(name="Whitney Portal", **kwargs):
    defaults = dict(
        name=name, side="east", latitude=36.5861, longitude=-118.2414,
        elevation_ft=8360.0, notes="Mount Whitney Trail",
        wilderness_area="John Muir Wilderness", land_agency="Inyo NF",
        permit_group="inyo_jmw_aaw", park="",
    )
    defaults.update(kwargs)
    return Trailhead(**defaults)


def _rule(**kwargs):
    defaults = dict(
        permit_group="inyo_jmw_aaw", agency="Inyo National Forest",
        permit_type="Inyo NF Wilderness Permit", quota_required=True,
        quota_season_start=(5, 1), quota_season_end=(11, 1),
        fee_notes="$6/permit", apply_url="https://example.gov/permit",
        source_last_updated="2026-07-08", verified_date="2026-07-23",
    )
    defaults.update(kwargs)
    return PermitRule(**defaults)


# -- slugs ------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Whitney Portal", "whitney-portal"),
    ("South Lake (Bishop Pass)", "south-lake-bishop-pass"),
    ("Twin Lakes (Bridgeport)", "twin-lakes-bridgeport"),
    ("Mineral King", "mineral-king"),
])
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_slug_collision_is_an_error_not_a_silent_overwrite():
    # Two names that slugify identically would publish to the same URL, so
    # the second would silently clobber the first.
    trailheads = [_trailhead("Mineral King"), _trailhead("mineral king!")]
    with pytest.raises(ValueError, match="Slug collision"):
        trailhead_views(trailheads, {"inyo_jmw_aaw": _rule()}, today=TODAY)


# -- date computation -------------------------------------------------------

def test_next_occurrence_rolls_to_next_year_once_the_date_has_passed():
    assert next_occurrence((2, 1), date(2026, 9, 12)) == date(2027, 2, 1)
    assert next_occurrence((12, 25), date(2026, 9, 12)) == date(2026, 12, 25)


def test_next_occurrence_includes_today():
    assert next_occurrence((9, 12), date(2026, 9, 12)) == date(2026, 9, 12)


def test_fixed_date_phase_gets_an_absolute_next_date():
    rule = _rule(release_phases=[ReleasePhase(
        permit_group="whitney_zone", phase_order=1, mechanism=LOTTERY_ANNUAL,
        season="in_season", fixed_month_day=(2, 1), label="apply_start",
    )])
    view = trailhead_view(_trailhead(), rule, today=TODAY)
    event = view["permit"]["release_events"][0]
    assert event["date"] == "2027-02-01"
    assert "2027-02-01" in event["description"]


def test_rolling_offset_phase_reports_the_entry_date_opening_today():
    # A 182-day offset has no absolute date of its own -- the useful inverse
    # is which entry date today's booking window covers.
    rule = _rule(release_phases=[ReleasePhase(
        permit_group="inyo_jmw_aaw", phase_order=1, mechanism=RESERVATION,
        offset_days=182, allocation_pct=60.0, label="first_release",
    )])
    view = trailhead_view(_trailhead(), rule, today=TODAY)
    event = view["permit"]["release_events"][0]
    assert event["date"] is None
    assert event["entry_date_opening_today"] == "2027-03-13"
    assert "60%" in event["description"]


def test_phase_without_offset_or_fixed_date_invents_nothing():
    rule = _rule(release_phases=[ReleasePhase(
        permit_group="sierra_nf", phase_order=2, mechanism=RESERVATION,
        allocation_pct=40.0, label="second_release",
        notes="Released for shorter-notice booking; no exact day published.",
    )])
    event = trailhead_view(_trailhead(), rule, today=TODAY)["permit"]["release_events"][0]
    assert event["date"] is None
    assert event["entry_date_opening_today"] is None
    assert "no release date published" in event["description"].lower()


def test_season_scope_is_stated_in_the_description():
    # An off-season phase listed next to in-season ones is misleading without
    # its scope attached -- Whitney's off-season window is not a lottery fallback.
    rule = _rule(release_phases=[ReleasePhase(
        permit_group="whitney_zone", phase_order=6, mechanism=RESERVATION,
        season="off_season", offset_days=14, label="off_season_release",
    )])
    event = trailhead_view(_trailhead(), rule, today=TODAY)["permit"]["release_events"][0]
    assert event["description"].startswith("Off season only")


@pytest.mark.parametrize("mechanism,expected", [
    (WALKUP, "in person"),
    (CONTACT_REQUIRED, "contact the agency"),
])
def test_non_reservable_mechanisms_describe_themselves(mechanism, expected):
    rule = _rule(release_phases=[ReleasePhase(
        permit_group="cpma", phase_order=1, mechanism=mechanism, label="x",
    )])
    event = trailhead_view(_trailhead(), rule, today=TODAY)["permit"]["release_events"][0]
    assert expected in event["description"]


def test_group_without_structured_phases_is_flagged_not_faked():
    view = trailhead_view(_trailhead(), _rule(release_phases=[]), today=TODAY)
    assert view["permit"]["has_computable_release"] is False
    assert view["permit"]["release_events"] == []


# -- what the page includes -------------------------------------------------

def test_permit_content_is_resolved_onto_the_trailhead():
    view = trailhead_view(_trailhead(), _rule(), today=TODAY)
    assert view["permit"]["known"] is True
    assert view["permit"]["agency"] == "Inyo National Forest"
    assert view["permit"]["quota_season"] == "May 1 - Nov 1"
    assert view["permit"]["verified_date"] == "2026-07-23"


def test_trailhead_with_no_matching_permit_rule_says_so():
    view = trailhead_view(_trailhead(), None, today=TODAY)
    assert view["permit"] == {"known": False}
    assert view["indexable"] is False


def test_approach_exceptions_are_filtered_to_this_trailhead():
    approaches = [
        ApproachRoute(peak_name="Mount Russell", trailhead="Whitney Portal",
                      approach_name="Mountaineers Route", permit_group="inyo_jmw_aaw",
                      status="confirmed"),
        ApproachRoute(peak_name="Elsewhere Peak", trailhead="Other Trailhead",
                      approach_name="Some Route", permit_group="", status="unconfirmed"),
    ]
    view = trailhead_view(_trailhead(), _rule(), approaches=approaches, today=TODAY)
    assert [a["peak_name"] for a in view["approach_exceptions"]] == ["Mount Russell"]


def test_nearby_peaks_are_labelled_as_unverified_proximity():
    # These come from a geometric assignment, not a curated approach list;
    # publishing them as fact would be exactly the inference the project's
    # own vocabulary forbids.
    peaks = [
        Peak(name="Mount Muir", latitude=36.5, longitude=-118.3, elevation_ft=14000,
             meta={"nearest_trailhead": "Whitney Portal"}),
        Peak(name="Far Peak", latitude=38.0, longitude=-119.0, elevation_ft=12000,
             meta={"nearest_trailhead": "Somewhere Else"}),
    ]
    nearby = trailhead_view(_trailhead(), _rule(), peaks=peaks, today=TODAY)["peaks_nearby"]
    assert nearby["names"] == ["Mount Muir"]
    assert nearby["verified"] is False
    assert nearby["basis"] == "computed-proximity"


def test_source_log_is_filtered_to_this_trailheads_permit_group():
    log = [
        SourceLogEntry(date_checked="2026-07-23", permit_group="inyo_jmw_aaw",
                       source_url="https://example.gov", source_last_updated="",
                       method="web", verdict="confirms-existing", summary="ok"),
        SourceLogEntry(date_checked="2026-07-23", permit_group="whitney_zone",
                       source_url="https://example.gov", source_last_updated="",
                       method="web", verdict="new-group", summary="other group"),
    ]
    view = trailhead_view(_trailhead(), _rule(), source_log=log, today=TODAY)
    assert len(view["source_log"]) == 1
    assert view["source_log"][0]["verdict"] == "confirms-existing"


def test_open_questions_are_scoped_by_trailhead_and_park():
    questions = [
        OpenQuestion(target_file="data/water_sources.csv", target_key="Spring",
                     question="No coordinates yet.", context="Whitney Portal"),
        OpenQuestion(target_file="data/campgrounds.csv", target_key="Other",
                     question="Unrelated.", context="Some Other Park"),
    ]
    view = trailhead_view(_trailhead(), _rule(), questions=questions, today=TODAY)
    assert len(view["open_questions"]) == 1
    assert view["open_questions"][0]["target_key"] == "Spring"


def test_views_are_sorted_and_carry_stable_urls():
    trailheads = [_trailhead("Zebra Pass"), _trailhead("Alpha Meadow")]
    views = trailhead_views(trailheads, {"inyo_jmw_aaw": _rule()}, today=TODAY)
    assert [v["name"] for v in views] == ["Alpha Meadow", "Zebra Pass"]
    assert views[0]["url_path"] == "/trailheads/alpha-meadow/"
    assert views[0]["canonical_url"] == "https://wayproof.dev/trailheads/alpha-meadow/"
