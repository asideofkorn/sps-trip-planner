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
from .approach import EntryConflict, choose_trailhead, entry_conflicts
from .park_access import ParkAccess
from .permits import (
    ClusterPermitInfo,
    PermitRule,
    clusters_permit_info,
    format_permit_entry_body,
)
from .reports import OpenQuestion, open_questions
from .water import WaterSource, WaterSourceLogEntry, latest_status_by_source


@dataclass
class FacilitiesInfo:
    """What IS known about the resolved trailhead's nearby facilities --
    the counterpart to ``PlanResult.open_questions``, which is what isn't.

    Linked to the trailhead via ``Trailhead.park`` (campgrounds/park_access)
    and exact ``WaterSource.location`` match (water sources) -- the same
    conservative linking :func:`wayproof.reports.open_questions` uses, so a
    trailhead with no known ``park`` (most Sierra trailheads today) simply
    gets no campground/park-access facts here, rather than a guessed one.
    """

    water_sources: List[WaterSource] = field(default_factory=list)
    water_status: Dict[str, WaterSourceLogEntry] = field(default_factory=dict)
    campgrounds: List[Campground] = field(default_factory=list)
    campsites: List[Campsite] = field(default_factory=list)
    park_access: Optional[ParkAccess] = None


@dataclass
class PlanResult:
    """The resolved logistics for a specific, named set of objectives."""

    requested_names: List[str]
    objectives: List[Peak]
    not_found: List[str]
    trip_date: date
    trailhead: Optional[Trailhead]
    trailhead_ambiguous: bool
    entry_conflicts: List[EntryConflict] = field(default_factory=list)
    """Objectives whose sourced route contradicts the trailhead geometry chose.

    Non-empty means this project cannot say which entry point governs, so the
    permit below is a candidate rather than an answer.
    """
    permit_entries: List[ClusterPermitInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    facilities: Optional[FacilitiesInfo] = None

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
            # The JSON must carry this too. The site already had a bug where
            # the machine surface said "unverified" and the human surfaces
            # said nothing; the reverse would be worse, since an agent acting
            # on this cannot see the warning text.
            d["entry_point_resolved"] = not self.entry_conflicts
            if self.entry_conflicts:
                d["entry_conflicts"] = [
                    {"peak": c.peak_name, "sourced_route": c.sourced_route,
                     "computed_trailhead": c.computed_trailhead}
                    for c in self.entry_conflicts
                ]
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
        if self.facilities:
            fac = self.facilities
            facilities_d: dict = {}
            if fac.water_sources:
                facilities_d["water_sources"] = [
                    {
                        "name": w.name,
                        "type": w.type,
                        "potable": w.potable,
                        "status": (fac.water_status[w.name].observed_status
                                   if w.name in fac.water_status else None),
                        "status_checked_date": (fac.water_status[w.name].checked_date
                                                 if w.name in fac.water_status else None),
                        "status_source": (fac.water_status[w.name].source
                                          if w.name in fac.water_status else None),
                    }
                    for w in fac.water_sources
                ]
            if fac.campgrounds:
                facilities_d["campgrounds"] = [
                    {
                        "name": c.name,
                        "reservation_method": c.reservation_method,
                        "reservation_contact": c.reservation_contact,
                        "fee_notes": c.fee_notes,
                        "nightly_entry_cutoff": c.nightly_entry_cutoff,
                        "campsites": [
                            {"name": s.name, "capacity": s.capacity,
                             "water_proximity": s.water_proximity,
                             "restroom_proximity": s.restroom_proximity}
                            for s in fac.campsites if s.campground == c.name
                        ],
                    }
                    for c in fac.campgrounds
                ]
            if fac.park_access:
                pa = fac.park_access
                facilities_d["park_access"] = {
                    "park": pa.park,
                    "entrance_fee": pa.entrance_fee,
                    "fee_conditions": pa.fee_conditions,
                    "fee_exemptions": pa.fee_exemptions,
                    "gate_open": pa.gate_open,
                    "gate_close": pa.gate_close,
                    "gate_hours_conditions": pa.gate_hours_conditions,
                }
            if facilities_d:
                d["facilities"] = facilities_d
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
    park_access: Optional[Sequence[ParkAccess]] = None,
    today: Optional[date] = None,
) -> PlanResult:
    """Resolve access and permit logistics for a specific, named set of objectives.

    Objective names are matched case-insensitively against ``peaks``. A name
    that doesn't match anything is reported in ``PlanResult.not_found``
    rather than raising -- a plan for a partially-known trip is more useful
    than none.

    ``water_sources``/``water_source_log``/``campgrounds``/``campsites``/
    ``park_access`` are optional; when given, they feed two different things:
    :func:`wayproof.reports.open_questions` derives ``PlanResult.open_questions``
    -- unconfirmed or missing facts relevant to these specific objectives,
    e.g. "we don't have coordinates for this trailhead's water source yet"
    (the scavenger-hunt nudge, shown exactly when someone is already
    planning to be at that location) -- while ``PlanResult.facilities``
    holds what IS already known and confirmed (a water source's last-checked
    status, a nearby campground's reservation method, the park's entrance
    fee), linked to the resolved trailhead the same conservative way.
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
    conflicts: List[EntryConflict] = []
    permit_entries: List[ClusterPermitInfo] = []

    if objectives:
        trailhead = choose_trailhead(objectives, trailheads)

        nearest_names = {
            str(p.meta["nearest_trailhead"]).strip()
            for p in objectives
            if p.meta.get("nearest_trailhead") and str(p.meta["nearest_trailhead"]).strip()
        }
        # A single objective whose OWN sourced route contradicts the geometry
        # used to be silent: `trailhead_ambiguous` only fires when objectives
        # disagree with each other. That silence is what let this tool answer
        # "Mineral King, SEKI permit" for a peak its own data routes over
        # Shepherd Pass on the far side of the crest.
        conflicts = entry_conflicts(objectives, trailhead)
        for conflict in conflicts:
            warnings.append(
                f"UNRESOLVED ENTRY POINT -- {conflict} This project has no sourced row "
                "linking this objective to an entry point, so the permit below follows "
                "geometry and is NOT verified. Confirm the approach before booking."
            )

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
            trailheads=trailheads,
            park_access=park_access or [],
            peak_names=[p.name for p in objectives],
        )

    facilities: Optional[FacilitiesInfo] = None
    if trailhead is not None:
        ws = [w for w in (water_sources or [])
              if w.location and w.location.strip() == trailhead.name]
        water_status = {
            name: entry for name, entry in latest_status_by_source(water_source_log or []).items()
            if name in {w.name for w in ws}
        }
        cgs = ([c for c in (campgrounds or []) if c.park == trailhead.park]
               if trailhead.park else [])
        cg_names = {c.name for c in cgs}
        sites = [s for s in (campsites or []) if s.campground in cg_names]
        pa = next((p for p in (park_access or []) if trailhead.park and p.park == trailhead.park),
                  None)
        if ws or cgs or sites or pa:
            facilities = FacilitiesInfo(
                water_sources=ws, water_status=water_status,
                campgrounds=cgs, campsites=sites, park_access=pa,
            )

    return PlanResult(
        requested_names=list(objective_names),
        objectives=objectives,
        not_found=not_found,
        trip_date=trip_date,
        trailhead=trailhead,
        trailhead_ambiguous=trailhead_ambiguous,
        entry_conflicts=conflicts,
        permit_entries=permit_entries,
        warnings=warnings,
        open_questions=questions,
        facilities=facilities,
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
        if result.entry_conflicts:
            # Lead with the doubt. Printing the trailhead first and the caveat
            # afterwards is how a reader ends up acting on the headline and
            # skimming the qualifier.
            lines.append("  ENTRY POINT UNRESOLVED -- sources disagree, see below.")
            lines.append(f"  Geometry suggests: {result.trailhead.name}{side}")
            for conflict in result.entry_conflicts:
                lines.append(f"  Sourced route for {conflict.peak_name}: "
                             f"{conflict.sourced_route}")
            lines.append("  These may be different entry points under different agencies, "
                         "which would mean a different permit entirely.")
        else:
            lines.append(f"  Trailhead: {result.trailhead.name}{side}")
    else:
        lines.append("  No trailhead data available.")
    lines.append("")

    if result.facilities:
        fac = result.facilities
        lines.append("Facilities")
        if fac.water_sources:
            lines.append(f"  Water sources at {result.trailhead.name}:")
            for w in fac.water_sources:
                status = fac.water_status.get(w.name)
                if status:
                    lines.append(f"    - {w.name}: {status.observed_status} "
                                 f"(checked {status.checked_date})")
                else:
                    lines.append(f"    - {w.name}: no availability check on file")
        for c in fac.campgrounds:
            lines.append(f"  Campground: {c.name}")
            if c.reservation_method:
                lines.append(f"    Reservation: {c.reservation_method}")
            if c.fee_notes:
                lines.append(f"    Fee: {c.fee_notes}")
            if c.nightly_entry_cutoff:
                lines.append(f"    Nightly entry cutoff: {c.nightly_entry_cutoff}")
            sites = [s for s in fac.campsites if s.campground == c.name]
            if sites:
                lines.append(f"    Sites: {', '.join(f'{s.name} ({s.capacity})' for s in sites)}")
        if fac.park_access:
            pa = fac.park_access
            lines.append(f"  Park access ({pa.park}):")
            if pa.entrance_fee:
                cond = f" ({pa.fee_conditions})" if pa.fee_conditions else ""
                lines.append(f"    Entrance fee: {pa.entrance_fee}{cond}")
            if pa.gate_open or pa.gate_close:
                cond = f" ({pa.gate_hours_conditions})" if pa.gate_hours_conditions else ""
                lines.append(f"    Gate hours: {pa.gate_open}-{pa.gate_close}{cond}")
            if pa.fee_exemptions:
                lines.append(f"    Fee exemptions: {pa.fee_exemptions}")
        lines.append("")

    if result.entry_conflicts:
        lines.append("Permit (CANDIDATE ONLY -- follows the unresolved entry point above)")
        lines.append("  The verification dates below belong to the permit rule, not to the "
                     "claim that this permit governs your route. Do not read them as "
                     "confirming the entry point.")
    else:
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
        if result.entry_conflicts:
            # Picket Guard Peak reported 23.2 mi beside a Mineral King trailhead;
            # that figure is measured from Shepherd Pass. Two inconsistent facts
            # in one output, and the mileage looked like it corroborated the
            # trailhead above it.
            lines.append(
                "  NOTE: that standard trailhead is the one in each objective's source "
                "data, which is exactly what the entry point above is unresolved about. "
                "These distances are probably NOT measured from the trailhead named above."
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
