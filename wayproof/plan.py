"""Resolve trip logistics for a specific, named set of objectives.

Unlike the experimental geographic clustering pipeline
(:mod:`wayproof.clustering` / :mod:`wayproof.tsp`), this module does
not discover or group objectives -- it assumes the user already knows what
they want to do (e.g. "Mount Williamson and Mount Tyndall") and answers: what
access applies, what permit governs it, when do you need to act, and what
evidence backs the answer?

Almost nothing here is new domain logic. :func:`resolve_plan` looks the named
objectives up, picks their shared trailhead with
:func:`wayproof.approach.choose_trailhead`, wraps them in a single-use
:class:`~wayproof.model.Cluster`, and hands that to
:func:`wayproof.permits.clusters_permit_info` -- reusing the approach
override/uncertainty handling and computable release-rule dates already
built for the clustering pipeline, rather than duplicating any of it.

Current scope, deliberately: a plan's objectives must share a single
trailhead, the same assumption already made everywhere else access is
modeled in this project (a ``Cluster`` has exactly one ``trailhead``).
Objectives that don't share one aren't rejected -- ``resolve_plan`` still
picks its best guess and reports the mismatch as a warning rather than
silently trusting it. A loop or point-to-point traverse with a genuinely
different entry and exit (e.g. an Evolution Loop-style objective) needs an
explicit entry/exit pair, which is a natural additive extension, not
something this module models yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

from .access import ApproachRoute
from .camping import Campground, Campsite
from .model import Cluster, Peak, Trailhead
from .approach import choose_trailhead
from .permits import (
    ClusterPermitInfo,
    PermitRule,
    clusters_permit_info,
    format_permit_entry_body,
)
from .reports import OpenQuestion, open_questions
from .water import WaterSource, WaterSourceLogEntry


@dataclass
class PlanResult:
    """The resolved logistics for a specific, named set of objectives."""

    requested_names: List[str]
    objectives: List[Peak]
    not_found: List[str]
    trip_date: date
    trailhead: Optional[Trailhead]
    trailhead_ambiguous: bool
    permit_entries: List[ClusterPermitInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {
            "requested_objectives": self.requested_names,
            "trip_date": self.trip_date.isoformat(),
            "objectives": [p.to_dict() for p in self.objectives],
        }
        if self.not_found:
            d["not_found"] = self.not_found
        if self.trailhead:
            d["trailhead"] = {
                "name": self.trailhead.name,
                "side": self.trailhead.side,
                "wilderness_area": self.trailhead.wilderness_area,
                "land_agency": self.trailhead.land_agency,
            }
            d["trailhead_ambiguous"] = self.trailhead_ambiguous
        d["permits"] = [
            {
                "agency": e.agency,
                "wilderness_area": e.wilderness_area,
                "permit_type": e.permit_type,
                "status": e.status,
                "fee_notes": e.fee_notes,
                "apply_url": e.apply_url,
                "notes": e.notes,
                "interagency_note": e.interagency_note,
                "peak_note": e.peak_note,
                "approach_name": e.approach_name,
                "approach_status": e.approach_status,
                "source_last_updated": e.source_last_updated,
                "verified_date": e.verified_date,
            }
            for e in self.permit_entries
        ]
        if self.warnings:
            d["warnings"] = self.warnings
        if self.open_questions:
            d["open_questions"] = [
                {"target_file": q.target_file, "target_key": q.target_key,
                 "question": q.question, "context": q.context}
                for q in self.open_questions
            ]
        return d


def resolve_plan(
    objective_names: Sequence[str],
    trip_date: date,
    peaks: Sequence[Peak],
    trailheads: Sequence[Trailhead],
    permits: Dict[str, PermitRule],
    approaches: Optional[Sequence[ApproachRoute]] = None,
    water_sources: Optional[Sequence[WaterSource]] = None,
    water_source_log: Optional[Sequence[WaterSourceLogEntry]] = None,
    campgrounds: Optional[Sequence[Campground]] = None,
    campsites: Optional[Sequence[Campsite]] = None,
    today: Optional[date] = None,
) -> PlanResult:
    """Resolve access and permit logistics for a specific, named set of objectives.

    Objective names are matched case-insensitively against ``peaks``. A name
    that doesn't match anything is reported in ``PlanResult.not_found``
    rather than raising -- a plan for a partially-known trip is more useful
    than none.

    ``water_sources``/``water_source_log``/``campgrounds``/``campsites`` are
    optional; when given, :func:`wayproof.reports.open_questions` derives
    ``PlanResult.open_questions`` -- unconfirmed or missing facts relevant to
    these specific objectives, e.g. "we don't have coordinates for this
    trailhead's water source yet." This is the scavenger-hunt nudge: shown
    exactly when someone is already planning to be at that location.
    """
    by_lower = {p.name.strip().lower(): p for p in peaks}
    objectives: List[Peak] = []
    not_found: List[str] = []
    for name in objective_names:
        peak = by_lower.get(name.strip().lower())
        if peak is None:
            not_found.append(name)
        else:
            objectives.append(peak)

    warnings: List[str] = [
        f"Objective not found in peak data: {name!r}" for name in not_found
    ]

    trailhead: Optional[Trailhead] = None
    trailhead_ambiguous = False
    permit_entries: List[ClusterPermitInfo] = []

    if objectives:
        trailhead = choose_trailhead(objectives, trailheads)

        nearest_names = {
            str(p.meta["nearest_trailhead"]).strip()
            for p in objectives
            if p.meta.get("nearest_trailhead") and str(p.meta["nearest_trailhead"]).strip()
        }
        trailhead_ambiguous = len(nearest_names) > 1
        if trailhead_ambiguous:
            warnings.append(
                "Objectives do not share the same default trailhead "
                f"({', '.join(sorted(nearest_names))}) -- this plan assumes a single "
                f"shared entry point ({trailhead.name if trailhead else 'none found'}); "
                "verify access independently before relying on this."
            )

        if trailhead is None:
            warnings.append("No trailhead data available -- cannot resolve permit logistics.")
        else:
            cluster = Cluster(
                cluster_id=0, peaks=list(objectives),
                trailhead=trailhead.name, trailhead_side=trailhead.side,
            )
            permit_entries = clusters_permit_info(
                [cluster], trailheads, permits, trip_date, today, approaches=approaches,
            )
            if not permit_entries:
                warnings.append(
                    f"No permit data found for trailhead {trailhead.name!r} "
                    f"(permit_group {trailhead.permit_group!r})."
                )

    questions: List[OpenQuestion] = []
    if objectives:
        questions = open_questions(
            peaks=objectives,
            approaches=approaches or [],
            water_sources=water_sources or [],
            water_source_log=water_source_log or [],
            campgrounds=campgrounds or [],
            campsites=campsites or [],
            peak_names=[p.name for p in objectives],
        )

    return PlanResult(
        requested_names=list(objective_names),
        objectives=objectives,
        not_found=not_found,
        trip_date=trip_date,
        trailhead=trailhead,
        trailhead_ambiguous=trailhead_ambiguous,
        permit_entries=permit_entries,
        warnings=warnings,
        open_questions=questions,
    )


def format_plan_summary(result: PlanResult) -> str:
    """Render a :class:`PlanResult` as a human-readable trip summary."""
    lines: List[str] = []
    title = " + ".join(p.name for p in result.objectives) or " + ".join(result.requested_names)
    lines.append(title.upper() if result.objectives else title)
    lines.append(f"Trip date: {result.trip_date:%Y-%m-%d}")
    lines.append("")

    if result.not_found:
        lines.append(f"Not found in peak data: {', '.join(result.not_found)}")
        lines.append("")

    if not result.objectives:
        lines.append("No objectives resolved -- nothing to plan.")
        return "\n".join(lines)

    lines.append("Access")
    if result.trailhead:
        side = f"  ({result.trailhead.side} side)" if result.trailhead.side else ""
        lines.append(f"  Trailhead: {result.trailhead.name}{side}")
    else:
        lines.append("  No trailhead data available.")
    lines.append("")

    lines.append("Permit")
    if result.permit_entries:
        for e in result.permit_entries:
            if e.peak_note:
                lines.append(f"  [{e.peak_note}]")
            lines.extend(format_permit_entry_body(e))
            lines.append("")
    else:
        lines.append("  No permit data resolved for this trailhead.")
        lines.append("")

    lines.append("Known per-objective mileage (official round trip, from source data)")
    any_known = False
    for p in result.objectives:
        mileage = p.meta.get("mileage_rt")
        gain = p.meta.get("gain_ft")
        if mileage:
            any_known = True
            gain_str = f", {int(gain):,} ft gain" if gain else ""
            lines.append(f"  {p.name}: {mileage} mi round trip{gain_str}")
        else:
            lines.append(f"  {p.name}: no official mileage on file")
    if any_known:
        lines.append(
            "  These are each objective's own official round-trip stats from its "
            "standard trailhead -- not a computed combined route. Whether they can "
            "reasonably be linked into one continuous trip is not modeled here; "
            "treat as reference points, not a verified itinerary."
        )
    lines.append("")

    if result.warnings:
        lines.append("Warnings")
        for w in result.warnings:
            lines.append(f"  - {w}")
        lines.append("")

    if result.open_questions:
        lines.append("Help us confirm (if you're going, and you check, please report back)")
        for q in result.open_questions:
            lines.append(f"  - {q.question}")
        lines.append("")

    lines.append(
        "Planning aid, not a booking guarantee -- verify the current rule at the "
        "official source before acting on any date above."
    )
    return "\n".join(lines)
