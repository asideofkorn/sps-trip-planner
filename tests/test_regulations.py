"""Tests for scoped regulations and their inheritance.

Run with:  python -m pytest tests/test_regulations.py
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.permits import load_permits
from wayproof.regulations import (
    AGENCY,
    JURISDICTION,
    PERMIT_GROUP,
    Regulation,
    group_by_category,
    load_regulations,
    regulations_for,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reg(regulation_id, scope_type, scope_value, category="fire", summary="x"):
    return Regulation(regulation_id=regulation_id, scope_type=scope_type,
                      scope_value=scope_value, category=category, summary=summary)


# -- loading ----------------------------------------------------------------

def test_missing_file_is_not_an_error(tmp_path):
    assert load_regulations(tmp_path / "nope.csv") == []


def test_invalid_scope_type_is_rejected_loudly(tmp_path):
    path = tmp_path / "regulations.csv"
    path.write_text(
        "regulation_id,scope_type,scope_value,category,summary,detail,citation,"
        "source_url,source_last_updated,verified_date\n"
        "x,galaxy,CA,fire,y,,,,,\n"
    )
    with pytest.raises(ValueError, match="Invalid scope_type"):
        load_regulations(path)


# -- inheritance ------------------------------------------------------------

def test_all_three_scopes_resolve_together():
    regs = [
        _reg("state-rule", JURISDICTION, "CA"),
        _reg("forest-rule", AGENCY, "Eldorado National Forest", category="camping"),
        _reg("group-rule", PERMIT_GROUP, "desolation", category="waste"),
        _reg("other-state", JURISDICTION, "NV"),
        _reg("other-group", PERMIT_GROUP, "whitney_zone"),
    ]
    got = regulations_for(regs, permit_group="desolation",
                          agency="Eldorado National Forest", jurisdiction="CA")
    assert {r.regulation_id for r in got} == {"state-rule", "forest-rule", "group-rule"}


def test_a_group_in_another_state_does_not_inherit_california_law():
    # The whole point of storing jurisdiction explicitly: "every group we have
    # is Californian" is true by coincidence of coverage today, and inheriting
    # state law off that coincidence would break silently on the first non-CA
    # permit group.
    regs = [_reg("ca-campfire-permit", JURISDICTION, "CA")]
    assert regulations_for(regs, permit_group="somewhere", agency="Humboldt-Toiyabe NF",
                           jurisdiction="NV") == []


def test_blank_scope_values_match_nothing():
    regs = [_reg("state-rule", JURISDICTION, "CA"), _reg("group-rule", PERMIT_GROUP, "desolation")]
    assert regulations_for(regs) == []


def test_specific_rules_sort_before_the_ones_they_sit_on_top_of():
    # A wilderness's own fire ban should read before the statewide permit
    # requirement it layers onto, not after it.
    regs = [
        _reg("ca-campfire-permit", JURISDICTION, "CA", category="fire"),
        _reg("desolation-campfire-ban", PERMIT_GROUP, "desolation", category="fire"),
    ]
    got = regulations_for(regs, permit_group="desolation", agency="", jurisdiction="CA")
    assert [r.regulation_id for r in got] == ["desolation-campfire-ban", "ca-campfire-permit"]


def test_categories_sort_by_declared_order_with_unknowns_last():
    regs = [
        _reg("a", PERMIT_GROUP, "g", category="commercial"),
        _reg("b", PERMIT_GROUP, "g", category="zzz_unknown"),
        _reg("c", PERMIT_GROUP, "g", category="fire"),
    ]
    got = regulations_for(regs, permit_group="g")
    assert [r.regulation_id for r in got] == ["c", "a", "b"]


def test_inherited_flag_and_scope_label():
    state = _reg("s", JURISDICTION, "CA")
    agency = _reg("a", AGENCY, "Eldorado National Forest")
    group = _reg("g", PERMIT_GROUP, "desolation")
    assert (state.inherited, state.scope_label) == (True, "CA state law")
    assert (agency.inherited, agency.scope_label) == (True, "Eldorado National Forest")
    assert (group.inherited, group.scope_label) == (False, "this permit")


def test_group_by_category_labels_and_orders():
    regs = [
        _reg("a", PERMIT_GROUP, "g", category="waste"),
        _reg("b", PERMIT_GROUP, "g", category="fire"),
    ]
    grouped = group_by_category(regulations_for(regs, permit_group="g"))
    assert [label for label, _ in grouped] == ["Fire", "Waste"]


# -- the real dataset -------------------------------------------------------

def test_campfire_permit_is_stored_once_and_inherited_by_every_california_group():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    campfire = [r for r in regs if r.regulation_id == "ca-campfire-permit"]
    assert len(campfire) == 1, "the statewide rule must exist exactly once"
    assert campfire[0].scope_type == JURISDICTION

    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    for group, rule in permits.items():
        applicable = regulations_for(regs, rule.permit_group, rule.agency, rule.jurisdiction)
        assert any(r.regulation_id == "ca-campfire-permit" for r in applicable), (
            f"{group} should inherit the statewide campfire permit rule"
        )


def test_no_permit_row_still_restates_the_campfire_permit_rule():
    # It had drifted across seven rows -- five calling it a "stove" permit,
    # three giving different URLs. It now lives once in regulations.csv.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    offenders = [
        group for group, rule in permits.items()
        if "campfire permit" in " ".join([
            rule.reservation_method, rule.fee_notes, rule.notes, rule.interagency_note,
        ]).lower()
    ]
    assert offenders == [], f"campfire permit rule duplicated back into: {offenders}"


def test_every_permit_group_declares_a_jurisdiction():
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    missing = [g for g, r in permits.items() if not r.jurisdiction]
    assert missing == [], f"permit groups with no jurisdiction: {missing}"


def test_campfire_rule_carries_the_facts_that_were_previously_missing():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    text = f"{rule.summary} {rule.detail}".lower()
    # Scope was wrong in five rows ("stove" only) and the exemption was wrong.
    for term in ("lantern", "barbeque", "18"):
        assert term in text, f"campfire rule should mention {term!r}"
    assert "261.52" in rule.citation and "4433" in rule.citation
    assert "readyforwildfire.org" in rule.source_url
