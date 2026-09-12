"""Tests for source authority, deferral, and conflict resolution.

The load-bearing tests are the ones at the bottom: the rule has to reproduce
every conflict resolution this project actually made and defended in prose. A
model that disagrees with the decisions it was derived from is wrong, and a
model that only agrees with invented examples proves nothing.

Run with:  python -m pytest tests/test_provenance.py
"""

from __future__ import annotations

import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.provenance import (
    ACCESS,
    BOOKING_MECHANICS,
    DEFERRAL,
    FEES,
    INTERNAL_FIRST,
    PERMIT_REQUIREMENT,
    RECENCY,
    REGULATION,
    ROLE,
    STALE_DAYS,
    UNRESOLVED,
    UNRESOLVED_STALE_AUTHORITY,
    Claim,
    age_days,
    deferral_for,
    load_deferrals,
    load_sources,
    resolve,
    source_for,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "data", "sources.csv")
DEFERRALS = os.path.join(ROOT, "data", "source_deferrals.csv")
TODAY = datetime.date(2026, 9, 12)

REC = "https://www.recreation.gov/permits/233261"
FAQ = "https://www.fs.usda.gov/r05/eldorado/about-area/faqs"
MOKE_PDF = "https://www.fs.usda.gov/sites/nfs/files/r05/eldorado/publication/x.pdf"


@pytest.fixture
def reg():
    return load_sources(SOURCES), load_deferrals(DEFERRALS)


# -- registry ---------------------------------------------------------------

def test_missing_files_are_not_errors(tmp_path):
    assert load_sources(tmp_path / "nope.csv") == []
    assert load_deferrals(tmp_path / "nope.csv") == []


def test_invalid_role_is_rejected_loudly(tmp_path):
    p = tmp_path / "sources.csv"
    p.write_text("source_id,publisher,url_prefix,role,regulates,notes\nx,X,https://x/,oracle,,\n")
    with pytest.raises(ValueError, match="Invalid role"):
        load_sources(p)


def test_unknown_topic_is_rejected_loudly(tmp_path):
    p = tmp_path / "sources.csv"
    p.write_text("source_id,publisher,url_prefix,role,regulates,notes\n"
                 "x,X,https://x/,regulator,vibes,\n")
    with pytest.raises(ValueError, match="Unknown topic"):
        load_sources(p)


def test_a_deferral_without_its_sentence_is_dropped(tmp_path):
    # Evidence is the whole point. Without the quoted wording this is an
    # opinion about who ought to win.
    p = tmp_path / "deferrals.csv"
    p.write_text("from_source,to_source,topic,observed_date,evidence_url,evidence\n"
                 "a,b,regulation,2026-01-01,https://x/,\n")
    assert load_deferrals(p) == []


def test_longest_url_prefix_wins(reg):
    sources, _ = reg
    assert source_for(REC, sources).source_id == "recreation_gov"
    assert source_for(FAQ, sources).source_id == "fs_usda"
    assert source_for("https://example.com/x", sources) is None


def test_a_secondary_source_owns_nothing(reg):
    sources, _ = reg
    desowv = next(s for s in sources if s.source_id == "desowv")
    assert not any(desowv.owns(t) for t in (REGULATION, FEES, PERMIT_REQUIREMENT))


def test_a_bare_year_is_not_a_usable_date():
    # A year is what a PDF stamps on itself; it cannot be compared with a page
    # that publishes a full last-updated date.
    assert age_days("2025", TODAY) is None
    assert age_days("", TODAY) is None
    assert age_days("2026-09-11", TODAY) == 1


# -- the historical decisions this rule has to reproduce --------------------

def test_desolation_day_use_resolves_on_self_contradiction_not_ranking(reg):
    # recreation.gov's overview says a permit is needed for day visits
    # year-round; its own operational section says day-use permits come from a
    # Forest Service office "or at trailheads in the summer". It disagreed with
    # itself, so no ranking was needed.
    sources, deferrals = reg
    contradictory = Claim(PERMIT_REQUIREMENT, REC, "", self_contradictory=True,
                          label="recreation.gov")
    forest = Claim(PERMIT_REQUIREMENT, FAQ, "2026-06-12", label="Eldorado NF FAQ")
    got = resolve(PERMIT_REQUIREMENT, contradictory, forest, sources, deferrals, TODAY)
    assert got.rule == INTERNAL_FIRST
    assert got.winner is forest


def test_the_fee_tier_went_to_the_booking_platform_because_it_owns_fees(reg):
    # recreation.gov said $10 for 2-14 nights; the 2022 USFS guide said 2-13.
    # The booking system won, and it should -- it is the thing that charges you.
    sources, deferrals = reg
    booking = Claim(FEES, REC, "2026-06-12", label="recreation.gov")
    guide = Claim(FEES, MOKE_PDF, "2022-08-18", label="2022 USFS guide")
    got = resolve(FEES, booking, guide, sources, deferrals, TODAY)
    assert got.rule == ROLE
    assert got.winner is booking


def test_the_dog_leash_scope_went_to_the_newer_of_two_equal_sources(reg):
    # Three Forest Service documents state the six-foot leash at widening
    # scopes. Same publisher, so authority cannot separate them; the newest
    # stands.
    sources, deferrals = reg
    old = Claim(REGULATION, MOKE_PDF, "2025-01-01", label="2025 regulations sheet")
    new = Claim(REGULATION, FAQ, "2026-06-12", label="2026 forest FAQ")
    got = resolve(REGULATION, old, new, sources, deferrals, TODAY)
    assert got.rule == RECENCY
    assert got.winner is new


def test_the_carson_pass_season_pass_stays_unresolved(reg):
    # Two 2025 Forest Service documents, one selling a $20 season pass and one
    # saying there is no longer one. Same publisher, neither dated more
    # precisely than the year. There is nothing to break the tie with.
    sources, deferrals = reg
    a = Claim(FEES, MOKE_PDF, "2025", label="2025 regulations sheet")
    b = Claim(FEES, MOKE_PDF, "2025", label="2025 permit instructions")
    got = resolve(FEES, a, b, sources, deferrals, TODAY)
    assert got.rule == UNRESOLVED
    assert not got.settled


def test_fishing_follows_the_deferral_to_the_state_wildlife_agency(reg):
    # "State fish and game laws apply" is recreation.gov handing the question
    # to CDFW in its own words.
    sources, deferrals = reg
    platform = Claim(REGULATION, REC, "2026-06-12", label="recreation.gov")
    state = Claim(REGULATION, "https://wildlife.ca.gov/fishing", "2026-01-01", label="CDFW")
    got = resolve(REGULATION, platform, state, sources, deferrals, TODAY)
    assert got.rule == DEFERRAL
    assert got.winner is state
    assert "State fish and game laws apply" in got.reason


def test_a_stale_regulator_does_not_win_on_authority_alone(reg):
    # The hazard the whole model exists for: a stale page from the governing
    # body is exactly how a superseded rule survives online.
    sources, deferrals = reg
    stale_forest = Claim(PERMIT_REQUIREMENT, FAQ, "2021-06-13", label="Forest Service, 2021")
    current_platform = Claim(PERMIT_REQUIREMENT, REC, "2026-06-12", label="recreation.gov, 2026")
    got = resolve(PERMIT_REQUIREMENT, stale_forest, current_platform, sources, deferrals, TODAY)
    assert got.rule == UNRESOLVED_STALE_AUTHORITY
    assert not got.settled, "a stale regulator page is an open question, not a tie to break"


def test_a_current_owner_does_win(reg):
    # The same pairing with a fresh regulator page resolves cleanly, so the
    # staleness clause narrows the rule rather than disabling it. The reason
    # given is the deferral, not our role assignment, because recreation.gov
    # handed this topic over in its own words.
    sources, deferrals = reg
    forest = Claim(PERMIT_REQUIREMENT, FAQ, "2026-06-12", label="Forest Service")
    platform = Claim(PERMIT_REQUIREMENT, REC, "2026-03-01", label="recreation.gov")
    got = resolve(PERMIT_REQUIREMENT, forest, platform, sources, deferrals, TODAY)
    assert got.rule == DEFERRAL
    assert got.winner is forest


def test_role_settles_a_topic_nobody_has_deferred_on(reg):
    # No deferral covers trailhead and road access, so the role assignment is
    # what separates them.
    sources, deferrals = reg
    forest = Claim(ACCESS, FAQ, "2026-06-12", label="Forest Service")
    platform = Claim(ACCESS, REC, "2026-03-01", label="recreation.gov")
    got = resolve(ACCESS, forest, platform, sources, deferrals, TODAY)
    assert got.rule == ROLE
    assert got.winner is forest


def test_a_deferral_does_not_make_a_stale_page_current(reg):
    # Being handed the question establishes authority, never currency.
    sources, deferrals = reg
    stale_forest = Claim(PERMIT_REQUIREMENT, FAQ, "2021-06-13", label="Forest Service, 2021")
    platform = Claim(PERMIT_REQUIREMENT, REC, "2026-06-12", label="recreation.gov, 2026")
    got = resolve(PERMIT_REQUIREMENT, stale_forest, platform, sources, deferrals, TODAY)
    assert got.rule == UNRESOLVED_STALE_AUTHORITY


def test_self_contradiction_is_checked_before_authority(reg):
    # Order matters: if ranking ran first, a self-contradicting regulator would
    # beat a consistent platform on a topic it owns.
    sources, deferrals = reg
    muddled_forest = Claim(PERMIT_REQUIREMENT, FAQ, "2026-06-12", self_contradictory=True,
                           label="Forest Service")
    clear_platform = Claim(PERMIT_REQUIREMENT, REC, "2026-01-01", label="recreation.gov")
    got = resolve(PERMIT_REQUIREMENT, muddled_forest, clear_platform, sources, deferrals, TODAY)
    assert got.rule == INTERNAL_FIRST
    assert got.winner is clear_platform


def test_an_unregistered_source_falls_through_to_recency(reg):
    sources, deferrals = reg
    known = Claim(REGULATION, FAQ, "2026-06-12", label="known")
    unknown = Claim(REGULATION, "https://some-blog.example/x", "2020-01-01", label="unknown")
    got = resolve(REGULATION, known, unknown, sources, deferrals, TODAY)
    assert got.rule == RECENCY
    assert got.winner is known


# -- the registry describes the real world ----------------------------------

def test_the_regulator_does_not_own_booking_and_the_platform_does_not_own_rules(reg):
    sources, _ = reg
    forest = next(s for s in sources if s.source_id == "fs_usda")
    platform = next(s for s in sources if s.source_id == "recreation_gov")
    assert forest.owns(REGULATION) and not forest.owns(BOOKING_MECHANICS)
    assert platform.owns(BOOKING_MECHANICS) and not platform.owns(REGULATION)


def test_the_two_agencies_defer_to_each_other_on_what_the_other_owns(reg):
    # Reciprocity is what makes this a real division of responsibility rather
    # than one publisher being vague.
    _, deferrals = reg
    assert deferral_for("recreation_gov", PERMIT_REQUIREMENT, deferrals).to_source == "fs_usda"
    assert deferral_for("fs_usda", BOOKING_MECHANICS, deferrals).to_source == "recreation_gov"


def test_every_deferral_names_a_registered_source_and_a_real_topic(reg):
    sources, deferrals = reg
    ids = {s.source_id for s in sources}
    from wayproof.provenance import TOPICS
    for d in deferrals:
        assert d.from_source in ids, d.from_source
        assert d.to_source in ids, d.to_source
        assert d.topic in TOPICS, d.topic
        assert len(d.evidence) > 10, f"{d.from_source} deferral needs its sentence"


# -- the derived gaps -------------------------------------------------------

def test_rules_resting_on_a_non_owning_source_are_flagged(reg):
    from wayproof.regulations import load_regulations
    from wayproof.reports import open_questions
    sources, deferrals = reg
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    keys = [q.target_key for q in open_questions(regulations=regs, sources=sources,
                                                 deferrals=deferrals, today=TODAY)
            if "sourced to" in q.target_key]
    assert keys == ["desolation (sourced to Recreation.gov)"], (
        "the Desolation rules were transcribed from the booking platform, which restates "
        "the land manager's regulations rather than making them"
    )


def test_a_stale_source_is_flagged_even_though_it_is_the_regulator(reg):
    from wayproof.permits import load_permits
    from wayproof.reports import open_questions
    sources, deferrals = reg
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    keys = {q.target_key for q in open_questions(permits=list(permits.values()), sources=sources,
                                                 deferrals=deferrals, today=TODAY)
            if "stale source" in q.target_key}
    assert keys == {"inyo_hoover_nonquota (stale source)", "inyo_gtw (stale source)"}


def test_an_unregistered_citation_is_reported_rather_than_trusted(reg):
    from wayproof.regulations import Regulation
    from wayproof.reports import open_questions
    sources, deferrals = reg
    stray = Regulation(regulation_id="x", scope_type="permit_group", scope_value="g",
                       category="fire", summary="y", source_url="https://blog.example/rules")
    keys = [q.target_key for q in open_questions(regulations=[stray], sources=sources,
                                                 deferrals=deferrals, today=TODAY)
            if q.target_file == "data/sources.csv"]
    assert keys == ["https://blog.example/rules"]


def test_no_provenance_gaps_are_derived_without_a_registry():
    # The registry is optional context, not a required input.
    from wayproof.regulations import load_regulations
    from wayproof.reports import open_questions
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    assert [q for q in open_questions(regulations=regs, today=TODAY)
            if "sourced to" in q.target_key] == []


def test_every_cited_url_in_the_real_data_is_registered(reg):
    from wayproof.regulations import load_regulations
    sources, _ = reg
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    unknown = sorted({r.source_url for r in regs
                      if r.source_url and source_for(r.source_url, sources) is None})
    assert unknown == [], f"cited but unregistered: {unknown}"
