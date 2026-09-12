"""Channel-agnostic core for the scavenger-hunt data loop: what's unconfirmed
or missing (:func:`open_questions`), and how someone reports back on it
(:func:`submit_report`).

The design goal is that CLI is the only *caller* of this today, and a GitHub
issue template, an MCP tool for Claude, a ChatGPT Action, or a website form
can each become an additional caller later without changing this module --
they'd all just build an ``OpenQuestion``/submit a ``Report`` the same way
``plan.py`` already does. Nothing here assumes a specific channel; ``channel``
on :class:`Report` is just metadata about where a submission came from.

``open_questions`` deliberately *derives* its list from confidence signals
already present in the domain data (an ``unconfirmed`` approach status, a
water source with no coordinates, two log entries that disagree, a note
containing "approximate") rather than from a hand-authored, separately
maintained list -- a static list drifts out of sync with the data it's
describing; a derived one can't.

Peak-scoped filtering (``peak_names``) is intentionally conservative: it only
includes gaps this module can link to a requested peak with real confidence
(an approach row's own ``peak_name``, a peak's own coordinate flag, or a
water source whose ``location`` matches that peak's ``nearest_trailhead``).
Campground- and campsite-level gaps aren't peak-filterable yet -- there's no
reliable link from a campground's ``park`` field to a specific peak's
trailhead (they use different naming granularity today), and a wrong-looking
"this is relevant to your trip" claim is worse than omitting it. Those gaps
still surface in the unfiltered (``peak_names=None``) view. See the "Known
follow-ups" note this leaves in DATA_LICENSE.md.

``submit_report`` writes to ``data/pending_reports.csv``, an intake queue
deliberately separate from the resolved domain ledgers (``water_source_log.csv``
etc.) -- a submission is a claim to review, not yet a fact. Accepting one is
still a manual step: the maintainer transcribes it into the relevant CSV,
citing the report ID, then calls :func:`resolve_report` to close it out.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from .access import ApproachRoute, UNCONFIRMED
from .camping import Campground, Campsite
from .park_access import ParkAccess
from .model import Peak, Trailhead
from .permits import PermitRule
from .regulations import PERMIT_GROUP as REG_PERMIT_GROUP, Regulation
from .release_policy import OFF_SEASON
from .timed_entry import TimedEntryPolicy
from .water import WaterSource, WaterSourceLogEntry, log_by_source

_UNCERTAIN_NOTE_MARKERS = ("approximate", "unconfirmed", "not a confirmed", "not found")
_CONFLICT_STATUS_MARKERS = ("contradict", "unclear")

_VALID_CONFIDENCE = {"firsthand", "official_source", "told_by_staff", "secondhand"}
_VALID_STATUS = {"pending", "accepted", "rejected", "needs-more-evidence"}

_REPORT_FIELDS = [
    "report_id", "submitted_date", "target_file", "target_key", "claim",
    "evidence", "confidence", "channel", "status", "resolution_notes",
]


@dataclass
class OpenQuestion:
    """A single, derived gap: something unconfirmed, missing, or conflicting
    in the current data."""

    target_file: str
    target_key: str
    question: str
    context: str = ""


@dataclass
class Report:
    """One row of ``data/pending_reports.csv``: a claim awaiting review."""

    report_id: str
    submitted_date: str
    target_file: str
    target_key: str
    claim: str
    evidence: str = ""
    confidence: str = "firsthand"
    channel: str = "cli"
    status: str = "pending"
    resolution_notes: str = ""


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _matches_peak_names(name: str, peak_names_lower: set) -> bool:
    return name.strip().lower() in peak_names_lower


def open_questions(
    peaks: Sequence[Peak] = (),
    approaches: Sequence[ApproachRoute] = (),
    water_sources: Sequence[WaterSource] = (),
    water_source_log: Sequence[WaterSourceLogEntry] = (),
    campgrounds: Sequence[Campground] = (),
    campsites: Sequence[Campsite] = (),
    timed_entry: Sequence[TimedEntryPolicy] = (),
    trailheads: Sequence[Trailhead] = (),
    park_access: Sequence[ParkAccess] = (),
    permits: Sequence[PermitRule] = (),
    regulations: Sequence[Regulation] = (),
    peak_names: Optional[Sequence[str]] = None,
) -> List[OpenQuestion]:
    """Derive the current list of unconfirmed/missing/conflicting facts.

    With ``peak_names`` given, only gaps confidently linkable to one of those
    peaks are returned (see the module docstring for exactly which kinds
    qualify). With ``peak_names=None``, every gap this function knows how to
    detect is returned -- the full backlog view.

    Campground/campsite/park-access gaps are peak-filterable via
    ``Trailhead.park`` (pass ``trailheads`` to enable this) -- a trailhead's
    specific park/preserve unit, distinct from its ``wilderness_area``. Omit
    ``trailheads`` and these three kinds fall back to appearing only in the
    unfiltered (global) view, same as before this field existed.
    """
    questions: List[OpenQuestion] = []
    peak_names_lower = {n.strip().lower() for n in peak_names} if peak_names is not None else None

    relevant_trailheads: set = set()
    relevant_parks: set = set()
    if peak_names_lower is not None:
        for p in peaks:
            if _matches_peak_names(p.name, peak_names_lower):
                th = p.meta.get("nearest_trailhead")
                if th and str(th).strip():
                    relevant_trailheads.add(str(th).strip())
        by_trailhead_name = {t.name: t for t in trailheads}
        for th_name in relevant_trailheads:
            th = by_trailhead_name.get(th_name)
            if th and th.park:
                relevant_parks.add(th.park)

    # -- Approaches with unconfirmed permit status: always peak-filterable. --
    for r in approaches:
        if r.status != UNCONFIRMED:
            continue
        if peak_names_lower is not None and not _matches_peak_names(r.peak_name, peak_names_lower):
            continue
        questions.append(OpenQuestion(
            target_file="data/approaches.csv",
            target_key=f"{r.peak_name} / {r.approach_name}",
            question=(f"Which permit actually governs {r.peak_name}'s approach via "
                      f"{r.approach_name}? Not yet confirmed against a source."),
            context=r.peak_name,
        ))

    # -- A peak's own coordinate source flagged as unconfirmed or Tier C. --
    for p in peaks:
        if peak_names_lower is not None and not _matches_peak_names(p.name, peak_names_lower):
            continue
        coord_source = str(p.meta.get("coord_source", "") or "")
        if "unconfirmed" in coord_source.lower():
            questions.append(OpenQuestion(
                target_file="data/peaks.csv",
                target_key=p.name,
                question=(f"{p.name}'s coordinates are sourced to {coord_source!r}, not yet "
                          "an independently confirmed GNIS feature ID."),
                context=p.name,
            ))
        elif coord_source.strip().lower() == "peakbagger":
            questions.append(OpenQuestion(
                target_file="data/peaks.csv",
                target_key=p.name,
                question=(f"{p.name}'s coordinates come from peakbagger.com (Tier C), not "
                          "GNIS -- not yet independently re-verified against a Tier A source."),
                context=p.name,
            ))

    # -- A peak's own notes flagging an unresolved data-quality issue, e.g. --
    # a duplicate-name tie-break where the underlying value conflict is
    # still unconfirmed. Peak-filterable, since these are direct peak facts.
    for p in peaks:
        if peak_names_lower is not None and not _matches_peak_names(p.name, peak_names_lower):
            continue
        note = str(p.meta.get("notes", "") or "")
        if note and any(m in note.lower() for m in _UNCERTAIN_NOTE_MARKERS):
            questions.append(OpenQuestion(
                target_file="data/peaks.csv",
                target_key=p.name,
                question=f"{p.name}: {note}",
                context=p.name,
            ))

    # -- Water sources: missing coordinates (peak-filterable via trailhead link). --
    log_by_name = log_by_source(water_source_log)
    for w in water_sources:
        is_relevant = (
            peak_names_lower is None
            or (w.location and w.location.strip() in relevant_trailheads)
        )
        if not is_relevant:
            continue
        if w.latitude is None or w.longitude is None:
            questions.append(OpenQuestion(
                target_file="data/water_sources.csv",
                target_key=w.name,
                question=f"We don't have coordinates for {w.name} yet.",
                context=w.location,
            ))

    # -- Water sources: no check on file, or the two most recent disagree. --
    # Global view only -- these aren't reliably linkable to one peak's trailhead
    # (most sources here are keyed to a campground along a shared corridor
    # trail, not to a single peak's own trailhead).
    if peak_names_lower is None:
        for w in water_sources:
            entries = log_by_name.get(w.name, [])
            if not entries:
                questions.append(OpenQuestion(
                    target_file="data/water_source_log.csv",
                    target_key=w.name,
                    question=f"No availability check on file for {w.name} -- is it running?",
                    context=w.location,
                ))
            elif any(m in entries[-1].observed_status.lower() for m in _CONFLICT_STATUS_MARKERS):
                questions.append(OpenQuestion(
                    target_file="data/water_source_log.csv",
                    target_key=w.name,
                    question=(f"Reports on {w.name}'s availability disagree "
                              "-- needs a fresh, independent check."),
                    context=w.location,
                ))

    # -- Campgrounds/campsites/park-access: peak-filterable via Trailhead.park
    # when `trailheads` was given; otherwise (or when no park link is known
    # for the requested peaks) they only appear in the unfiltered view. --
    campground_park_by_name = {c.name: c.park for c in campgrounds}
    show_by_park = peak_names_lower is None or bool(relevant_parks)

    def _park_is_relevant(park: str) -> bool:
        return peak_names_lower is None or (park and park in relevant_parks)

    if show_by_park:
        # -- Campsites missing both proximity fields. --
        for s in campsites:
            if not _park_is_relevant(campground_park_by_name.get(s.campground, "")):
                continue
            if not s.water_proximity and not s.restroom_proximity:
                questions.append(OpenQuestion(
                    target_file="data/campsites.csv",
                    target_key=s.name,
                    question=f"We don't know {s.name}'s proximity to water or a restroom.",
                    context=s.campground,
                ))

        # -- Trailhead/campground notes flagging their own uncertainty. --
        for c in campgrounds:
            if not _park_is_relevant(c.park):
                continue
            for field_name, text in (("notes", c.notes), ("nightly_entry_cutoff", c.nightly_entry_cutoff)):
                if text and any(m in text.lower() for m in _UNCERTAIN_NOTE_MARKERS):
                    questions.append(OpenQuestion(
                        target_file="data/campgrounds.csv",
                        target_key=f"{c.name}.{field_name}",
                        question=f"{c.name}'s {field_name.replace('_', ' ')} is flagged uncertain: {text}",
                        context=c.park,
                    ))

        # -- Park-access rows with a lower-confidence field (e.g. a fee
        # exemption confirmed only verbally, not in writing). --
        for pa in park_access:
            if not _park_is_relevant(pa.park):
                continue
            for field_name, text in (("fee_exemptions", pa.fee_exemptions), ("notes", pa.notes)):
                if text and "verbal" in text.lower():
                    questions.append(OpenQuestion(
                        target_file="data/park_access.csv",
                        target_key=f"{pa.park}.{field_name}",
                        question=f"{pa.park}'s {field_name.replace('_', ' ')} is only verbally confirmed, not published: {text}",
                        context=pa.park,
                    ))
                    break  # one question per park-access row is enough

    if peak_names_lower is None:
        # -- Permit groups with no local fire rule on file. --
        # The California Campfire Permit is inherited by every group in the
        # state, and on its own it reads like permission. It isn't: CAL FIRE's
        # own guidance says local rules override, and Sierra wildernesses
        # commonly ban fires outright or above an elevation. A group with the
        # statewide rule and nothing local is therefore silent on the question
        # a reader will actually ask, and silence next to an inherited permit
        # rule is worse than a stated gap.
        fire_rules_by_group = {
            r.scope_value for r in regulations
            if r.category == "fire" and r.scope_type == REG_PERMIT_GROUP
        }
        # Only ask where a broader fire rule is actually being inherited: the
        # gap is that an inherited permit requirement reads as permission with
        # nothing local beside it. With no such rule in play there's nothing
        # to misread, and nothing to ask about.
        inherited_fire = {
            r.scope_value for r in regulations
            if r.category == "fire" and r.scope_type != REG_PERMIT_GROUP
        }
        for rule in permits:
            if not ({rule.jurisdiction, rule.agency} & inherited_fire):
                continue
            if rule.permit_group in fire_rules_by_group:
                continue
            # Transitional: several groups still carry their fire rule as prose
            # in notes rather than as a structured regulation. Those aren't
            # silent, just unmigrated, so don't report them as unknown.
            prose = f"{rule.notes} {rule.reservation_method}".lower()
            if "campfire" in prose:
                continue
            questions.append(OpenQuestion(
                target_file="data/regulations.csv",
                target_key=f"{rule.permit_group} (fire)",
                question=(f"Are campfires actually allowed in {rule.permit_group}, and up to "
                          "what elevation? Only the statewide California Campfire Permit rule "
                          "applies here so far, which is a precondition rather than permission "
                          "-- no local restriction is on file either way."),
                context=rule.permit_group,
            ))

        # -- Quota'd permit groups with no off-season release phase. --
        # permit_status() falls back to asserting the off-season permit is
        # "free/self-issue, no reservation" for these. That assumption has
        # now been caught wrong twice against a real source (Whitney Zone,
        # then Desolation -- both actually still require an online booking
        # out of season), so every remaining group carrying it is a claim
        # this project is making without evidence, not a safe default.
        for rule in permits:
            if not rule.quota_required or not rule.release_phases:
                continue
            if any(p.season == OFF_SEASON for p in rule.release_phases):
                continue
            questions.append(OpenQuestion(
                target_file="data/release_policies.csv",
                target_key=f"{rule.permit_group} (off-season)",
                question=(f"How is a {rule.permit_group} permit actually obtained outside its "
                          "quota season? With no off-season phase on file we currently claim "
                          "it's free/self-issue with no reservation -- an assumption already "
                          "found wrong for two other groups."),
                context=rule.permit_group,
            ))

        # -- Timed-entry rows sourced to secondary/aggregator coverage rather
        # than the year's own official NPS announcement. Always global --
        # no trailhead in this dataset currently sets `park` to a park unit
        # that also appears in data/timed_entry.csv (e.g. Yosemite's own
        # trailheads still use the older Sierra permit model, not `park`).
        for t in timed_entry:
            if t.notes and any(m in t.notes.lower() for m in ("secondary", "aggregator")):
                questions.append(OpenQuestion(
                    target_file="data/timed_entry.csv",
                    target_key=f"{t.park} {t.year}",
                    question=(f"{t.park}'s {t.year} timed-entry record is secondary-sourced, "
                              "not yet confirmed against that year's original NPS announcement."),
                    context=t.park,
                ))

    return questions


def format_open_questions(questions: Sequence[OpenQuestion]) -> str:
    """Render the global backlog view: every open question, grouped by
    target file so related gaps (e.g. everything in data/peaks.csv) sit
    together."""
    if not questions:
        return "No open questions on file."
    by_file: dict[str, List[OpenQuestion]] = {}
    for q in questions:
        by_file.setdefault(q.target_file, []).append(q)

    lines: List[str] = [f"{len(questions)} open question(s) across {len(by_file)} file(s)", ""]
    for target_file in sorted(by_file):
        lines.append(target_file)
        for q in by_file[target_file]:
            lines.append(f"  [{q.target_key}] {q.question}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_pending_reports(reports: Sequence[Report]) -> str:
    """Render the pending-review queue: submitted claims awaiting a
    maintainer's decision, separate from `open_questions()`'s derived gaps
    -- one is "please go check this," the other is "someone already told us
    something, still needs review." """
    pending = [r for r in reports if r.status == "pending"]
    if not pending:
        return "No pending reports."
    lines: List[str] = [f"{len(pending)} pending report(s) awaiting review", ""]
    for r in pending:
        lines.append(f"[{r.report_id}] {r.target_file} / {r.target_key}")
        lines.append(f"  Claim ({r.confidence}, via {r.channel}, {r.submitted_date}): {r.claim}")
        if r.evidence:
            lines.append(f"  Evidence: {r.evidence}")
        lines.append("")
    return "\n".join(lines).rstrip()


def submit_report(
    target_file: str,
    target_key: str,
    claim: str,
    evidence: str = "",
    confidence: str = "firsthand",
    channel: str = "cli",
    path: str | Path = "data/pending_reports.csv",
) -> Report:
    """Append a new report to the pending-review queue and return it."""
    if confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"Invalid confidence {confidence!r}; expected one of {sorted(_VALID_CONFIDENCE)}")
    path = Path(path)
    existing = pending_reports(path)
    report = Report(
        report_id=f"R{len(existing) + 1:04d}",
        submitted_date=date.today().isoformat(),
        target_file=target_file,
        target_key=target_key,
        claim=claim,
        evidence=evidence,
        confidence=confidence,
        channel=channel,
        status="pending",
    )
    row = pd.DataFrame([asdict(report)], columns=_REPORT_FIELDS)
    row.to_csv(path, mode="a", header=not path.exists(), index=False)
    return report


def pending_reports(path: str | Path = "data/pending_reports.csv") -> List[Report]:
    """Load every report on file, oldest first. Empty list if none exist yet."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [
        Report(**{f: _str_field(row, f) for f in _REPORT_FIELDS})
        for _, row in df.iterrows()
        if _str_field(row, "report_id")
    ]


def resolve_report(
    report_id: str,
    status: str,
    resolution_notes: str = "",
    path: str | Path = "data/pending_reports.csv",
) -> Report:
    """Mark a report resolved (accepted/rejected/needs-more-evidence).

    This only updates the queue entry itself -- actually applying an accepted
    report to the relevant domain CSV (e.g. adding a water_source_log.csv
    row) is still a separate, deliberate step, not something this function
    does automatically.
    """
    if status not in _VALID_STATUS:
        raise ValueError(f"Invalid status {status!r}; expected one of {sorted(_VALID_STATUS)}")
    reports = pending_reports(path)
    match = next((r for r in reports if r.report_id == report_id), None)
    if match is None:
        raise ValueError(f"No report found with id {report_id!r}")
    match.status = status
    match.resolution_notes = resolution_notes

    path = Path(path)
    df = pd.DataFrame([asdict(r) for r in reports], columns=_REPORT_FIELDS)
    df.to_csv(path, index=False)
    return match
