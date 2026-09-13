"""The test that should have existed from the first day `plan.py` did.

`plan.py` answers "which permit governs this objective". It resolves that
through `Peak.meta["nearest_trailhead"]`, which `scripts/assign_trailheads.py`
computes as great-circle distance from the summit -- geometry, not a source.
`views.py` labels that same field "UNVERIFIED: assigned by straight-line
proximity... Do not state these as this trailhead's approach list", and then
`plan.py` stated it anyway, under a line reading "we last checked this against
the source on <date>".

The project already holds a *sourced* route name for all 247 SPS peaks, in
`data/collections/sps.csv`. For Picket Guard Peak it says Shepherd Pass Trail
(Inyo NF, east side); the geometry says Mineral King (SEKI, west side). Those
are opposite sides of the range and different agencies. The tool preferred the
geometry and said nothing.

Nothing here asserts which one is right -- resolving that needs a source this
project does not yet have. What it asserts is that the tool must not silently
pick one. A stated "we don't know" is a usable answer; a confident wrong permit
with a verification date attached is the one failure this project cannot have.

Run with:  python -m pytest tests/test_entry_point.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.permits import load_permits
from wayproof.plan import format_plan_summary, resolve_plan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEAKS = os.path.join(ROOT, "data", "peaks.csv")
COLLECTIONS = os.path.join(ROOT, "data", "collections", "sps.csv")
TRAILHEADS = os.path.join(ROOT, "data", "trailheads.csv")
PERMITS = os.path.join(ROOT, "data", "permits.csv")
POLICIES = os.path.join(ROOT, "data", "release_policies.csv")

TRIP = date(2027, 7, 15)
TODAY = date(2026, 9, 13)


def _plan(*names):
    peaks = load_peaks(PEAKS, collections_path=COLLECTIONS)
    return resolve_plan(list(names), TRIP, peaks, load_trailheads(TRAILHEADS),
                        load_permits(PERMITS, POLICIES), today=TODAY)


#: Peaks whose sourced route and computed nearest trailhead name different
#: places, with the agency each implies. Spot-checked by hand against
#: data/collections/sps.csv.
KNOWN_CONFLICTS = [
    ("Picket Guard Peak", "Shepherd Pass", "Mineral King"),
    ("Mount Reinstein", "Maxson", "South Lake"),
    ("Independence Peak", "Robertson Lake", "Onion Valley"),
]


def test_a_contradicted_entry_point_is_never_answered_silently():
    for name, sourced, computed in KNOWN_CONFLICTS:
        result = _plan(name)
        text = " ".join(result.warnings).lower()
        assert "entry point" in text or "trailhead" in text, (
            f"{name}: sourced route names {sourced}, geometry names {computed}, "
            f"and the plan warned about neither. Warnings were: {result.warnings}"
        )
        assert sourced.lower() in text, (
            f"{name}: the warning must name the sourced route ({sourced}), "
            "or a reader cannot check it"
        )


def test_the_rendered_summary_shows_the_conflict_not_just_the_answer():
    # A warning only in the object is not a warning. It has to reach the page.
    peaks = load_peaks(PEAKS, collections_path=COLLECTIONS)
    result = resolve_plan(["Picket Guard Peak"], TRIP, peaks, load_trailheads(TRAILHEADS),
                          load_permits(PERMITS, POLICIES), today=TODAY)
    text = format_plan_summary(result).lower()
    assert "shepherd pass" in text, "the sourced route must appear in the output"
    assert "unresolved" in text or "conflict" in text or "disagree" in text


def test_an_uncontradicted_objective_still_answers_cleanly():
    # The fix must not make the tool useless. Where the sourced route and the
    # geometry agree, the answer stands with no warning.
    result = _plan("Mount Tallac")
    entry = [w for w in result.warnings if "entry point" in w.lower()]
    assert entry == [], f"Mount Tallac should resolve cleanly, got: {entry}"
    assert result.trailhead is not None


def test_the_provenance_line_is_not_attached_to_a_contradicted_answer():
    # The permit row's verification date is real. Printing it under an entry
    # point the project cannot source reads as though the whole answer was
    # verified, which is the specific deception being fixed.
    text = format_plan_summary(_plan("Picket Guard Peak"))
    if "Provenance:" in text:
        before = text.split("Provenance:")[0].lower()
        assert "unresolved" in before or "not verified" in before, (
            "a provenance line appears above no statement that the entry point is unresolved"
        )


def test_the_json_surface_carries_the_conflict_too():
    # An agent reading to_dict() cannot see warning prose. The site already had
    # the mirror-image bug -- JSON saying "unverified" while HTML said nothing
    # -- so this one is pinned in both directions.
    d = _plan("Picket Guard Peak").to_dict()
    assert d["entry_point_resolved"] is False
    assert d["entry_conflicts"][0]["sourced_route"] == "Shepherd Pass Trail"
    assert d["entry_conflicts"][0]["computed_trailhead"] == "Mineral King"

    clean = _plan("Mount Tallac").to_dict()
    assert clean["entry_point_resolved"] is True
    assert "entry_conflicts" not in clean


def test_the_fix_does_not_silence_the_whole_dataset():
    # Flagging everything would be as useless as flagging nothing. Most SPS
    # peaks whose sourced route agrees with the geometry must still answer.
    peaks = load_peaks(PEAKS, collections_path=COLLECTIONS)
    trailheads, permits = load_trailheads(TRAILHEADS), load_permits(PERMITS, POLICIES)
    sps = [p for p in peaks if p.meta.get("list") == "SPS"]
    clean = sum(1 for p in sps
                if not resolve_plan([p.name], TRIP, peaks, trailheads, permits,
                                    today=TODAY).entry_conflicts)
    assert clean >= 80, f"only {clean} of {len(sps)} SPS peaks still answer cleanly"
    assert clean <= len(sps) - 50, (
        f"{clean} of {len(sps)} answer cleanly -- the detector has stopped detecting"
    )
