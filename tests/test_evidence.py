"""Tests for linking a claim to the verification events behind it.

Two directions of one edge. Forward, a reader asks "where does this come from,
and is anyone arguing about it". Backward, ingestion asks "this page changed,
what do I re-check". Both were unanswerable while the log was a diary with no
index.

Run with:  python -m pytest tests/test_evidence.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.evidence import (
    CONTESTED,
    SETTLED,
    UNVERIFIED,
    claims_citing_url,
    dangling_citations,
    entries_for_url,
    evidence_for,
    index_log,
    parse_ids,
)
from wayproof.permits import SourceLogEntry, load_source_log
from wayproof.provenance import load_sources
from wayproof.regulations import load_regulations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "permit_source_log.csv")
REGS = os.path.join(ROOT, "data", "regulations.csv")
REC = "https://www.recreation.gov/permits/233261"


def _entry(entry_id, url="https://x.example", verdict="confirms-existing",
           conflict_id="", group="g", date="2026-01-01", kind=""):
    return SourceLogEntry(date_checked=date, permit_group=group, source_url=url,
                          source_last_updated="", method="test", verdict=verdict,
                          summary="s", conflict_id=conflict_id, conflict_kind=kind,
                          entry_id=entry_id)


# -- parsing and the three states -------------------------------------------

def test_parse_ids_handles_the_raw_cell():
    assert parse_ids("a; b ;c") == ("a", "b", "c")
    assert parse_ids("") == () and parse_ids(None) == ()


def test_no_citation_is_unverified_not_settled():
    # The distinction the whole thing turns on: "nobody checked" must never
    # render like "checked and fine".
    assert evidence_for("", [_entry("x")]).status == UNVERIFIED


def test_a_citation_with_no_open_conflict_is_settled():
    log = [_entry("a")]
    got = evidence_for("a", log)
    assert got.status == SETTLED and got.last_checked == "2026-01-01"


def test_a_citation_touching_an_open_conflict_is_contested():
    log = [_entry("a", conflict_id="c1", verdict="unresolved-conflict")]
    got = evidence_for("a", log)
    assert got.status == CONTESTED
    assert [e.conflict_id for e in got.open_conflicts] == ["c1"]


def test_a_conflict_that_was_closed_is_settled_but_still_visible():
    # "We considered this and resolved it" reassures a sceptical reader more
    # than silence, and tells the next maintainer not to relitigate it.
    log = [_entry("a", conflict_id="c1", verdict="unresolved-conflict"),
           _entry("b", conflict_id="c1", verdict="corrects-existing", date="2026-02-01")]
    got = evidence_for("a; b", log)
    assert got.status == SETTLED
    assert [e.conflict_id for e in got.closed_conflicts] == ["c1", "c1"]


def test_a_dangling_citation_does_not_pass_as_evidence():
    got = evidence_for("nope", [_entry("a")])
    assert got.status == UNVERIFIED
    assert got.missing_ids == ("nope",)


def test_a_partly_dangling_citation_keeps_what_resolves_and_reports_the_rest():
    got = evidence_for("a; nope", [_entry("a")])
    assert got.status == SETTLED and got.missing_ids == ("nope",)


def test_sources_are_deduplicated_in_first_cited_order():
    log = [_entry("a", url="https://one"), _entry("b", url="https://two"),
           _entry("c", url="https://one")]
    assert evidence_for("a; b; c", log).source_urls == ["https://one", "https://two"]


def test_the_publisher_is_resolved_when_a_registry_is_given():
    sources = load_sources(os.path.join(ROOT, "data", "sources.csv"))
    got = evidence_for("a", [_entry("a", url=REC)], sources)
    assert got.entries[0].publisher == "Recreation.gov"
    assert "Recreation.gov" in got.entries[0].headline


# -- the backward edge, which is what makes ingestion actionable ------------

def test_a_changed_url_names_the_claims_that_depend_on_it():
    log = [_entry("a", url=REC), _entry("b", url="https://other")]
    claims = [("rule-1", "a"), ("rule-2", "b"), ("rule-3", "a; b")]
    assert claims_citing_url(REC, log, claims) == ["rule-1", "rule-3"]


def test_an_unwatched_url_names_nothing_rather_than_everything():
    log = [_entry("a", url=REC)]
    assert claims_citing_url("https://never-seen", log, [("rule-1", "a")]) == []


def test_entries_for_url_returns_the_whole_history_of_one_page():
    log = [_entry("a", url=REC), _entry("b", url="https://other"),
           _entry("c", url=REC, date="2026-03-01")]
    assert [e.entry_id for e in entries_for_url(REC, log)] == ["a", "c"]


def test_dangling_citations_are_found_across_every_claim_table():
    log = [_entry("a")]
    claims = [("permits.csv:x", "a; ghost"), ("regulations.csv:y", "a")]
    assert dangling_citations(log, claims) == [("permits.csv:x", "ghost")]


# -- the real dataset -------------------------------------------------------

def test_every_log_entry_has_a_unique_stable_id():
    log = load_source_log(LOG)
    ids = [e.entry_id for e in log]
    assert all(ids), "an entry with no id cannot be cited"
    assert len(ids) == len(set(ids))


def test_entry_ids_are_sayable_and_sortable():
    for e in load_source_log(LOG):
        assert e.entry_id.startswith(e.permit_group + "-" + e.date_checked + "-")
        assert e.entry_id.replace("-", "").replace("_", "").isalnum()


def test_no_citation_in_the_real_data_dangles():
    log = load_source_log(LOG)
    regs = load_regulations(REGS)
    bad = dangling_citations(log, [(r.regulation_id, r.log_entry_ids) for r in regs])
    assert bad == [], f"citations resolving to nothing: {bad}"


def test_exactly_the_disputed_rule_reads_as_contested():
    # A badge that marks settled rules as contested is worse than no badge.
    # Only the 25-vs-30 ft camping setback is genuinely in dispute.
    log, sources = load_source_log(LOG), load_sources(os.path.join(ROOT, "data", "sources.csv"))
    contested = sorted(r.regulation_id for r in load_regulations(REGS)
                       if evidence_for(r.log_entry_ids, log, sources).status == CONTESTED)
    assert contested == ["desolation-camp-setback"]


def test_a_conflict_entry_is_only_cited_by_the_rule_it_concerns():
    log = load_source_log(LOG)
    by_id = index_log(log)
    for r in load_regulations(REGS):
        for cited in parse_ids(r.log_entry_ids):
            entry = by_id[cited]
            if entry.conflict_id == "desolation-sma-distance":
                assert r.regulation_id == "desolation-camp-setback"


def test_changing_the_desolation_permit_page_names_the_rules_to_recheck():
    log = load_source_log(LOG)
    claims = [(r.regulation_id, r.log_entry_ids) for r in load_regulations(REGS)]
    affected = claims_citing_url(REC, log, claims)
    assert len(affected) >= 10
    assert all(a.startswith("desolation-") for a in affected), (
        "a change to Desolation's permit page should not implicate Mokelumne's rules"
    )


def test_both_surfaces_state_the_evidence_and_agree():
    from wayproof.model import Trailhead
    from wayproof.permits import PermitRule
    from wayproof.render import render_trailhead_html, render_trailhead_markdown
    from wayproof.views import trailhead_view

    th = Trailhead(name="Lyons Creek", latitude=38.8, longitude=-120.1,
                   permit_group="desolation")
    rule = PermitRule(permit_group="desolation", agency="Eldorado NF / LTBMU",
                      permit_type="Desolation Wilderness Permit", quota_required=True,
                      jurisdiction="CA", wilderness_area="Desolation Wilderness")
    view = trailhead_view(th, rule, source_log=load_source_log(LOG),
                          sources=load_sources(os.path.join(ROOT, "data", "sources.csv")),
                          regulations=load_regulations(REGS))
    html = render_trailhead_html(view)
    md = render_trailhead_markdown(view)
    for text in (html, md):
        assert "desolation-2026-09-12" in text, "entry ids must be followable on the page"
    assert "sources disagree" in md.lower()   # the status label
    assert "open conflict" in md.lower()      # which one, named once
    assert "desolation-sma-distance" in md
