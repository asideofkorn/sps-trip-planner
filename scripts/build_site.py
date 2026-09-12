#!/usr/bin/env python3
"""Build the static wayproof.dev site.

Deliberately minimal for now: a landing page plus a live "Help us confirm"
list generated from wayproof.reports.open_questions() against the currently
committed data, so the site can't drift out of sync with the dataset it's
describing -- there's no separately maintained copy to go stale. This is a
first pass meant to prove the DNS -> Pages -> live data -> report-back loop
works end to end; layout, scope, and content get revisited once that's
confirmed working.

Usage
-----
    python scripts/build_site.py --output _site
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wayproof.access import load_approaches
from wayproof.camping import load_campgrounds, load_campsites
from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.park_access import load_park_access
from wayproof.reports import open_questions
from wayproof.timed_entry import load_timed_entry
from wayproof.water import load_water_sources, load_water_source_log

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
            '<li class="q">'
            f'<div class="q-text">{html.escape(q.question)}</div>'
            f'<div class="q-meta"><code class="pill mono">{html.escape(q.target_file)}</code> &middot; '
            f'{html.escape(q.target_key)} &mdash; '
            f'<a href="{url}" target="_blank" rel="noopener">Report / confirm this</a></div>'
            "</li>"
        )
    return f'<ul class="q-list">{"".join(items)}</ul>'


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wayproof</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 720px; margin: 0 auto; padding: 2rem 1.25rem 4rem;
    line-height: 1.5; color: #1a1a1a; background: #fff;
  }}
  a {{ color: #1a5fb4; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e6e6e6; background: #0e0e0e; }}
    a {{ color: #7db8ff; }}
    .q {{ border-color: #333; }}
    pre {{ background: #1c1c1c; border-color: #333; color: #f2f2f2; }}
    .pill {{ background: #1c1c1c; color: #f2f2f2; }}
  }}
  h1 {{ margin-bottom: 0.25rem; }}
  .tagline {{ color: #666; margin-top: 0; }}
  nav a {{ margin-right: 1rem; }}
  section {{ margin-top: 2.5rem; }}
  .q-list {{ list-style: none; padding: 0; margin: 0; }}
  .q {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; }}
  .q-text {{ margin-bottom: 0.35rem; }}
  .q-meta {{ font-size: 0.85rem; color: #777; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .pill {{ background: #f3f3f3; padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em; }}
  pre {{
    background: #f3f3f3; border: 1px solid #ddd; border-radius: 8px;
    padding: 0.9rem 1rem; overflow-x: auto; font-size: 0.9rem;
    line-height: 1.6; color: #1a1a1a;
  }}
  pre code {{ background: none; padding: 0; color: inherit; }}
  footer {{ margin-top: 3rem; font-size: 0.85rem; color: #777; }}
</style>
</head>
<body>
<h1>Wayproof</h1>
<p class="tagline">Open-source, source-backed logistics for hiking, trail running,
backpacking, and mountaineering. Sierra Nevada first, designed to expand to
U.S. public lands.</p>

<nav>
  <a href="https://github.com/{repo}">GitHub</a>
  <a href="https://github.com/{repo}#readme">Docs</a>
  <a href="https://github.com/{repo}/issues/new?template=data_report.md&labels=data">Submit a report</a>
</nav>

<section>
  <h2>Help us confirm ({count} open)</h2>
  <p>Everything below is derived live from the dataset itself on every push to
  main, not a hand-maintained list -- each item is something the data
  currently flags as unconfirmed, missing, or conflicting. Click through to
  report what you know; it opens a pre-filled GitHub issue, reviewed the
  same way as any other data correction.</p>
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
  Built from <a href="https://github.com/{repo}">{repo}</a>'s own dataset.
</footer>
</body>
</html>
"""


def build(output_dir: Path) -> int:
    data = _load_all_data()
    questions = open_questions(**data)
    page = PAGE_TEMPLATE.format(
        repo=REPO, count=len(questions),
        questions_html=_render_questions_html(questions),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(page)
    # Baked into the deployed artifact (not just set in repo Settings) so the
    # custom domain survives every GitHub Actions Pages deployment.
    (output_dir / "CNAME").write_text("wayproof.dev\n")
    return len(questions)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--output", default="_site", help="Output directory (default _site)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    count = build(Path(args.output))
    print(f"Built site into {args.output}/ ({count} open questions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
