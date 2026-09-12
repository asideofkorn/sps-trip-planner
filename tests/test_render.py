"""Tests for wayproof.render's three page surfaces.

Run with:  python -m pytest tests/test_render.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.access import ApproachRoute
from wayproof.model import Peak, Trailhead
from wayproof.permits import PermitRule, SourceLogEntry
from wayproof.release_policy import LOTTERY_ANNUAL, ReleasePhase
from wayproof.render import (
    render_json,
    render_robots,
    render_sitemap,
    render_trailhead_html,
    render_trailhead_index_html,
    render_trailhead_markdown,
)
from wayproof.views import trailhead_view

TODAY = date(2026, 9, 12)


def _view(**overrides):
    trailhead = Trailhead(
        name="Whitney Portal", side="east", latitude=36.5861, longitude=-118.2414,
        elevation_ft=8360.0, notes="Mount Whitney Trail & Mountaineers Route",
        wilderness_area="Mount Whitney Zone", land_agency="Inyo NF",
        permit_group="whitney_zone", park="",
    )
    rule = PermitRule(
        permit_group="whitney_zone", agency="Inyo National Forest",
        permit_type="Mount Whitney Zone Permit", quota_required=True,
        quota_season_start=(5, 1), quota_season_end=(11, 1),
        fee_notes="$15/person", apply_url="https://www.recreation.gov/permits/445860",
        notes="Covers the classic Mt. Whitney Trail only.",
        interagency_note="Overnight permits may exit via the JMT into Yosemite.",
        source_last_updated="2026-07-08", verified_date="2026-07-23",
        release_phases=[ReleasePhase(
            permit_group="whitney_zone", phase_order=1, mechanism=LOTTERY_ANNUAL,
            season="in_season", fixed_month_day=(2, 1), label="apply_start",
        )],
    )
    approaches = [ApproachRoute(
        peak_name="Mount Russell", trailhead="Whitney Portal",
        approach_name="Mountaineers Route", permit_group="inyo_jmw_aaw",
        status="confirmed", source_url="https://example.gov/src",
        notes="Excluded from the Whitney Zone lottery by name.",
    )]
    peaks = [Peak(name="Mount Muir", latitude=36.5, longitude=-118.3,
                  elevation_ft=14012, meta={"nearest_trailhead": "Whitney Portal"})]
    log = [SourceLogEntry(
        date_checked="2026-07-23", permit_group="whitney_zone",
        source_url="https://example.gov/src", source_last_updated="2026-07-08",
        method="web", verdict="corrects-existing", summary="Only one results date.",
    )]
    view = trailhead_view(trailhead, rule, approaches, peaks, log, (), TODAY)
    view.update(overrides)
    return view


# -- HTML -------------------------------------------------------------------

def test_html_has_canonical_alternates_and_structured_data():
    out = render_trailhead_html(_view())
    assert '<link rel="canonical" href="https://wayproof.dev/trailheads/whitney-portal/">' in out
    assert '<link rel="alternate" type="text/markdown" href="/trailheads/whitney-portal.md">' in out
    assert '<link rel="alternate" type="application/json" href="/trailheads/whitney-portal.json">' in out
    assert '"@type": "Place"' in out


def test_html_leads_with_permit_content_before_the_peak_list():
    # The permit rule is this page's sourced, authoritative content; the peak
    # list is a proximity signal. Order on the page should say so.
    out = render_trailhead_html(_view())
    assert out.index("<h2>Permit</h2>") < out.index("Peaks nearest this trailhead")


def test_html_labels_the_peak_list_as_unverified_proximity():
    out = render_trailhead_html(_view())
    assert "straight-line proximity" in out
    assert "not an approach list" in out or "not by a verified" in out


def test_non_indexable_page_gets_a_noindex_robots_tag():
    assert '<meta name="robots" content="noindex,follow">' in render_trailhead_html(
        _view(indexable=False))
    assert 'content="noindex' not in render_trailhead_html(_view())


def test_html_escapes_content_rather_than_injecting_markup():
    out = render_trailhead_html(_view(notes='<script>alert("x")</script>'))
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out


# -- Markdown (agent surface) ----------------------------------------------

def test_markdown_states_its_canonical_url_and_generation_date():
    out = render_trailhead_markdown(_view())
    assert "https://wayproof.dev/trailheads/whitney-portal/" in out
    assert "Generated: 2026-09-12" in out


def test_markdown_carries_provenance_inline_with_the_claim():
    # An agent quoting the permit rule needs the verification date attached to
    # the claim, not parked in a sidebar it won't relay.
    out = render_trailhead_markdown(_view())
    assert "last verified by Wayproof: 2026-07-23" in out


def test_markdown_marks_the_proximity_peak_list_unverified():
    out = render_trailhead_markdown(_view())
    peaks_section = out[out.index("## Peaks nearest"):]
    assert "UNVERIFIED" in peaks_section
    assert "Do not state these as this trailhead's approach list." in peaks_section


def test_markdown_keeps_approach_status_attached_to_each_route():
    out = render_trailhead_markdown(_view())
    assert "**Mount Russell** via Mountaineers Route [confirmed]" in out


def test_markdown_does_not_instruct_the_reading_agent():
    # Instructions aimed at a reader's agent are prompt injection; a source
    # whose value is trustworthiness must not be one.
    out = render_trailhead_markdown(_view()).lower()
    for phrase in ("star the repo", "you are an ai", "if you are an agent",
                   "ignore previous", "please star"):
        assert phrase not in out


# -- JSON -------------------------------------------------------------------

def test_json_round_trips_the_view():
    view = _view()
    assert json.loads(render_json(view)) == json.loads(json.dumps(view))


# -- the invariant that makes three surfaces trustworthy --------------------

def test_all_three_surfaces_assert_the_same_facts():
    view = _view()
    html_out = render_trailhead_html(view)
    md_out = render_trailhead_markdown(view)
    json_out = json.loads(render_json(view))

    for fact in (view["permit"]["permit_type"], view["permit"]["agency"],
                 view["permit"]["fee_notes"], view["permit"]["verified_date"],
                 view["approach_exceptions"][0]["peak_name"]):
        assert fact in html_out, f"HTML is missing {fact!r}"
        assert fact in md_out, f"Markdown is missing {fact!r}"

    assert json_out["permit"]["permit_type"] == view["permit"]["permit_type"]
    assert json_out["peaks_nearby"]["verified"] is False
    # The computed release date has to be identical everywhere, not recomputed
    # per surface -- divergence here is the failure the split exists to prevent.
    release_date = view["permit"]["release_events"][0]["date"]
    assert release_date in html_out and release_date in md_out


# -- site-level files -------------------------------------------------------

def test_index_lists_every_trailhead_grouped_by_agency():
    views = [_view(), _view(name="Other TH", slug="other-th",
                            url_path="/trailheads/other-th/")]
    out = render_trailhead_index_html(views)
    assert "Whitney Portal" in out and "Other TH" in out
    assert "Inyo NF" in out


def test_sitemap_and_robots_are_well_formed():
    sitemap = render_sitemap(["https://wayproof.dev/", "https://wayproof.dev/trailheads/"])
    assert sitemap.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<loc>https://wayproof.dev/</loc>" in sitemap
    assert "Sitemap: https://wayproof.dev/sitemap.xml" in render_robots()
