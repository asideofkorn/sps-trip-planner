"""Renderers: one view model (see :mod:`wayproof.views`) to three surfaces.

Every page is published three ways -- HTML for people, Markdown for agents,
JSON for programs -- and all three render from the same dict, so they cannot
assert different facts.

The Markdown surface carries provenance and uncertainty inline rather than as
page furniture, because an agent summarising a permit rule to someone needs
the "verified on" date and the "unconfirmed" flag attached to the claim
itself, not in a sidebar it won't quote. It also states its own canonical URL
so it can be cited accurately. What it deliberately does *not* do is address
the agent or ask it to do anything: instructions aimed at a reader's agent are
prompt injection, and a site whose entire value is being a trustworthy source
cannot also be a source that injects instructions into its readers' tools.
"""

from __future__ import annotations

import html
import json
from typing import Optional, Sequence

from .views import REPO, SITE_URL

STYLESHEET = """\
:root { color-scheme: light dark; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 760px; margin: 0 auto; padding: 2rem 1.25rem 4rem;
  line-height: 1.55; color: #1a1a1a; background: #fff;
}
a { color: #1a5fb4; }
h1 { margin-bottom: 0.25rem; font-size: 1.9rem; }
h2 { margin-top: 2.25rem; font-size: 1.25rem; }
h3 { margin-top: 1.5rem; font-size: 1.05rem; }
.tagline, .subtitle { color: #666; margin-top: 0; }
nav.crumbs { font-size: 0.85rem; margin-bottom: 1.5rem; }
nav.crumbs a { margin-right: 0.35rem; }
.lede { font-size: 1.05rem; }
.card { border: 1px solid #ddd; border-radius: 8px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }
.card h3 { margin-top: 0; }
.meta { font-size: 0.85rem; color: #777; }
.pill { background: #f3f3f3; padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.flag { display: inline-block; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.04em; padding: 0.1em 0.45em; border-radius: 4px;
        border: 1px solid #bbb; color: #555; }
.flag.confirmed { border-color: #2a7; color: #176; }
.flag.unconfirmed { border-color: #c82; color: #a51; }
dl.facts { display: grid; grid-template-columns: max-content 1fr; gap: 0.35rem 1rem; margin: 0; }
dl.facts dt { color: #666; }
dl.facts dd { margin: 0; }
ul.events { list-style: none; padding: 0; }
ul.events li { border-left: 3px solid #1a5fb4; padding: 0.35rem 0 0.35rem 0.75rem; margin-bottom: 0.5rem; }
ul.plain { padding-left: 1.1rem; }
pre { background: #f3f3f3; border: 1px solid #ddd; border-radius: 8px;
      padding: 0.9rem 1rem; overflow-x: auto; font-size: 0.9rem; line-height: 1.6; color: #1a1a1a; }
pre code { background: none; padding: 0; color: inherit; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
footer { margin-top: 3.5rem; padding-top: 1rem; border-top: 1px solid #ddd;
         font-size: 0.85rem; color: #777; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #0e0e0e; }
  a { color: #7db8ff; }
  .card, dl.facts dt { border-color: #333; }
  .card { border-color: #333; }
  .pill { background: #1c1c1c; color: #f2f2f2; }
  pre { background: #1c1c1c; border-color: #333; color: #f2f2f2; }
  .flag { border-color: #555; color: #bbb; }
  .flag.confirmed { border-color: #2a7; color: #6d9; }
  .flag.unconfirmed { border-color: #c82; color: #e9a; }
  th, td { border-color: #2a2a2a; }
  footer { border-color: #333; }
}
"""


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _page(title: str, description: str, canonical: str, body: str,
          alternates: Sequence[tuple] = (), indexable: bool = True,
          jsonld: Optional[dict] = None) -> str:
    head = [
        '<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_e(title)}</title>',
        f'<meta name="description" content="{_e(description)}">',
        f'<link rel="canonical" href="{_e(canonical)}">',
        '<link rel="stylesheet" href="/style.css">',
    ]
    if not indexable:
        head.append('<meta name="robots" content="noindex,follow">')
    for mime, href in alternates:
        head.append(f'<link rel="alternate" type="{_e(mime)}" href="{_e(href)}">')
    if jsonld:
        head.append('<script type="application/ld+json">'
                    f'{json.dumps(jsonld)}</script>')
    head.append('</head>')
    return "\n".join(head) + f"\n<body>\n{body}\n</body>\n</html>\n"


def _footer(view: Optional[dict] = None) -> str:
    lines = ['<footer>']
    if view:
        lines.append(
            f'<p>Machine-readable: '
            f'<a href="/trailheads/{_e(view["slug"])}.md">Markdown</a> &middot; '
            f'<a href="/trailheads/{_e(view["slug"])}.json">JSON</a></p>'
        )
        lines.append(f'<p class="meta">Page generated {_e(view["generated"])} from '
                     f'<a href="https://github.com/{REPO}">{REPO}</a>\'s dataset.</p>')
    lines.append(
        f'<p><a href="/">Wayproof</a> &middot; '
        f'<a href="/trailheads/">All trailheads</a> &middot; '
        f'<a href="https://github.com/{REPO}">GitHub</a></p>'
    )
    lines.append('<p class="meta">Planning aid, not a booking guarantee -- verify the '
                 'current rule at the official source before acting on any date here.</p>')
    lines.append('</footer>')
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Trailhead: HTML
# --------------------------------------------------------------------------

def _permit_html(permit: dict) -> str:
    if not permit["known"]:
        return "<p>No permit rule resolved for this trailhead yet.</p>"

    out = ['<h2>Permit</h2>']
    out.append('<dl class="facts">')
    rows = [
        ("Permit", permit["permit_type"]),
        ("Agency", permit["agency"]),
        ("Quota", "Required" if permit["quota_required"] else "Not quota-limited"),
        ("Quota season", permit["quota_season"]),
        ("Fees", permit["fee_notes"]),
    ]
    for label, value in rows:
        if value:
            out.append(f'<dt>{_e(label)}</dt><dd>{_e(value)}</dd>')
    if permit["apply_url"]:
        out.append(f'<dt>Apply</dt><dd><a href="{_e(permit["apply_url"])}" '
                   f'rel="nofollow">{_e(permit["apply_url"])}</a></dd>')
    out.append('</dl>')

    if permit["release_events"]:
        out.append('<h2>Key dates</h2>')
        out.append('<ul class="events">')
        for event in permit["release_events"]:
            note = f'<div class="meta">{_e(event["notes"])}</div>' if event["notes"] else ""
            out.append(f'<li>{_e(event["description"])}{note}</li>')
        out.append('</ul>')
    elif permit["quota_required"]:
        out.append('<h2>Key dates</h2>')
        out.append('<p>This permit group has no structured release policy yet, so exact '
                   'release dates are not computed here. The rule as published:</p>')

    if permit["reservation_method"]:
        out.append(f'<h3>How reservations work</h3><p>{_e(permit["reservation_method"])}</p>')
    if permit["notes"]:
        out.append(f'<h3>Notes</h3><p>{_e(permit["notes"])}</p>')
    if permit["interagency_note"]:
        out.append(f'<h3>Travel into neighbouring units</h3>'
                   f'<p>{_e(permit["interagency_note"])}</p>')
    return "\n".join(out)


def _provenance_html(permit: dict, source_log: Sequence[dict]) -> str:
    out = ['<h2>Provenance</h2>']
    if permit.get("source_last_updated") or permit.get("verified_date"):
        out.append('<dl class="facts">')
        if permit.get("source_last_updated"):
            out.append('<dt>Source last updated</dt>'
                       f'<dd>{_e(permit["source_last_updated"])}</dd>')
        if permit.get("verified_date"):
            out.append(f'<dt>We last checked</dt><dd>{_e(permit["verified_date"])}</dd>')
        out.append('</dl>')
        out.append('<p class="meta">Those are different claims: a source can be current '
                   'and still not have been re-checked here recently.</p>')
    if source_log:
        out.append('<h3>Verification history</h3>')
        out.append('<table><thead><tr><th>Checked</th><th>Verdict</th><th>Source</th>'
                   '</tr></thead><tbody>')
        for entry in source_log:
            link = (f'<a href="{_e(entry["source_url"])}" rel="nofollow">source</a>'
                    if entry["source_url"] else "")
            out.append(f'<tr><td>{_e(entry["date_checked"])}</td>'
                       f'<td>{_e(entry["verdict"])}<div class="meta">'
                       f'{_e(entry["summary"])}</div></td><td>{link}</td></tr>')
        out.append('</tbody></table>')
    return "\n".join(out)


def render_trailhead_html(view: dict) -> str:
    permit = view["permit"]
    loc, land = view["location"], view["land"]

    body = [
        '<nav class="crumbs"><a href="/">Wayproof</a> / '
        '<a href="/trailheads/">Trailheads</a></nav>',
        f'<h1>{_e(view["name"])}</h1>',
        f'<p class="subtitle">{_e(land["wilderness_area"] or land["land_agency"])}'
        f'{" &middot; " + _e(land["land_agency"]) if land["wilderness_area"] and land["land_agency"] else ""}'
        '</p>',
    ]
    if view["notes"]:
        body.append(f'<p class="lede">{_e(view["notes"])}</p>')

    body.append(_permit_html(permit))

    regs = view.get("regulations", [])
    if regs:
        body.append('<h2>Rules in force</h2>')
        body.append('<p class="meta">What applies once you hold the permit. Rules marked with a '
                    'scope other than "this permit" are inherited &mdash; state law or an '
                    'agency-wide policy &mdash; and are stored once rather than restated per '
                    'permit.</p>')
        for group in regs:
            body.append(f'<h3>{_e(group["label"])}</h3>')
            for rule in group["rules"]:
                bits = []
                if rule["detail"]:
                    bits.append(_e(rule["detail"]))
                if rule["citation"]:
                    bits.append(f'<em>{_e(rule["citation"])}</em>')
                if rule["source_url"]:
                    bits.append(f'<a href="{_e(rule["source_url"])}" rel="nofollow">source</a>')
                meta = (f'<div class="meta">{" &middot; ".join(bits)}</div>') if bits else ""
                scope = (f' <span class="flag">{_e(rule["scope"])}</span>'
                         if rule["inherited"] else "")
                body.append(f'<div class="card"><div>{_e(rule["summary"])}{scope}</div>{meta}</div>')

    zones = view.get("zones", {})
    if zones.get("quota_by_zone"):
        body.append(f'<h2>Destination zones ({zones["count"]})</h2>')
        body.append('<p>This permit\'s quota is assigned per destination zone, not per '
                    'trailhead. Booking asks which zone you will spend your <strong>first '
                    'night</strong> in; after that night you may move between zones on the '
                    'same permit, as long as you exit by the last date booked. A day hike '
                    'needs no zone.</p>')
        body.append('<p class="meta">Which zone serves a given objective is not asserted here. '
                    'Zone names often match a lake or peak, but a zone is a mapped boundary and '
                    'a name is not that boundary &mdash; that mapping needs the official zone '
                    'map, and is an open question until it has one.</p>')
        body.append('<ul class="plain">')
        for zone in zones["entries"]:
            note = f' <span class="meta">&mdash; {_e(zone["notes"])}</span>' if zone["notes"] else ""
            body.append(f'<li><span class="pill">{_e(zone["label"])}</span>{note}</li>')
        body.append('</ul>')

    if view["approach_exceptions"]:
        body.append('<h2>Route-specific permits from this trailhead</h2>')
        body.append('<p>These objectives do not simply inherit the trailhead default -- '
                    'a different named route can fall under a different permit.</p>')
        for a in view["approach_exceptions"]:
            flag = f'<span class="flag {_e(a["status"])}">{_e(a["status"])}</span>'
            src = (f' &middot; <a href="{_e(a["source_url"])}" rel="nofollow">source</a>'
                   if a["source_url"] else "")
            group = a["permit_group"] or "not yet established"
            body.append(
                f'<div class="card"><h3>{_e(a["peak_name"])} {flag}</h3>'
                f'<p>Via {_e(a["approach_name"])} &mdash; permit: '
                f'<span class="pill">{_e(group)}</span></p>'
                f'<p class="meta">{_e(a["notes"])}{src}</p></div>'
            )

    body.append('<h2>Location</h2><dl class="facts">')
    if loc["latitude"] is not None and loc["longitude"] is not None:
        body.append(f'<dt>Coordinates</dt><dd>{loc["latitude"]:.4f}, {loc["longitude"]:.4f}</dd>')
    if loc["elevation_ft"]:
        body.append(f'<dt>Elevation</dt><dd>{loc["elevation_ft"]:,.0f} ft</dd>')
    for label, value in (("Side of range", loc["side"]),
                         ("Wilderness", land["wilderness_area"]),
                         ("Agency", land["land_agency"]),
                         ("Park", land["park"])):
        if value:
            body.append(f'<dt>{_e(label)}</dt><dd>{_e(value)}</dd>')
    body.append('</dl>')

    nearby = view["peaks_nearby"]
    if nearby["count"]:
        body.append(f'<h2>Peaks nearest this trailhead ({nearby["count"]})</h2>')
        body.append('<p class="meta">Assigned by straight-line proximity, not by a verified '
                    'approach. Permits attach to where you enter the wilderness, so a peak '
                    'listed here may well be climbed from somewhere else -- and a long '
                    'point-to-point route may pass peaks that list a different trailhead '
                    'entirely. Treat this as a starting point, not an approach list.</p>')
        body.append('<ul class="plain">')
        body.extend(f'<li>{_e(name)}</li>' for name in nearby["names"])
        body.append('</ul>')

    if view["open_questions"]:
        body.append('<h2>Help us confirm</h2><ul class="plain">')
        for q in view["open_questions"]:
            body.append(f'<li>{_e(q["question"])}</li>')
        body.append('</ul>')
        body.append(f'<p><a href="https://github.com/{REPO}/issues/new?labels=data">'
                    'Report what you know</a></p>')

    body.append(_provenance_html(permit, view["source_log"]))
    body.append(_footer(view))

    description = (f'{view["name"]}: which permit applies, quota season, fees, and the '
                   f'dates you need to act. Sourced and dated.')
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": view["name"],
        "url": view["canonical_url"],
    }
    if loc["latitude"] is not None and loc["longitude"] is not None:
        jsonld["geo"] = {"@type": "GeoCoordinates",
                         "latitude": loc["latitude"], "longitude": loc["longitude"]}

    return _page(
        title=f'{view["name"]} Trailhead -- Permit, Quota & Access | Wayproof',
        description=description,
        canonical=view["canonical_url"],
        body="\n".join(body),
        alternates=[("text/markdown", f'/trailheads/{view["slug"]}.md'),
                    ("application/json", f'/trailheads/{view["slug"]}.json')],
        indexable=view["indexable"],
        jsonld=jsonld,
    )


# --------------------------------------------------------------------------
# Trailhead: Markdown (agent surface)
# --------------------------------------------------------------------------

def render_trailhead_markdown(view: dict) -> str:
    permit = view["permit"]
    loc, land = view["location"], view["land"]
    out = [
        f'# {view["name"]} Trailhead',
        "",
        f'Source: Wayproof ({view["canonical_url"]})  ',
        f'Generated: {view["generated"]}  ',
        f'Structured version: {SITE_URL}/trailheads/{view["slug"]}.json',
        "",
        "Planning aid, not a booking guarantee. Verify against the official source "
        "before acting on any date below.",
        "",
    ]

    if view["notes"]:
        out += [view["notes"], ""]

    out += ["## Permit", ""]
    if not permit["known"]:
        out += ["No permit rule resolved for this trailhead yet.", ""]
    else:
        out += [
            f'- Permit: {permit["permit_type"]}',
            f'- Permit group ID: `{permit["permit_group"]}`',
            f'- Agency: {permit["agency"] or "n/a"}',
            f'- Quota required: {"yes" if permit["quota_required"] else "no"}',
        ]
        if permit["quota_season"]:
            out.append(f'- Quota season: {permit["quota_season"]}')
        if permit["fee_notes"]:
            out.append(f'- Fees: {permit["fee_notes"]}')
        if permit["apply_url"]:
            out.append(f'- Apply: {permit["apply_url"]}')
        out.append(f'- Source last updated: {permit["source_last_updated"] or "unknown"}; '
                   f'last verified by Wayproof: {permit["verified_date"] or "not recorded"}')
        out.append("")

        if permit["release_events"]:
            out += ["### Key dates", ""]
            for event in permit["release_events"]:
                line = f'- {event["description"]}'
                if event["notes"]:
                    line += f' ({event["notes"]})'
                out.append(line)
            out.append("")
        elif permit["quota_required"]:
            out += ["### Key dates", "",
                    "No structured release policy for this permit group yet -- exact "
                    "release dates are not computed. Use the reservation method below.", ""]

        if permit["reservation_method"]:
            out += ["### How reservations work", "", permit["reservation_method"], ""]
        if permit["notes"]:
            out += ["### Notes", "", permit["notes"], ""]
        if permit["interagency_note"]:
            out += ["### Travel into neighbouring units", "", permit["interagency_note"], ""]

    regs = view.get("regulations", [])
    if regs:
        out += ["## Rules in force", "",
                "What applies once you hold the permit. A rule whose scope is not "
                "\"this permit\" is inherited from state law or an agency-wide policy and "
                "applies to other permits in the same jurisdiction too.", ""]
        for group in regs:
            out += [f'### {group["label"]}', ""]
            for rule in group["rules"]:
                line = f'- **[{rule["scope"]}]** {rule["summary"]}'
                if rule["detail"]:
                    line += f' {rule["detail"]}'
                if rule["citation"]:
                    line += f' ({rule["citation"]})'
                if rule["source_url"]:
                    line += f' Source: {rule["source_url"]}'
                out.append(line)
            out.append("")

    zones = view.get("zones", {})
    if zones.get("quota_by_zone"):
        out += [f'## Destination zones ({zones["count"]})', "",
                "This permit's quota is assigned per destination zone, not per trailhead. "
                "Booking asks which zone you will spend your FIRST night in; after that night "
                "you may move between zones on the same permit, as long as you exit by the last "
                "date booked. A day hike needs no zone.", "",
                "NOT ASSERTED: which zone serves a given objective. Zone names often match a "
                "lake or peak, but a zone is a mapped boundary and a name is not that boundary. "
                "Do not infer that an objective lies in the similarly-named zone.", ""]
        for zone in zones["entries"]:
            out.append(f'- {zone["label"]}' + (f' -- {zone["notes"]}' if zone["notes"] else ""))
        out.append("")

    if view["approach_exceptions"]:
        out += ["## Route-specific permits from this trailhead", "",
                "These objectives do not inherit the trailhead default.", ""]
        for a in view["approach_exceptions"]:
            group = a["permit_group"] or "not yet established"
            out.append(f'- **{a["peak_name"]}** via {a["approach_name"]} '
                       f'[{a["status"]}] -- permit: `{group}`.'
                       f'{" Source: " + a["source_url"] if a["source_url"] else ""}'
                       f'{" " + a["notes"] if a["notes"] else ""}')
        out.append("")

    out += ["## Location", ""]
    if loc["latitude"] is not None and loc["longitude"] is not None:
        out.append(f'- Coordinates: {loc["latitude"]:.4f}, {loc["longitude"]:.4f}')
    if loc["elevation_ft"]:
        out.append(f'- Elevation: {loc["elevation_ft"]:,.0f} ft')
    for label, value in (("Side of range", loc["side"]),
                         ("Wilderness", land["wilderness_area"]),
                         ("Agency", land["land_agency"]),
                         ("Park", land["park"])):
        if value:
            out.append(f'- {label}: {value}')
    out.append("")

    nearby = view["peaks_nearby"]
    if nearby["count"]:
        out += [f'## Peaks nearest this trailhead ({nearby["count"]})', "",
                "UNVERIFIED: assigned by straight-line proximity, not by a confirmed "
                "approach relationship. Permits attach to the entry point, so a peak "
                "listed here may be climbed from a different trailhead. Do not state "
                "these as this trailhead's approach list.", "",
                ", ".join(nearby["names"]), ""]

    if view["open_questions"]:
        out += ["## Known gaps", ""]
        out += [f'- {q["question"]}' for q in view["open_questions"]]
        out.append("")

    if view["source_log"]:
        out += ["## Verification history", ""]
        for entry in view["source_log"]:
            out.append(f'- {entry["date_checked"]} [{entry["verdict"]}] {entry["summary"]}'
                       f'{" Source: " + entry["source_url"] if entry["source_url"] else ""}')
        out.append("")

    return "\n".join(out)


def render_json(view: dict) -> str:
    return json.dumps(view, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------
# Indexes and site files
# --------------------------------------------------------------------------

def render_trailhead_index_html(views: Sequence[dict]) -> str:
    by_agency: dict = {}
    for view in views:
        by_agency.setdefault(view["land"]["land_agency"] or "Other", []).append(view)

    body = ['<nav class="crumbs"><a href="/">Wayproof</a></nav>',
            '<h1>Trailheads</h1>',
            f'<p class="subtitle">{len(views)} trailheads, each with the permit that '
            'governs entry, its quota season, fees, and the dates you need to act.</p>']
    for agency in sorted(by_agency):
        body.append(f'<h2>{_e(agency)}</h2><ul class="plain">')
        for view in sorted(by_agency[agency], key=lambda v: v["name"]):
            permit = view["permit"]
            label = permit["permit_type"] if permit["known"] else "permit unknown"
            body.append(f'<li><a href="{_e(view["url_path"])}">{_e(view["name"])}</a> '
                        f'<span class="meta">&mdash; {_e(label)}</span></li>')
        body.append('</ul>')
    body.append(_footer())

    return _page(
        title="Sierra Nevada Trailheads -- Permits, Quotas & Access | Wayproof",
        description=("Every trailhead in the Wayproof dataset with the permit that governs "
                     "entry, quota season, fees, and computed release dates."),
        canonical=f"{SITE_URL}/trailheads/",
        body="\n".join(body),
        alternates=[("application/json", "/trailheads/index.json")],
    )


def render_sitemap(urls: Sequence[str]) -> str:
    entries = "\n".join(f"  <url><loc>{_e(u)}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'{entries}\n</urlset>\n')


def render_robots() -> str:
    return ("User-agent: *\n"
            "Allow: /\n\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n")
