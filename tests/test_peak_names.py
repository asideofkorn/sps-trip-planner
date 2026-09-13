"""Peak names, and the fact that the source list's typography is not a name.

`data/peaks.csv` keyed on the Sierra Club list's own formatting. That meant
fifteen ALLCAPS names, ninety-odd carrying emblem/mountaineers markers and
stray quotes, and nine the source misspells -- including "Mount Carillion",
which `scripts/merge_gnis.py` has mapped to the correct GNIS spelling since the
coordinates were merged. The project knew the right name and stored the wrong
one.

The user-visible result: `plan.py "Mount Carillon"` answered "not found" for a
peak sitting at line 29, and the project's only community report (R0001) was
filed claiming the peak was missing. That report was false, and nothing caught
it.

Run with:  python -m pytest tests/test_peak_names.py
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayproof.data_loader import load_peaks, normalize_peak_name, resolve_peak_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEAKS = os.path.join(ROOT, "data", "peaks.csv")
COLLECTIONS = os.path.join(ROOT, "data", "collections", "sps.csv")


def _peaks():
    return load_peaks(PEAKS, collections_path=COLLECTIONS)


def test_the_name_a_person_would_type_resolves():
    for query, expected in [
        ("Mount Carillon", "Mount Carillon"),
        ("Mount Whitney", "Mount Whitney"),
        ("mount whitney", "Mount Whitney"),
        ("Foerster Peak", "Foerster Peak"),
        ("Duane Bliss Peak", "Duane Bliss Peak  @"),
    ]:
        peak, candidates = resolve_peak_name(query, _peaks())
        assert peak is not None, f"{query!r} did not resolve (candidates: {candidates})"
        assert peak.name == expected


def test_the_source_lists_own_spellings_still_resolve():
    # Existing references, bookmarks and the Sierra Club list itself all use
    # these. Correcting the key must not orphan them.
    for old in ("Mount Carillion", "Forester Peak", "MOUNT WHITNEY", "Mount MacClure"):
        peak, _ = resolve_peak_name(old, _peaks())
        assert peak is not None, f"the list spelling {old!r} no longer resolves"


def test_no_stored_name_is_allcaps():
    shouty = [p.name for p in _peaks() if p.name.isupper() and " " in p.name]
    assert shouty == [], f"the source uppercases emblem peaks; that is typography: {shouty}"


def test_ambiguity_is_offered_not_guessed():
    # Mount Stanford (N) and (S) are about forty miles apart. Picking one is
    # the same class of error as guessing a trailhead.
    for query in ("Pyramid Peak", "Mount Stanford", "Mount Morgan"):
        peak, candidates = resolve_peak_name(query, _peaks())
        assert peak is None, f"{query!r} should be ambiguous, resolved to {peak and peak.name}"
        assert len(candidates) >= 2, f"{query!r} should offer its candidates, got {candidates}"


def test_markup_only_differences_are_never_merged():
    # Cirque Peak and "Cirque Peak #" are different summits that differ only by
    # the list's mountaineers marker. Normalizing them together would merge two
    # mountains.
    names = {p.name for p in _peaks()}
    assert {"Cirque Peak", "Cirque Peak #"} <= names
    peak, candidates = resolve_peak_name("Cirque Peak", _peaks())
    assert peak is not None and peak.name == "Cirque Peak", "exact match must win"


def test_disambiguators_survive_normalization():
    assert normalize_peak_name("Mount Stanford (N)") != normalize_peak_name("Mount Stanford (S)")
    assert normalize_peak_name("Duane Bliss Peak  @") == "duane bliss peak"


def test_florence_peak_was_not_merged_into_a_different_mountain():
    # scripts/merge_gnis.py maps "Florence Peak" to GNIS "Mount Florence", but
    # a different Mount Florence already exists ~90 miles north in another SPS
    # section. Renaming on that mapping merges two summits.
    by_name = {p.name: p for p in _peaks()}
    assert "Florence Peak" in by_name and "Mount Florence" in by_name
    assert abs(by_name["Florence Peak"].latitude - by_name["Mount Florence"].latitude) > 1.0


def test_the_false_community_report_is_marked_rejected():
    # R0001 claimed Mount Carillon was absent. It never was. A ledger that
    # quietly deletes its own wrong entries is worth less than one that shows
    # them, so it is kept and marked.
    rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "pending_reports.csv"))))
    r0001 = next(r for r in rows if r["report_id"] == "R0001")
    assert r0001["status"] == "rejected"
    assert "false" in r0001["resolution_notes"].lower()
    assert resolve_peak_name(r0001["target_key"], _peaks())[0] is not None, (
        "the peak the report said was missing must resolve"
    )
