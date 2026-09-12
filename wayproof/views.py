"""View models for wayproof.dev's generated pages.

A "view" here is a plain dict: everything one published page asserts, resolved
from the domain data and nothing else. :mod:`wayproof.render` turns a view into
HTML, Markdown, or JSON.

The split matters more than usual for this project. Every page ships in three
representations (human HTML, agent Markdown, structured JSON), and a site whose
whole claim is "these facts are sourced and consistent" cannot afford the agent
surface to say something the human one doesn't. Resolving once into a dict and
rendering three times makes disagreement impossible by construction, rather
than by discipline.

Trailhead views are deliberately **permit-led**. A trailhead's authoritative,
sourced content is its access and permit rule -- the agency, the quota season,
the release mechanics, the fees. Its peak list is not: ``nearest_trailhead``
in ``data/peaks.csv`` is a *geometric* assignment computed by
``scripts/assign_trailheads.py``, not a curated approach relationship, and
permits attach to where you *enter* rather than to whatever summit happens to
be closest (a JMT hiker entering at Happy Isles carries that permit past peaks
whose nearest road is hundreds of miles of trail away). So proximity-derived
peaks appear only as an explicitly labelled, secondary signal, while
``data/approaches.csv``'s sourced rows -- the ones that actually know which
permit governs a named route -- are surfaced as first-class facts.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from .access import ApproachRoute
from .model import Peak, Trailhead
from .permit_zones import PermitZone
from .provenance import Source
from .regulations import Regulation, group_by_category, regulations_for
from .evidence import evidence_for
from .permits import PermitRule, SourceLogEntry
from .release_policy import CONTACT_REQUIRED, LOTTERY_ANNUAL, WALKUP, ReleasePhase
from .reports import OpenQuestion

SITE_URL = "https://wayproof.dev"
REPO = "asideofkorn/wayproof"


def slugify(name: str) -> str:
    """URL slug for a page. Stable: changing one orphans a published URL."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")


def _format_month_day(month_day: Optional[tuple]) -> str:
    if not month_day:
        return ""
    return f"{date(2001, month_day[0], month_day[1]):%b %-d}"


def _format_quota_season(rule: PermitRule) -> str:
    start = _format_month_day(rule.quota_season_start)
    end = _format_month_day(rule.quota_season_end)
    if start and end:
        return f"{start} - {end}"
    if rule.quota_required:
        return "Year-round"
    return ""


def next_occurrence(month_day: tuple, today: date) -> date:
    """The next calendar occurrence of a (month, day), today included."""
    month, day = month_day
    candidate = date(today.year, month, day)
    if candidate < today:
        candidate = date(today.year + 1, month, day)
    return candidate


def _phase_event(phase: ReleasePhase, today: date) -> dict:
    """One upcoming dated event, or the honest absence of one.

    Two genuinely different shapes live here. A fixed-calendar phase (a
    lottery window) has an absolute next date. A rolling-offset phase does
    not -- it opens N days before *your* entry date, so the useful framing is
    the inverse: what entry date is opening for booking today. Neither is
    invented: a phase whose source gives no offset and no fixed date resolves
    to no date at all (see release_policy's module docstring).
    """
    event = {
        "label": phase.label,
        "mechanism": phase.mechanism,
        "season": phase.season,
        "allocation_pct": phase.allocation_pct,
        "time_of_day": phase.time_of_day,
        "timezone": phase.timezone,
        "notes": phase.notes,
        "date": None,
        "offset_days": phase.offset_days,
        "entry_date_opening_today": None,
    }

    if phase.fixed_month_day:
        event["date"] = next_occurrence(phase.fixed_month_day, today).isoformat()
    elif phase.offset_days is not None:
        event["entry_date_opening_today"] = (today + timedelta(days=phase.offset_days)).isoformat()

    return event


def _describe_event(event: dict) -> str:
    """A single self-contained sentence for one upcoming event.

    Self-contained matters: these are read one line at a time, and a
    season-scoped phase listed next to an unscoped one is actively
    misleading without its scope attached (Whitney Zone's off-season
    14-day reservation is not a fallback for its in-season lottery).
    """
    parts = []
    if event["season"]:
        parts.append(f"{event['season'].replace('_', ' ').capitalize()} only:")
    if event["label"]:
        parts.append(event["label"].replace("_", " ").capitalize())
    if event["allocation_pct"]:
        parts.append(f"({event['allocation_pct']:g}% of the quota)")
    prefix = " ".join(parts)

    at_time = ""
    if event["time_of_day"]:
        at_time = f" at {event['time_of_day']}"
        if event["timezone"]:
            at_time += f" {event['timezone']}"

    if event["mechanism"] == WALKUP:
        body = "issued in person, day-of, first-come -- no advance reservation"
    elif event["mechanism"] == CONTACT_REQUIRED:
        body = "not self-issue -- contact the agency directly to arrange a permit"
    elif event["date"]:
        verb = "next" if event["mechanism"] == LOTTERY_ANNUAL else "opens next"
        body = f"{verb} on {event['date']}{at_time}"
    elif event["entry_date_opening_today"]:
        body = (f"opens {event['offset_days']} days before your entry date{at_time} "
                f"-- booking today covers entry around {event['entry_date_opening_today']}")
    else:
        body = "no release date published by the source"

    if prefix:
        return f"{prefix} -- {body}.".replace(" -- --", " --")
    return f"{body[0].upper()}{body[1:]}."


def _permit_block(rule: Optional[PermitRule], today: date) -> dict:
    if rule is None:
        return {"known": False}

    events = [_phase_event(p, today) for p in rule.release_phases]
    for event in events:
        event["description"] = _describe_event(event)

    return {
        "known": True,
        "permit_group": rule.permit_group,
        "agency": rule.agency,
        "permit_type": rule.permit_type,
        "quota_required": rule.quota_required,
        "quota_season": _format_quota_season(rule),
        "reservation_method": rule.reservation_method,
        "fee_notes": rule.fee_notes,
        "apply_url": rule.apply_url,
        "notes": rule.notes,
        "interagency_note": rule.interagency_note,
        # What this permit does NOT admit you to. Rendered high on the
        # page, because holding the wrong permit is discovered at the
        # trailhead and cannot be fixed there.
        "excludes": rule.excludes,
        "source_last_updated": rule.source_last_updated,
        "verified_date": rule.verified_date,
        "release_events": events,
        # False means this group still uses permits.py's coarser fallback
        # rather than data/release_policies.csv -- worth saying out loud
        # rather than presenting a vaguer answer as an equally precise one.
        "has_computable_release": bool(rule.release_phases),
    }


def trailhead_view(
    trailhead: Trailhead,
    rule: Optional[PermitRule],
    approaches: Sequence[ApproachRoute] = (),
    peaks: Sequence[Peak] = (),
    source_log: Sequence[SourceLogEntry] = (),
    sources: Sequence[Source] = (),
    zones: Optional[Dict[str, List[PermitZone]]] = None,
    regulations: Sequence[Regulation] = (),
    questions: Sequence[OpenQuestion] = (),
    today: Optional[date] = None,
) -> dict:
    """Everything wayproof.dev publishes about one trailhead.

    ``approaches``, ``peaks``, ``source_log`` and ``questions`` are the full
    datasets; this filters each to what actually concerns this trailhead.
    """
    today = today or date.today()
    slug = slugify(trailhead.name)

    here = [a for a in approaches if a.trailhead == trailhead.name]
    nearby = [p for p in peaks
              if str(p.meta.get("nearest_trailhead", "")).strip() == trailhead.name]
    contexts = {trailhead.name, trailhead.park} - {""}
    relevant_questions = [q for q in questions if q.context in contexts]

    permit = _permit_block(rule, today)
    log = [entry for entry in source_log
           if rule is not None and entry.permit_group == rule.permit_group]
    zone_list = (zones or {}).get(rule.permit_group, []) if rule is not None else []
    applicable = regulations_for(
        regulations,
        permit_group=rule.permit_group if rule else "",
        agency=rule.agency_ids if rule else (),
        jurisdiction=rule.jurisdiction if rule else "",
        wilderness=rule.wilderness_area if rule else "",
    )

    return {
        "type": "trailhead",
        "slug": slug,
        "name": trailhead.name,
        "url_path": f"/trailheads/{slug}/",
        "canonical_url": f"{SITE_URL}/trailheads/{slug}/",
        "title": f"{trailhead.name} Trailhead -- permit, quota, and access",
        "location": {
            "latitude": trailhead.latitude,
            "longitude": trailhead.longitude,
            "elevation_ft": trailhead.elevation_ft,
            "side": trailhead.side,
        },
        "land": {
            "wilderness_area": trailhead.wilderness_area,
            "land_agency": trailhead.land_agency,
            "park": trailhead.park,
        },
        "notes": trailhead.notes,
        "permit": permit,
        # Sourced, route-specific permit relationships: the cases where this
        # trailhead's default permit is known (or suspected) to be wrong for a
        # particular objective. First-class facts, unlike `peaks_nearby`.
        "approach_exceptions": [
            {
                "peak_name": a.peak_name,
                "approach_name": a.approach_name,
                "permit_group": a.permit_group,
                "status": a.status,
                "source_url": a.source_url,
                "verified_date": a.verified_date,
                "notes": a.notes,
            }
            for a in here
        ],
        # What you may and may not do once you hold the permit, resolved
        # across all three scopes (this permit, its agency, its state) so a
        # statewide rule is inherited rather than copied per group.
        "regulations": [
            {
                "label": label,
                "rules": [
                    {"id": r.regulation_id, "summary": r.summary, "detail": r.detail,
                     "citation": r.citation, "source_url": r.source_url,
                     "scope": r.scope_label, "inherited": r.inherited,
                     "evidence": evidence_for(r.log_entry_ids, source_log, sources).as_dict()}
                    for r in items
                ],
            }
            for label, items in group_by_category(applicable)
        ],
        # Bookable zones, for the minority of permit groups whose quota
        # attaches to a destination rather than to this entry point. Which
        # zone serves a given objective is deliberately NOT asserted -- a
        # zone is a mapped boundary, and its name is not that boundary.
        "zones": {
            "quota_by_zone": bool(zone_list),
            "count": sum(1 for z in zone_list if z.zone_code is not None),
            "entries": [
                {"code": z.zone_code, "name": z.zone_name, "label": z.label,
                 "type": z.zone_type, "notes": z.notes}
                for z in zone_list
            ],
        },
        # Deliberately secondary and labelled: a geometric assignment, not a
        # curated approach list. See this module's docstring.
        "peaks_nearby": {
            "basis": "computed-proximity",
            "verified": False,
            "count": len(nearby),
            "names": sorted(p.name for p in nearby),
        },
        "open_questions": [
            {"target_file": q.target_file, "target_key": q.target_key, "question": q.question}
            for q in relevant_questions
        ],
        # Where this permit row's current state came from, walkable forward
        # to the sources and any argument still open against them.
        "evidence": (evidence_for(rule.log_entry_ids, source_log, sources).as_dict()
                     if rule is not None else evidence_for("", source_log, sources).as_dict()),
        "source_log": [
            {
                "date_checked": e.date_checked,
                "source_url": e.source_url,
                "source_last_updated": e.source_last_updated,
                "method": e.method,
                "verdict": e.verdict,
                "summary": e.summary,
                "entry_id": e.entry_id,
                "conflict_id": e.conflict_id,
                "conflict_kind": e.conflict_kind,
            }
            for e in log
        ],
        "generated": today.isoformat(),
        # Everything with a resolved permit rule carries real, sourced content
        # worth indexing -- including `none`, whose "no wilderness permit, but
        # you still need a campfire permit for a stove" answer is exactly the
        # thing people get wrong.
        "indexable": permit["known"],
    }


def trailhead_views(
    trailheads: Sequence[Trailhead],
    permits: Dict[str, PermitRule],
    approaches: Sequence[ApproachRoute] = (),
    peaks: Sequence[Peak] = (),
    source_log: Sequence[SourceLogEntry] = (),
    sources: Sequence[Source] = (),
    zones: Optional[Dict[str, List[PermitZone]]] = None,
    regulations: Sequence[Regulation] = (),
    questions: Sequence[OpenQuestion] = (),
    today: Optional[date] = None,
) -> List[dict]:
    """Build every trailhead view, sorted by name.

    Raises on a slug collision rather than silently letting one published
    page overwrite another.
    """
    views = [
        trailhead_view(t, permits.get(t.permit_group), approaches=approaches, peaks=peaks,
                       source_log=source_log, sources=sources,
                       zones=zones, regulations=regulations,
                       questions=questions, today=today)
        for t in sorted(trailheads, key=lambda t: t.name)
    ]
    seen: Dict[str, str] = {}
    for view in views:
        if view["slug"] in seen:
            raise ValueError(
                f"Slug collision: {view['name']!r} and {seen[view['slug']]!r} "
                f"both slugify to {view['slug']!r}"
            )
        seen[view["slug"]] = view["name"]
    return views
