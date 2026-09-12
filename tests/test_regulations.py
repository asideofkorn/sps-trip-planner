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
    WILDERNESS,
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
        applicable = regulations_for(regs, rule.permit_group, rule.agency_ids, rule.jurisdiction)
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


# -- the inherited-rule-reads-as-permission failure -------------------------

def test_statewide_campfire_rule_does_not_read_as_permission():
    # Inherited alone, "a permit is required for any campfire" reads as
    # permission. It isn't -- CAL FIRE says local rules override, and Sierra
    # wildernesses commonly ban fires outright.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    text = f"{rule.summary} {rule.detail}".lower()
    assert "does not mean fires are allowed" in text or "not mean fires are allowed" in text
    assert "local restrictions override" in text or "local rules" in text


def test_groups_with_no_local_fire_rule_become_open_questions():
    from wayproof.permits import PermitRule
    from wayproof.reports import open_questions

    silent = PermitRule(permit_group="whitney_zone", agency="Inyo National Forest",
                        permit_type="x", quota_required=True, jurisdiction="CA")
    covered = PermitRule(permit_group="desolation", agency="Eldorado NF", permit_type="y",
                         quota_required=True, jurisdiction="CA")
    regs = [
        _reg("ca-campfire-permit", JURISDICTION, "CA", category="fire"),
        _reg("desolation-campfire-ban", PERMIT_GROUP, "desolation", category="fire"),
    ]
    keys = [q.target_key for q in open_questions(permits=[silent, covered], regulations=regs)
            if q.target_key.endswith("(fire)")]
    assert keys == ["whitney_zone (fire)"]


def test_a_group_stating_its_fire_rule_in_prose_is_not_flagged_as_unknown():
    # Several groups still carry the rule as notes prose rather than a
    # structured regulation. Unmigrated is not the same as unknown.
    from wayproof.permits import PermitRule
    from wayproof.reports import open_questions

    prose = PermitRule(permit_group="mokelumne_free", agency="Eldorado NF", permit_type="z",
                       quota_required=False, jurisdiction="CA",
                       notes="Campfires are NOT allowed anywhere in the Mokelumne Wilderness.")
    regs = [_reg("ca-campfire-permit", JURISDICTION, "CA", category="fire")]
    assert [q for q in open_questions(permits=[prose], regulations=regs)
            if q.target_key.endswith("(fire)")] == []


# -- the scope that inherited to nothing ------------------------------------
#
# `eldorado-dispersed-stay-limit` was scoped to the agency "Eldorado National
# Forest". No permit group carries that string: Desolation's agency reads
# "Eldorado NF / LTBMU" and the Mokelumne groups read "Eldorado NF (Amador
# Ranger District)", because that column is a display name carrying ranger
# district and co-management detail. So the forest-wide rule applied to zero
# groups and nothing said so. These tests make a dead scope fail loudly.

def test_every_regulation_scope_reaches_at_least_one_permit_group():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    reached = set()
    for rule in permits.values():
        for reg in regulations_for(regs, rule.permit_group, rule.agency_ids,
                                   rule.jurisdiction, rule.wilderness_area):
            reached.add(reg.regulation_id)
    dead = [r.regulation_id for r in regs if r.regulation_id not in reached]
    assert dead == [], (
        f"regulations whose scope matches no permit group: {dead}. A rule that "
        "inherits to nothing is worse than a missing one -- it reads as covered."
    )


def test_permit_groups_carry_agency_keys_not_just_display_names():
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    missing = [g for g, r in permits.items() if r.agency and not r.agency_ids]
    assert missing == [], f"permit groups with an agency but no agency_id: {missing}"


def test_agency_matching_ignores_the_display_string():
    # Passing the display name must not accidentally work -- that's the habit
    # that hid the dead scope.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    desolation = permits["desolation"]
    regs = [_reg("forest-rule", AGENCY, "eldorado_nf", category="camping")]
    assert regulations_for(regs, agency=desolation.agency) == []
    assert len(regulations_for(regs, agency=desolation.agency_ids)) == 1


def test_a_co_managed_group_inherits_from_either_manager():
    # Desolation is administered jointly by Eldorado NF and the Lake Tahoe
    # Basin Management Unit. A rule from either applies.
    regs = [
        _reg("eldorado-rule", AGENCY, "eldorado_nf", category="camping"),
        _reg("ltbmu-rule", AGENCY, "ltbmu", category="waste"),
        _reg("inyo-rule", AGENCY, "inyo_nf", category="food_storage"),
    ]
    got = regulations_for(regs, agency=("eldorado_nf", "ltbmu"))
    assert {r.regulation_id for r in got} == {"eldorado-rule", "ltbmu-rule"}


def test_the_eldorado_forest_wide_rule_reaches_all_three_eldorado_groups():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    got = {g for g, r in permits.items()
           if any(x.regulation_id == "eldorado-dispersed-stay-limit"
                  for x in regulations_for(regs, r.permit_group, r.agency_ids,
                                           r.jurisdiction, r.wilderness_area))}
    assert got == {"desolation", "cpma", "mokelumne_free"}


def test_an_agency_key_still_renders_as_a_readable_name():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "eldorado-dispersed-stay-limit")
    assert rule.scope_value == "eldorado_nf"      # what it matches on
    assert rule.scope_label == "Eldorado National Forest"  # what a reader sees


# -- two campfire permits, and the wrong one is not a valid document --------

def test_campfire_rule_distinguishes_the_two_permit_types():
    # CAL FIRE issues one permit for federal- and state-controlled lands and a
    # separate one for private lands. A hiker who grabs the private-lands
    # permit for a national forest trip is carrying the wrong document, so the
    # rule has to say which one applies rather than describing "the" permit.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    text = f"{rule.summary} {rule.detail}".lower()
    assert "federal- and state-controlled lands" in text
    assert "private lands" in text
    assert "written permission from the landowner" in text


def test_campfire_rule_says_which_type_this_project_needs():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    text = f"{rule.summary} {rule.detail}".lower()
    assert "not the private-lands one" in text


def test_campfire_rule_flags_the_land_type_it_cannot_place():
    # Every trailhead is on federal land except two on East Bay Regional Park
    # District land -- a special district that is neither federal, state, nor
    # private. Stating the gap beats silently implying the federal permit
    # covers it.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    assert "East Bay Regional Park District" in rule.detail
    assert "not confirmed" in rule.detail


def test_campfire_rule_warns_off_the_debris_burning_permit():
    # The same portal issues debris-burn permits, which are a different
    # product entirely.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    assert "burning debris" in rule.detail.lower()


def test_the_lantern_discrepancy_was_settled_by_a_third_source():
    # CAL FIRE's permits FAQ omitted lanterns where the campfire-safety page
    # included them. Eldorado NF's FAQ independently names lanterns, so the
    # fuller list now rests on two sources against one summary -- and the
    # detail says so rather than leaving the old hedge in place.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    assert "lantern question is settled" in rule.detail
    assert "two sources against one summary" in rule.detail


def test_the_campfire_permit_must_be_carried_for_inspection():
    # Holding one is not enough: Eldorado NF says it must be available for
    # rangers to check while camping.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "ca-campfire-permit")
    assert "YOU MUST CARRY IT" in rule.detail
    assert "inspect" in rule.detail or "check" in rule.detail


# -- forest-wide rules from the Eldorado NF FAQ -----------------------------

def _eldorado_rules_for(group):
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    rule = permits[group]
    return {r.regulation_id for r in regulations_for(regs, group, rule.agency_ids,
                                                     rule.jurisdiction, rule.wilderness_area)}


def test_the_faq_rules_reach_all_three_eldorado_groups():
    added = {"eldorado-firewood-gathering", "eldorado-dog-leash",
             "eldorado-firearm-carry", "eldorado-drones"}
    for group in ("desolation", "mokelumne_free", "cpma"):
        assert added <= _eldorado_rules_for(group), f"{group} should inherit all four"


def test_the_faq_rules_do_not_leak_to_other_forests():
    assert "eldorado-dog-leash" not in _eldorado_rules_for("whitney_zone")


def test_the_forest_leash_rule_is_stricter_than_the_permit_pages_wording():
    # recreation.gov says "under control at all times"; the forest says
    # physically restrained on a leash under six feet. A reader planning from
    # the looser wording alone would be out of compliance.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    leash = next(r for r in regs if r.regulation_id == "eldorado-dog-leash")
    assert "six feet" in leash.summary
    assert "physically restrained" in leash.summary
    assert "stricter" in leash.detail


def test_firewood_gathering_does_not_read_as_permission_to_have_a_fire():
    # Gathering wood is allowed forest-wide; campfires are banned outright in
    # both wildernesses this forest administers. The rule has to say so, or it
    # reads as an invitation.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    wood = next(r for r in regs if r.regulation_id == "eldorado-firewood-gathering")
    assert "permits the gathering, not the fire" in wood.detail
    assert "Desolation" in wood.detail and "Mokelumne" in wood.detail


def test_the_drone_rule_states_the_practical_answer():
    # "Allowed on the forest, except over wilderness" is technically true and
    # practically backwards here, since nearly every objective is in wilderness.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    drones = next(r for r in regs if r.regulation_id == "eldorado-drones")
    assert "the practical answer for a summit flight is no" in drones.detail


def test_a_permit_group_named_none_reads_as_english_in_a_question():
    # "none" is a real key meaning no wilderness permit is required. Rendered
    # raw it produced "Are campfires actually allowed in none".
    from wayproof.permits import PermitRule
    from wayproof.reports import open_questions

    rule = PermitRule(permit_group="none", agency="", permit_type="No wilderness permit required",
                      quota_required=False, jurisdiction="CA")
    regs = [_reg("ca-campfire-permit", JURISDICTION, "CA", category="fire")]
    question = next(q for q in open_questions(permits=[rule], regulations=regs)
                    if q.target_key.endswith("(fire)"))
    assert "allowed in none" not in question.question
    assert "areas needing no wilderness permit" in question.question
    assert question.target_key == "none (fire)", "the key still points at the row to fix"


# -- the day-use conflict this FAQ closed -----------------------------------

def test_desolation_day_use_is_now_quota_season_only():
    # Resolved in favour of the land manager: Eldorado NF says so on two of its
    # own pages, one last updated 2026-06-12, while recreation.gov (a booking
    # platform, not the regulating authority) and a 2011 map say year-round.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    notes = permits["desolation"].notes
    assert "ONLY during quota season" in notes
    assert "no day-use permit is needed" in notes


def test_the_losing_source_is_still_named_in_the_stored_answer():
    # A reader who books on recreation.gov will meet text saying the opposite.
    # Stating which source lost, and why, beats letting them think we're wrong.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    notes = permits["desolation"].notes
    assert "recreation.gov" in notes and "year-round" in notes
    assert "booking platform rather than the regulating authority" in notes


def test_mokelumne_needs_no_day_use_permit_at_all():
    # Adjacent to Desolation and easily confused with it.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    assert "no day-use permit is needed for day hiking" in permits["mokelumne_free"].notes


def test_the_cpma_naming_trap_is_recorded():
    # The agency calls one unit CPMA on its permit page and CPMU in its FAQ.
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    notes = permits["cpma"].notes
    assert "CPMU" in notes and "CPMA" in notes


# -- the wilderness scope ---------------------------------------------------
#
# Mokelumne Wilderness is entered on two different permits -- the free general
# self-issue one and the quota'd Carson Pass Management Area one -- under a
# single rulebook. Scoping those rules per permit group would have meant
# maintaining eleven rules in two places, which is the drift this table exists
# to stop.

def _resolved(group):
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    permits = load_permits(os.path.join(ROOT, "data", "permits.csv"),
                           os.path.join(ROOT, "data", "release_policies.csv"))
    r = permits[group]
    return {x.regulation_id for x in regulations_for(regs, group, r.agency_ids,
                                                     r.jurisdiction, r.wilderness_area)}


def test_one_rulebook_reaches_both_mokelumne_permits():
    shared = _resolved("mokelumne_free") & _resolved("cpma")
    moke = {r for r in shared if r.startswith("mokelumne-")}
    assert len(moke) >= 11, f"expected the whole Mokelumne rulebook on both permits, got {moke}"


def test_no_mokelumne_rule_is_stored_twice():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    moke = [r for r in regs if r.regulation_id.startswith("mokelumne-")]
    assert len(moke) == len({r.regulation_id for r in moke})
    assert all(r.scope_type == WILDERNESS for r in moke), (
        "a wilderness rule scoped to one permit group would drift against the other"
    )


def test_desolations_rules_do_not_leak_into_mokelumne():
    assert not any(r.startswith("desolation-") for r in _resolved("mokelumne_free"))
    assert not any(r.startswith("mokelumne-") for r in _resolved("desolation"))


def test_a_wilderness_rule_sorts_below_the_permits_own_and_above_the_forests():
    regs = [
        _reg("group", PERMIT_GROUP, "cpma", category="camping"),
        _reg("wild", WILDERNESS, "Mokelumne Wilderness", category="camping"),
        _reg("forest", AGENCY, "eldorado_nf", category="camping"),
        _reg("state", JURISDICTION, "CA", category="camping"),
    ]
    got = regulations_for(regs, permit_group="cpma", agency=("eldorado_nf",),
                          jurisdiction="CA", wilderness="Mokelumne Wilderness")
    assert [r.regulation_id for r in got] == ["group", "wild", "forest", "state"]


def test_a_wilderness_rule_renders_with_the_wilderness_name():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "mokelumne-campfire-ban")
    assert rule.inherited and rule.scope_label == "Mokelumne Wilderness"


# -- the two wildernesses genuinely differ ----------------------------------

def test_the_food_storage_rules_differ_between_neighbouring_wildernesses():
    # Desolation REQUIRES a hard-sided canister, fines up to $5,000. Mokelumne
    # merely recommends one and accepts counterbalance hanging. Carrying a
    # habit from one to the other goes wrong in both directions.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    deso = next(r for r in regs if r.regulation_id == "desolation-bear-canister")
    moke = next(r for r in regs if r.regulation_id == "mokelumne-food-storage")
    assert "REQUIRED" in deso.summary
    assert "RECOMMENDED, not required" in moke.summary
    assert "Desolation" in moke.detail, "the difference must be stated where it's surprising"


def test_the_mokelumne_campfire_ban_blocks_the_forest_wide_firewood_allowance():
    # Eldorado NF lets you gather downed wood forest-wide. Mokelumne says that
    # wood is critical alpine habitat and bans fires outright.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    ban = next(r for r in regs if r.regulation_id == "mokelumne-campfire-ban")
    assert "critical habitat" in ban.detail
    assert "does not translate into a fire here" in ban.detail


def test_the_stricter_camp_setback_is_the_one_stated():
    # The 2025 sheet says 100 ft from water, the 2026 permit page says 200 ft.
    # One figure satisfies both.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "mokelumne-camp-setback")
    assert "Use 200 ft and you satisfy both" in rule.detail


def test_mokelumne_day_use_group_size_is_larger_than_overnight():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "mokelumne-group-size")
    assert "8 people overnight and 12 for a day hike" in rule.summary
    assert "easy to get backwards" in rule.detail


def test_desolation_group_size_does_not_claim_to_cover_day_use():
    # The 12 comes from the overnight booking widget, where a destination zone
    # is selected for the first night. Desolation day-use permits are free,
    # self-issued and not booked there, and no source states their group size.
    # Mokelumne proves the numbers can differ within one forest: 12 day, 8
    # overnight.
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "desolation-group-size")
    assert "NO SOURCE ON HAND STATES A GROUP SIZE FOR DESOLATION DAY USE" in rule.detail
    assert "Do not assume it is also 12" in rule.detail
    assert "Mokelumne" in rule.detail


def test_the_booking_widget_cap_is_recorded_as_flat_not_per_zone():
    regs = load_regulations(os.path.join(ROOT, "data", "regulations.csv"))
    rule = next(r for r in regs if r.regulation_id == "desolation-group-size")
    assert "flat rather than per zone" in rule.detail
