#!/usr/bin/env python3
"""Build the static wayproof.dev site.

Generates, from the committed dataset on every build:

- a landing page whose "Help us confirm" list comes straight from
  ``wayproof.reports.open_questions()``;
- one page per trailhead, led by the permit that governs entry there --
  agency, quota season, fees, and the dates you actually need to act on;
- ``sitemap.xml`` and ``robots.txt``.

Every generated page ships three ways: HTML for people, Markdown for agents,
JSON for programs. All three render from one view model
(:mod:`wayproof.views`) through :mod:`wayproof.render`, so no surface can
assert a fact another one doesn't.

Usage
-----
    python scripts/build_site.py --output _site
"""

from __future__ import annotations

import argparse
import datetime
import html
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wayproof.access import load_approaches
from wayproof.camping import load_campgrounds, load_campsites
from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.park_access import load_park_access
from wayproof.permit_zones import load_permit_zones
from wayproof.permits import load_permits, load_source_log
from wayproof.render import (
    STYLESHEET,
    render_json,
    render_robots,
    render_sitemap,
    render_trailhead_html,
    render_trailhead_index_html,
    render_trailhead_markdown,
)
from wayproof.reports import open_questions
from wayproof.timed_entry import load_timed_entry
from wayproof.views import SITE_URL, trailhead_views
from wayproof.water import load_water_source_log, load_water_sources

REPO = "asideofkorn/wayproof"

_ISSUE_BODY = """**What is this about?**
{target_key} (`{target_file}`)

**What are you reporting?**
{question}

**Evidence** (optional)


**How confident are you?** (check one)
- [ ] Firsthand -- you saw or experienced it yourself
- [ ] Official source -- a citable page or document (link it above)
- [ ] Told by staff -- a ranger, gate attendant, or reservation agent told you in person
- [ ] Secondhand -- you believe this but haven't independently confirmed it

**Which file, if you know?** (optional -- leave blank if unsure)
{target_file}
"""


def _issue_url(target_file: str, target_key: str, question: str) -> str:
    title = f"[data] {target_key}"
    body = _ISSUE_BODY.format(target_key=target_key, target_file=target_file, question=question)
    return f"https://github.com/{REPO}/issues/new?labels=data&title={quote(title)}&body={quote(body)}"


def _load_all_data() -> dict:
    return dict(
        peaks=load_peaks("data/peaks.csv", collections_path="data/collections/sps.csv"),
        trailheads=load_trailheads("data/trailheads.csv"),
        approaches=load_approaches("data/approaches.csv"),
        water_sources=load_water_sources("data/water_sources.csv"),
        water_source_log=load_water_source_log("data/water_source_log.csv"),
        campgrounds=load_campgrounds("data/campgrounds.csv"),
        campsites=load_campsites("data/campsites.csv"),
        park_access=list(load_park_access("data/park_access.csv").values()),
        timed_entry=[t for entries in load_timed_entry("data/timed_entry.csv").values() for t in entries],
    )


def _render_questions_html(questions) -> str:
    if not questions:
        return "<p>No open questions on file right now.</p>"
    items = []
    for q in questions:
        url = _issue_url(q.target_file, q.target_key, q.question)
        items.append(
            '<li class="card">'
            f'<div>{html.escape(q.question)}</div>'
            f'<div class="meta"><span class="pill">{html.escape(q.target_file)}</span> &middot; '
            f'{html.escape(q.target_key)} &mdash; '
            f'<a href="{url}" target="_blank" rel="noopener">Report / confirm this</a></div>'
            "</li>"
        )
    return f'<ul class="plain" style="list-style:none;padding:0">{"".join(items)}</ul>'


LANDING_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wayproof -- Source-Backed Permit &amp; Access Logistics for the Sierra Nevada</title>
<meta name="description" content="Which permit governs your objective, when reservations
open, what it costs, and what source says so. Sierra Nevada first, open source, every
fact dated.">
<link rel="canonical" href="{site}/">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<h1>Wayproof</h1>
<p class="tagline">Open-source, source-backed logistics for hiking, trail running,
backpacking, and mountaineering. Sierra Nevada first, designed to expand to
U.S. public lands.</p>

<p class="lede">Which permit governs your objective, when its reservations open,
what it costs, and which source says so &mdash; every fact dated, and the
uncertain ones labelled rather than guessed.</p>

<nav>
  <a href="/trailheads/">Trailheads</a>
  <a href="https://github.com/{repo}">GitHub</a>
  <a href="https://github.com/{repo}#readme">Docs</a>
  <a href="https://github.com/{repo}/issues/new?template=data_report.md&labels=data">Submit a report</a>
</nav>

<section>
  <h2>Start with a trailhead</h2>
  <p>{trailhead_count} trailheads, each with the permit that governs entry there,
  its quota season, fees, and the dates you need to act on.</p>
  <ul class="plain">{trailhead_sample}</ul>
  <p><a href="/trailheads/">All {trailhead_count} trailheads &rarr;</a></p>
</section>

<section>
  <h2>Help us confirm ({count} open)</h2>
  <p>Everything below is derived live from the dataset itself on every build,
  not a hand-maintained list -- each item is something the data currently flags
  as unconfirmed, missing, or conflicting. Click through to report what you
  know; it opens a pre-filled GitHub issue, reviewed the same way as any other
  data correction.</p>
  {questions_html}
</section>

<section>
  <h2>Use it yourself</h2>
  <pre><code>pip install -e .
wayproof "Mount Whitney" --date 2027-07-15</code></pre>
  <p>See the <a href="https://github.com/{repo}#readme">README</a> for the full
  CLI and what it does and doesn't cover today.</p>
</section>

<footer>
  <p>Built from <a href="https://github.com/{repo}">{repo}</a>'s own dataset.</p>
  <p class="meta">Planning aid, not a booking guarantee -- verify the current rule at
  the official source before acting on any date here.</p>
</footer>
</body>
</html>
"""

# Trailheads whose permit rule is richest make the best front-door examples.
_FEATURED = ["Whitney Portal", "South Lake (Bishop Pass)", "Onion Valley (Kearsarge Pass)",
             "Shepherd Pass", "Twin Lakes (Bridgeport)", "Mineral King"]


def _featured_html(views) -> str:
    by_name = {v["name"]: v for v in views}
    out = []
    for name in _FEATURED:
        view = by_name.get(name)
        if not view:
            continue
        permit = view["permit"]
        label = permit["permit_type"] if permit["known"] else "permit unknown"
        out.append(f'<li><a href="{view["url_path"]}">{html.escape(view["name"])}</a> '
                   f'<span class="meta">&mdash; {html.escape(label)}</span></li>')
    return "".join(out)


def build(output_dir: Path, today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    permits = load_permits("data/permits.csv", "data/release_policies.csv")
    data = _load_all_data()
    questions = open_questions(permits=list(permits.values()), **data)

    views = trailhead_views(
        trailheads=data["trailheads"],
        permits=permits,
        approaches=data["approaches"],
        peaks=data["peaks"],
        source_log=load_source_log("data/permit_source_log.csv"),
        zones=load_permit_zones("data/permit_zones.csv"),
        questions=questions,
        today=today,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "style.css").write_text(STYLESHEET)
    # Baked into the deployed artifact (not just set in repo Settings) so the
    # custom domain survives every GitHub Actions Pages deployment.
    (output_dir / "CNAME").write_text("wayproof.dev\n")

    (output_dir / "index.html").write_text(LANDING_TEMPLATE.format(
        site=SITE_URL, repo=REPO, count=len(questions),
        questions_html=_render_questions_html(questions),
        trailhead_count=len(views), trailhead_sample=_featured_html(views),
    ))

    trailhead_dir = output_dir / "trailheads"
    trailhead_dir.mkdir(parents=True, exist_ok=True)
    (trailhead_dir / "index.html").write_text(render_trailhead_index_html(views))
    (trailhead_dir / "index.json").write_text(render_json(
        {"type": "trailhead_index", "count": len(views), "generated": today.isoformat(),
         "trailheads": [{"name": v["name"], "slug": v["slug"], "url_path": v["url_path"],
                         "permit_group": v["permit"].get("permit_group", "")} for v in views]}
    ))

    for view in views:
        page_dir = trailhead_dir / view["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render_trailhead_html(view))
        (trailhead_dir / f'{view["slug"]}.md').write_text(render_trailhead_markdown(view))
        (trailhead_dir / f'{view["slug"]}.json').write_text(render_json(view))

    urls = [f"{SITE_URL}/", f"{SITE_URL}/trailheads/"]
    urls += [v["canonical_url"] for v in views if v["indexable"]]
    (output_dir / "sitemap.xml").write_text(render_sitemap(urls))
    (output_dir / "robots.txt").write_text(render_robots())

    return {"open_questions": len(questions), "trailheads": len(views),
            "indexed_urls": len(urls)}


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--output", default="_site", help="Output directory (default _site)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    stats = build(Path(args.output))
    print(f"Built site into {args.output}/: "
          f"{stats['trailheads']} trailhead pages (x3 representations), "
          f"{stats['open_questions']} open questions, "
          f"{stats['indexed_urls']} URLs in sitemap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
