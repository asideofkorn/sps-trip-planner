"""Tests guarding the migration of facts out of the permits `notes` field.

`notes` is where every fact lands when it has nowhere better to go, so it
accretes. It was split once before -- Desolation went from ~3,500 characters to
955 when regulations moved out -- and had grown back to 1,917 before this pass.

Two dangers in a move like this, and one test each:

- **Losing a fact.** Deleting prose is only safe if the fact is resolvable
  somewhere else afterwards. :func:`test_no_migrated_fact_was_lost` pins each
  one to its new home.
- **Keeping both copies.** Five Mokelumne facts were asserted in `notes` AND as
  resolved rules at the same time, created hours apart on the same day. That is
  the failure that produced seven drifting copies of the campfire permit rule.
  :func:`test_no_notes_field_restates_a_resolved_rule` is what would have caught
  it the day it happened.

Run with:  python -m pytest tests/test_notes_split.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.permits import load_permits
from wayproof.regulations import load_regulations, regulations_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERMITS = os.path.join(ROOT, "data", "permits.csv")
POLICIES = os.path.join(ROOT, "data", "release_policies.csv")
REGS = os.path.join(ROOT, "data", "regulations.csv")


def _permits():
    return load_permits(PERMITS, POLICIES)


def _rules_text(group, rule):
    regs = load_regulations(REGS)
    applicable = regulations_for(regs, group, rule.agency_ids, rule.jurisdiction,
                                 rule.wilderness_area)
    return " ".join(f"{r.summary} {r.detail}" for r in applicable).lower()


# -- nothing was lost in the move -------------------------------------------

#: ``permit_group -> [(what it is, phrase that must still resolve as a rule)]``
MIGRATED_TO_RULES = {
    "hoover": [("group size", "15 people and 25 stock"),
               ("sawtooth exception", "sawtooth ridge zone")],
    "sierra_nf": [("stock limit", "25 head of stock")],
    "stanislaus_free": [("elevation campfire ban", "9,000 ft"),
                        ("group size", "15 people"),
                        ("camp setback", "100 ft of lakes"),
                        ("canisters not required", "not required")],
    "gtw_free": [("conditional campfire ban", "fire danger")],
    "mokelumne_free": [("group size", "8 people overnight and 12 for a day hike"),
                       ("campfire ban", "campfires are prohibited everywhere in mokelumne"),
                       ("emigrant setback", "300 ft of emigrant lake"),
                       ("group separation", "within one mile"),
                       ("woods lake", "woods lake")],
}


def test_no_migrated_fact_was_lost():
    permits = _permits()
    missing = []
    for group, facts in MIGRATED_TO_RULES.items():
        text = _rules_text(group, permits[group])
        missing += [f"{group}: {label}" for label, phrase in facts
                    if phrase.lower() not in text]
    assert missing == [], f"facts removed from notes that no rule now carries: {missing}"


#: ``permit_group -> [(what it is, phrase that must be in `excludes`)]``
MIGRATED_TO_EXCLUDES = {
    "whitney_zone": [("north fork approaches", "north fork of lone pine creek"),
                     ("named routes", "mountaineers route"),
                     ("what to use instead", "inyo_jmw_aaw"),
                     ("modelling caveat", "no route-level data")],
    "gtw_free": [("cottonwood entries", "cottonwood pass"),
                 ("what to use instead", "inyo_gtw")],
    "cpma": [("cpma only", "does not cover the wider mokelumne")],
    # Probe on a phrase distinctive to the exclusion. "cpma" alone matches the
    # legitimate "non-CPMA entry points" in the parking sentence.
    "mokelumne_free": [("three lakes", "winnemucca"),
                       ("cpma boundary", "carson pass management area")],
    "inyo_hoover_nonquota": [("guiding limit", "yosemite mountain guides")],
}


def test_no_scope_limit_was_lost():
    permits = _permits()
    missing = []
    for group, facts in MIGRATED_TO_EXCLUDES.items():
        text = permits[group].excludes.lower()
        missing += [f"{group}: {label}" for label, phrase in facts
                    if phrase.lower() not in text]
    assert missing == [], f"scope limits removed from notes that `excludes` lacks: {missing}"


def test_the_whitney_exclusion_survived_intact():
    # The single most consequential fact here: act on it wrongly and you reach
    # the trailhead holding a permit that does not admit you.
    excludes = _permits()["whitney_zone"].excludes.lower()
    for route in ("mountaineers route", "east face", "east buttress", "mount russell"):
        assert route in excludes, f"{route} must stay named"
    assert "does not cover" in excludes or "not cover" in excludes


# -- and no fact is asserted twice ------------------------------------------

def test_no_notes_field_restates_a_resolved_rule():
    # Generalises the campfire-permit check to every rule. A fact asserted in
    # two places is a fact maintained in neither.
    permits = _permits()
    offenders = []
    for group, rule in permits.items():
        text = _rules_text(group, rule)
        if not text.strip():
            continue
        notes = rule.notes.lower()
        for label, phrase in MIGRATED_TO_RULES.get(group, []):
            if phrase.lower() in notes:
                offenders.append(f"{group}: {label}")
    assert offenders == [], f"still stated in notes as well as in a rule: {offenders}"


def test_no_notes_field_restates_a_scope_limit():
    permits = _permits()
    offenders = []
    for group, facts in MIGRATED_TO_EXCLUDES.items():
        notes = permits[group].notes.lower()
        offenders += [f"{group}: {label}" for label, phrase in facts
                      if phrase.lower() in notes]
    assert offenders == [], f"still stated in notes as well as in excludes: {offenders}"


# -- the field stays a miscellany rather than a dumping ground --------------

def test_notes_stays_short_enough_to_read():
    # Not a style rule. Past roughly this length the field is holding facts
    # that belong somewhere structured, which is how it refilled last time.
    # The cap allows for the three categories this pass deliberately left in
    # prose -- permit validity mechanics, cancellation policy, and conditions.
    # Structuring those is what would let it come down further.
    permits = _permits()
    over = {g: len(r.notes) for g, r in permits.items() if len(r.notes) > 1400}
    assert over == {}, f"notes fields long enough to be hiding structured facts: {over}"


def test_notes_no_longer_restates_its_own_structured_columns():
    # Desolation's quota season sat in notes AND in quota_season_start/end,
    # and its parking fees sat in notes AND in fee_notes.
    permits = _permits()
    deso = permits["desolation"]
    assert deso.quota_season_end == (9, 30)
    assert "September 30 each year" not in deso.notes
    assert "parking fee" not in deso.notes.lower()
    assert "parking" in deso.fee_notes.lower()


# -- the exclusion has to reach the page, or moving it made things worse ----

def test_the_whitney_exclusion_reaches_all_three_surfaces():
    import json

    from wayproof.model import Trailhead
    from wayproof.render import (
        render_json, render_trailhead_html, render_trailhead_markdown,
    )
    from wayproof.views import trailhead_view

    th = Trailhead(name="Whitney Portal", latitude=36.5872, longitude=-118.2400,
                   permit_group="whitney_zone")
    view = trailhead_view(th, _permits()["whitney_zone"])

    html = render_trailhead_html(view)
    md = render_trailhead_markdown(view)
    data = json.loads(render_json(view))

    for text in (html, md):
        assert "does NOT cover" in text or "does not cover" in text.lower()
        assert "Mountaineers Route" in text
        assert "North Fork" in text
    assert "Mountaineers Route" in data["permit"]["excludes"]


def test_the_exclusion_reads_before_the_rules():
    # Being wrong here is discovered at the trailhead and cannot be fixed
    # there, so it must not sit below a wall of regulations.
    from wayproof.model import Trailhead
    from wayproof.render import render_trailhead_markdown
    from wayproof.views import trailhead_view

    th = Trailhead(name="Whitney Portal", latitude=36.5872, longitude=-118.2400,
                   permit_group="whitney_zone")
    md = render_trailhead_markdown(trailhead_view(
        th, _permits()["whitney_zone"], regulations=load_regulations(REGS)))
    assert "Rules in force" in md, "this view should carry inherited rules"
    assert md.index("does NOT cover") < md.index("Rules in force")


def test_a_permit_with_no_exclusion_renders_no_block():
    from wayproof.model import Trailhead
    from wayproof.render import render_trailhead_markdown
    from wayproof.views import trailhead_view

    th = Trailhead(name="Anywhere", latitude=37.0, longitude=-119.0, permit_group="seki")
    md = render_trailhead_markdown(trailhead_view(th, _permits()["seki"]))
    assert "does NOT cover" not in md
