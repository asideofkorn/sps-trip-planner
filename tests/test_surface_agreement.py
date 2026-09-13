"""The three surfaces must assert the same facts, checked on the real build.

The README's central claim is that HTML, Markdown and JSON cannot disagree,
because one view model feeds all three. That held for regulations and broke for
the permit: `evidence` was attached to the view's top level instead of inside
the `permit` block, so both renderers looked it up as `permit["evidence"]`,
found nothing, and rendered nothing -- while the JSON published it. For two
days, 66 of 88 published pages told a machine the permit was "Not
independently verified" and told a person nothing at all.

The existing consistency test compared hand-picked strings on one synthetic
view. This one walks the actual generated site.

Run with:  python -m pytest tests/test_surface_agreement.py
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def site():
    scratch = os.environ.get("CLAUDE_SCRATCHPAD") or tempfile.gettempdir()
    out = tempfile.mkdtemp(prefix="wayproof-site-", dir=scratch)
    subprocess.run([sys.executable, "scripts/build_site.py", "--output", out],
                   cwd=ROOT, check=True, capture_output=True)
    return out


def _pages(site):
    for path in sorted(glob.glob(f"{site}/trailheads/*.json")):
        slug = os.path.basename(path)[:-5]
        if slug == "index":          # the trailhead index, not a trailhead
            continue
        data = json.load(open(path))
        html = open(f"{site}/trailheads/{slug}/index.html").read().lower()
        md = open(f"{site}/trailheads/{slug}.md").read().lower()
        yield slug, data, html, md


def test_every_permit_evidence_id_reaches_both_human_surfaces(site):
    missing = []
    for slug, data, html, md in _pages(site):
        evidence = data.get("permit", {}).get("evidence") or {}
        for entry in evidence.get("entries", []):
            eid = entry["entry_id"].lower()
            if eid not in html or eid not in md:
                missing.append(f"{slug}:{eid}")
    assert missing == [], (
        f"{len(missing)} evidence ids are published in JSON but missing from a human "
        f"surface, e.g. {missing[:3]}"
    )


def test_no_page_claims_unverified_on_one_surface_and_stays_silent_on_others(site):
    # The specific two-day bug, pinned.
    divergent = []
    for slug, data, html, md in _pages(site):
        evidence = data.get("permit", {}).get("evidence") or {}
        if evidence.get("status") != "unverified":
            continue
        if "not independently verified" not in html or "not independently verified" not in md:
            divergent.append(slug)
    assert divergent == [], f"JSON says unverified, humans told nothing: {divergent}"


def test_an_open_conflict_is_visible_on_all_three(site):
    divergent = []
    for slug, data, html, md in _pages(site):
        evidence = data.get("permit", {}).get("evidence") or {}
        for conflict in evidence.get("open_conflicts", []):
            if conflict.lower() not in html or conflict.lower() not in md:
                divergent.append(f"{slug}:{conflict}")
    assert divergent == [], f"open conflicts published only in JSON: {divergent}"


def test_the_evidence_lives_in_one_place_in_the_view():
    # It was duplicated at the view top level and inside `permit`; the
    # renderers read one and the JSON published the other.
    from wayproof.model import Trailhead
    from wayproof.permits import PermitRule
    from wayproof.views import trailhead_view

    view = trailhead_view(
        Trailhead(name="X", latitude=37.0, longitude=-119.0, permit_group="seki"),
        PermitRule(permit_group="seki", agency="A", permit_type="P", quota_required=True),
    )
    assert "evidence" in view["permit"]
    assert "evidence" not in view, "a second copy at the top level will drift from the first"
