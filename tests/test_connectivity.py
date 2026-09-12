"""Tests for crowd-reported mobile coverage.

The whole risk in this dataset is overclaiming: it is the only table here
sourced from visitors rather than an agency, its rating has no stated scale,
and it describes a whole wilderness rather than a point. These tests exist to
keep all three admissions attached to the number.

Run with:  python -m pytest tests/test_connectivity.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.connectivity import (
    Coverage,
    coverage_by_group,
    coverage_for,
    load_connectivity,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "connectivity.csv")


def _cov(carrier, rating=None, sample_size=None, area_id="desolation", **kw):
    return Coverage(area_type="permit_group", area_id=area_id, carrier=carrier,
                    rating=rating, sample_size=sample_size, **kw)


# -- loading ----------------------------------------------------------------

def test_missing_file_is_not_an_error(tmp_path):
    assert load_connectivity(tmp_path / "nope.csv") == []


def test_blank_rating_loads_as_unread_not_as_zero():
    # A carrier with reports and no rating means "we haven't read it". Reading
    # it as 0.0 would assert the worst possible coverage on no evidence.
    rows = load_connectivity(DATA)
    att = next(c for c in rows if c.carrier == "AT&T")
    assert att.rating is None and att.unread
    assert att.sample_size == 209


# -- what we're willing to say ----------------------------------------------

def test_an_unstated_scale_is_admitted_in_the_rendered_string():
    assert "scale unstated" in _cov("Verizon", rating=0.8, rating_label="Major Issues").display


def test_a_known_scale_drops_the_admission():
    got = _cov("Verizon", rating=0.8, rating_label="Major Issues", rating_scale_known=True)
    assert "scale unstated" not in got.display


def test_an_unread_carrier_says_so_rather_than_showing_a_number():
    text = _cov("AT&T", sample_size=209).display
    assert "not read" in text and "209" in text


# -- ordering ---------------------------------------------------------------

def test_worst_coverage_sorts_first():
    # The decision this informs is whether to carry a satellite communicator,
    # and that's driven by the carrier you have, not the best one on the list.
    rows = [_cov("Good", rating=3.2), _cov("Bad", rating=0.8), _cov("Mid", rating=2.0)]
    assert [c.carrier for c in coverage_for(rows, "desolation")] == ["Bad", "Mid", "Good"]


def test_unread_carriers_sort_last_since_they_support_no_conclusion():
    rows = [_cov("Unknown"), _cov("Known", rating=2.0)]
    assert [c.carrier for c in coverage_for(rows, "desolation")] == ["Known", "Unknown"]


def test_another_permit_group_gets_nothing():
    rows = [_cov("Verizon", rating=0.8)]
    assert coverage_for(rows, "whitney_zone") == []
    assert coverage_for(rows, "") == []


def test_coverage_by_group():
    rows = [_cov("a", area_id="desolation"), _cov("b", area_id="seki")]
    assert set(coverage_by_group(rows)) == {"desolation", "seki"}


# -- the real dataset -------------------------------------------------------

def test_desolation_carries_the_verizon_reading_from_the_permit_page():
    rows = coverage_for(load_connectivity(DATA), "desolation")
    verizon = next(c for c in rows if c.carrier == "Verizon")
    assert (verizon.rating, verizon.rating_label, verizon.sample_size) == (0.8, "Major Issues", 272)
    assert not verizon.rating_scale_known, "no source has stated what the rating is out of"
    assert "recreation.gov" in verizon.source_url


def test_every_row_carries_a_source_and_a_verification_date():
    for c in load_connectivity(DATA):
        assert c.source_url, f"{c.carrier} has no source"
        assert c.verified_date, f"{c.carrier} has no verified_date"


def test_an_unread_carrier_becomes_an_open_question():
    from wayproof.reports import open_questions
    keys = [q.target_key for q in open_questions(connectivity=load_connectivity(DATA))
            if q.target_file == "data/connectivity.csv"]
    assert keys == ["desolation (AT&T)"]


# -- how it reads on the page -----------------------------------------------

def test_both_surfaces_say_it_is_crowd_reported_and_area_wide():
    from wayproof.model import Trailhead
    from wayproof.permits import PermitRule
    from wayproof.render import render_trailhead_html, render_trailhead_markdown
    from wayproof.views import trailhead_view

    th = Trailhead(name="Lyons Creek", latitude=38.8, longitude=-120.1, side="west",
                   permit_group="desolation")
    rule = PermitRule(permit_group="desolation", agency="Eldorado NF / LTBMU",
                      permit_type="Desolation Wilderness Permit", quota_required=True)
    view = trailhead_view(th, rule, connectivity=load_connectivity(DATA))

    for text in (render_trailhead_html(view), render_trailhead_markdown(view)):
        lower = text.lower()
        assert "major issues" in lower
        assert "recreation.gov" in lower
        assert "not stated by the managing agency" in lower
        assert "permit area rather than this trailhead" in lower


def test_a_trailhead_with_no_coverage_data_renders_no_section():
    from wayproof.model import Trailhead
    from wayproof.permits import PermitRule
    from wayproof.render import render_trailhead_markdown
    from wayproof.views import trailhead_view

    th = Trailhead(name="Somewhere", latitude=37.0, longitude=-118.0, side="east",
                   permit_group="whitney_zone")
    rule = PermitRule(permit_group="whitney_zone", agency="Inyo NF",
                      permit_type="x", quota_required=True)
    view = trailhead_view(th, rule, connectivity=load_connectivity(DATA))
    assert view["connectivity"]["carriers"] == []
    assert "Mobile coverage" not in render_trailhead_markdown(view)
