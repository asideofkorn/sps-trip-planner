"""Permit requirements for planned trips.

Wilderness permit rules (issuing agency, quota season, reservation window) are
curated in ``data/permits.csv``, keyed by the ``permit_group`` each trailhead
in ``data/trailheads.csv`` is tagged with. This module joins a cluster's
trailhead to its permit rule and, given a candidate trip start date, works out
whether that date falls in the quota season and when the reservation window
opens.

*When* a permit_group's inventory actually becomes available -- a single
rolling release, a percentage-split release, an annual lottery, a walk-up-only
system, or one requiring direct contact off-season -- is computed generically
from ``data/release_policies.csv`` (see :mod:`wayproof.release_policy`)
rather than special-cased per group in this module. That closed a real gap:
previously, a permit_group with e.g. a 60%-then-40% split release only ever
had its *first* release date computed; the second release existed only as a
sentence in ``reservation_method``, never as a date the tool itself could act
on. Yosemite's weekly lottery is the one deliberate exception still handled
inline below -- see :mod:`wayproof.release_policy` for why.

A permit's issuing agency is the trailhead's agency, not necessarily the
agency governing every peak reached from it: Sierra Nevada wilderness permits
are interagency -- a permit issued for the trailhead you start at is honored
for the rest of the trip, even where the route crosses into a neighboring
wilderness or national park (e.g. a Sierra NF permit picked up at the
Isberg/Clover Meadow trailhead covers the leg into Yosemite over Isberg Pass;
an Emigrant Wilderness self-issue permit covers a route that crosses into
Yosemite at Bond Pass). You do *not* need a second permit from the agency
whose land you pass through.

Per Inyo NF's own wording, this reciprocity requires *continuous* wilderness
travel: exiting the wilderness and re-entering elsewhere voids the permit and
requires a new one from the agency where that next section begins, EXCEPT a
reasonable resupply break for long-distance through-hikers. For the single-
trailhead loop trips this tool plans, that condition is always satisfied.
Each :class:`PermitRule` carries an ``interagency_note`` documenting where
reciprocity applies; a handful of boundary crossings have their own
procedural wrinkle on top of it (e.g. Kibbie Lake / Lake Eleanor out of
Stanislaus NF requires calling Yosemite's Groveland Ranger District a day
ahead) -- see the note before assuming blanket reciprocity.

Rules and dates shift year to year (recreation.gov release times, lottery
windows, exact quota-season start/end). Treat this as a planning aid, not a
booking guarantee -- always confirm against the ``apply_url`` before relying
on a date.

A trailhead's permit_group is a default, not a guarantee for every peak
reached from it: some trailheads serve more than one permitted trail with
different rules (e.g. Whitney Portal serves the lottery-only classic Mt.
Whitney Trail, but also the separately-permitted Mountaineers Route /
North Fork of Lone Pine Creek trail for Mount Russell). ``data/approaches.csv``
(see :mod:`wayproof.access`) records these peak-specific approach
relationships as structured data: which named route a peak uses, which
trailhead it starts from, and -- when a source directly confirms it -- which
permit_group actually governs it. :func:`clusters_permit_info` emits an
extra, peak-specific entry for each confirmed relationship that differs from
the trailhead default.

Some cases are plausible but not directly confirmed by a source (e.g. Mount
Irvine and Mount Mallory's source-listed trailhead names the Meysan Lake
Trail, a different route than Whitney Portal's main trail, but no source
confirms which permit product actually governs it). Rather than silently
assuming the trailhead default or silently omitting the peak,
``data/approaches.csv`` can record these with ``status=unconfirmed``;
:func:`clusters_permit_info` then emits an explicit caution alongside the
default entry instead of asserting an unverified answer. Treat any peak
sharing a trailhead with a lottery/special permit as worth double-checking if
its standard route isn't the trailhead's main trail, even when it has no row
here yet.

``data/permits.csv`` only stores the current best-known answer per
permit_group -- each edit overwrites the last one, so on its own it can't
reveal that two different sources disagreed. ``data/permit_source_log.csv``
is the append-only complement: one row per verification event (never
edited, only appended to), recording the source URL, the source's own
"last updated" date, how it was checked, and a verdict of ``new-group``,
``confirms-existing``, ``corrects-existing``, or ``unresolved-conflict``.
When a new source disagrees with what's already logged, log it as
``unresolved-conflict`` first (don't silently pick one), then once it's
reconciled -- by updating ``data/permits.csv`` and appending a follow-up
``corrects-existing`` entry explaining which source won and why -- the
disagreement closes, because the log is read in chronological order.

Conflicts are tracked per ``(permit_group, conflict_id)``, not per
permit_group. That distinction was learned the hard way: Desolation opened
three unrelated disagreements in one session (whether day-use permits are
year-round or quota-season-only, which fee tier applies, and whether the
Special Management Area setback is 25 or 30 feet). With group-level
tracking, resolving any one of them closed all three, because only the
group's last entry was read. Closing a conflict that is still open is worse
than not tracking it at all -- it converts a known unknown into a silent
wrong answer -- so the workaround at the time was to leave a resolved
verdict deliberately dirty, which does not survive a third conflict.

:func:`open_conflicts` reports each open disagreement separately;
:func:`unresolved_conflicts` rolls those up to the permit_groups affected.
A resolving entry closes only the ``conflict_id`` it names, so a generic
``confirms-existing`` row never silently closes a specific identified
disagreement. Entries with no ``conflict_id`` share one per-group bucket,
which is the old behaviour and is fine for a group that only ever has one
conflict open at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .access import ApproachRoute
from .model import Cluster, Trailhead
from .release_policy import (
    ReleasePhase,
    IN_SEASON,
    OFF_SEASON,
    RESERVATION,
    LOTTERY_ANNUAL,
    WALKUP,
    CONTACT_REQUIRED,
    load_release_policies,
)

# Special-cased because the 60% portion is a weekly lottery (apply within a
# week-long window, don't just show up at the 168-day mark and book), not a
# simple first-come reservation like the generic "window is open" message
# below implies. Unlike every other lottery/split-release group, this one is
# deliberately NOT migrated to data/release_policies.csv -- see that module's
# docstring for why (the source's own per-area dates are approximate).
_YOSEMITE = "yosemite"


@dataclass
class PermitRule:
    """One row of ``data/permits.csv``: the permit rule for a permit_group."""

    permit_group: str
    agency: str
    """Display name of the issuing agency, e.g. ``"Eldorado NF / LTBMU"``.

    Free text, and deliberately so -- it carries ranger-district and
    co-management detail a reader wants. Never match on it; use
    :attr:`agency_ids`.
    """
    permit_type: str
    quota_required: bool
    quota_season_start: Optional[tuple] = None  # (month, day) or None
    quota_season_end: Optional[tuple] = None
    reservation_window_days: Optional[int] = None
    reservation_method: str = ""
    fee_notes: str = ""
    apply_url: str = ""
    notes: str = ""
    interagency_note: str = ""
    excludes: str = ""
    """What this permit does NOT cover, and what you need instead.

    A boundary statement about the permit product, distinct from a regulation
    (what you may do) and from provenance (how we know). It earns a field
    because getting it wrong means arriving at a trailhead holding a document
    that does not admit you: the Whitney Zone permit does not cover the North
    Fork of Lone Pine Creek approaches, which need an ordinary Inyo NF permit,
    and that fact was previously buried in seven sentences of prose.
    """
    # Structured release phases from data/release_policies.csv, if migrated
    # (see wayproof.release_policy). Empty for groups still on the
    # generic reservation_window_days fallback below (currently Yosemite).
    release_phases: List[ReleasePhase] = field(default_factory=list)
    # State whose law applies, e.g. "CA". Used by wayproof.regulations to
    # inherit statewide rules (the California Campfire Permit) without
    # copying them into every permit_group.
    jurisdiction: str = ""
    wilderness_area: str = ""
    """The designated wilderness this permit admits you to, e.g.
    ``"Mokelumne Wilderness"``.

    Used by :mod:`wayproof.regulations` to inherit one wilderness's rulebook
    across every permit product that enters it. Mokelumne has two -- the free
    general self-issue permit and the quota'd Carson Pass Management Area
    permit -- sharing one set of regulations.
    """
    agency_ids: tuple = ()
    """Stable keys for the managing agencies, e.g. ``("eldorado_nf", "ltbmu")``.

    Separate from :attr:`agency` for the same reason ``jurisdiction`` is a
    column rather than an inference: agency-scoped regulations have to match
    *something*, and matching the display string silently matched nothing --
    Desolation's reads "Eldorado NF / LTBMU" while the regulation said
    "Eldorado National Forest", so the forest-wide rule inherited to zero
    groups and nobody noticed. A list because co-management is real: Desolation
    is administered jointly by Eldorado NF and the Lake Tahoe Basin Management
    Unit, and a rule from either applies.
    """
    source_last_updated: str = ""
    """The ``apply_url`` page's OWN "last updated" date, if it shows one.

    One row, one date, describing one page. When a row is enriched from a
    second source -- a forest FAQ, a trip-planning guide -- that source's date
    belongs in ``data/permit_source_log.csv`` alongside its URL, not here.
    Stamping it here reads as "the apply_url page was updated then", which is
    false and quietly ages the row wrong in both directions.
    """
    verified_date: str = ""        # date this row was last checked against that source
    log_entry_ids: str = ""
    """Semicolon-separated ``entry_id`` values establishing this row's current
    state. See :mod:`wayproof.evidence`."""

    def in_quota_season(self, trip_date: date) -> bool:
        """Whether ``trip_date`` falls in this rule's quota season.

        A quota-required rule with no season bounds (e.g. Sierra NF, whose
        quotas apply year-round per fs.usda.gov) is always in season.
        """
        if not self.quota_required:
            return False
        if not self.quota_season_start:
            return True
        start, end = self.quota_season_start, self.quota_season_end
        return (start[0], start[1]) <= (trip_date.month, trip_date.day) <= (end[0], end[1])


def _parse_mmdd(value) -> Optional[tuple]:
    if pd.isna(value) or not str(value).strip():
        return None
    month, day = str(value).strip().split("-")
    return (int(month), int(day))


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def load_permits(
    path: str | Path = "data/permits.csv",
    release_policies_path: str | Path = "data/release_policies.csv",
) -> Dict[str, PermitRule]:
    """Load the curated permit-rule table, keyed by ``permit_group``.

    Also attaches each group's structured release phases from
    ``release_policies_path`` (see :mod:`wayproof.release_policy`), when
    that permit_group has been migrated there. Groups without any phases
    (currently only Yosemite) fall back to ``permit_status``'s older,
    coarser single-offset logic.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Permit rules file not found: {path}")
    df = pd.read_csv(path)
    phases_by_group = load_release_policies(release_policies_path)

    rules: Dict[str, PermitRule] = {}
    for _, row in df.iterrows():
        group = _str_field(row, "permit_group")
        window = row.get("reservation_window_days")
        rules[group] = PermitRule(
            permit_group=group,
            agency=_str_field(row, "agency"),
            wilderness_area=_str_field(row, "wilderness_area"),
            agency_ids=tuple(
                part.strip() for part in _str_field(row, "agency_id").split(";") if part.strip()
            ),
            jurisdiction=_str_field(row, "jurisdiction"),
            permit_type=_str_field(row, "permit_type"),
            quota_required=_str_field(row, "quota_required").lower() == "yes",
            quota_season_start=_parse_mmdd(row.get("quota_season_start")),
            quota_season_end=_parse_mmdd(row.get("quota_season_end")),
            reservation_window_days=int(window) if not pd.isna(window) and str(window).strip() else None,
            reservation_method=_str_field(row, "reservation_method"),
            fee_notes=_str_field(row, "fee_notes"),
            apply_url=_str_field(row, "apply_url"),
            notes=_str_field(row, "notes"),
            interagency_note=_str_field(row, "interagency_note"),
            excludes=_str_field(row, "excludes"),
            release_phases=phases_by_group.get(group, []),
            source_last_updated=_str_field(row, "source_last_updated"),
            verified_date=_str_field(row, "verified_date"),
            log_entry_ids=_str_field(row, "log_entry_ids"),
        )
    return rules


def _format_reservation_phases(
    phases: Sequence[ReleasePhase], trip_date: date, today: date
) -> str:
    """Render one or more ``reservation`` phases, earliest date first.

    A single phase reproduces the original simple "reservations open/window
    is open" wording. A second (or later) phase surfaces its own date and
    allocation -- the gap this module exists to close: that date previously
    only ever existed as prose. A phase with no resolvable date (the source
    gives an allocation but not an exact offset) contributes its ``notes``
    instead of a fabricated date.
    """
    resolved = [(p, p.event_date(trip_date)) for p in phases]
    dated = sorted(((p, d) for p, d in resolved if d is not None), key=lambda pd: pd[1])
    undated = [p for p, d in resolved if d is None]

    if not dated:
        return "Not reservable in advance -- see notes for timing."

    first_phase, first_date = dated[0]
    time_suffix = f" ({first_phase.time_of_day} {first_phase.timezone})" if first_phase.time_of_day else ""
    if today < first_date:
        lines = [f"Reservations open {first_date:%Y-%m-%d}{time_suffix} -- mark your calendar."]
    else:
        lines = [f"Reservation window is OPEN (opened {first_date:%Y-%m-%d}{time_suffix}) "
                 f"-- book now on recreation.gov."]

    for phase, event_date in dated[1:]:
        pct = f"{int(phase.allocation_pct)}%" if phase.allocation_pct else "remaining"
        suffix = f" ({phase.time_of_day} {phase.timezone})" if phase.time_of_day else ""
        verb = "opens" if today < event_date else "also opened"
        lines.append(f"A further {pct} release {verb} {event_date:%Y-%m-%d}{suffix}.")

    for phase in undated:
        if phase.notes:
            lines.append(phase.notes)

    return " ".join(lines)


def _format_annual_lottery(
    phases: Sequence[ReleasePhase], trip_date: date, today: date
) -> str:
    """Render an annual (fixed calendar-date) lottery cycle, e.g. Whitney Zone.

    Requires ``apply_start`` and ``apply_end`` labeled phases at minimum;
    ``results`` and ``claim_deadline`` are used when present, and a
    ``reservation`` phase in the same set is treated as the unclaimed-permit
    release that follows the claim deadline.
    """
    by_label = {p.label: p for p in phases if p.mechanism == LOTTERY_ANNUAL}
    release_phase = next((p for p in phases if p.mechanism == RESERVATION), None)

    apply_start = by_label["apply_start"].event_date(trip_date)
    apply_end = by_label["apply_end"].event_date(trip_date)
    results_phase = by_label.get("results")
    results_date = results_phase.event_date(trip_date) if results_phase else None
    claim_phase = by_label.get("claim_deadline")
    claim_date = claim_phase.event_date(trip_date) if claim_phase else None
    unclaimed_date = release_phase.event_date(trip_date) if release_phase else None

    year = trip_date.year
    if today < apply_start:
        return f"Lottery for {year} opens {apply_start:%b %-d}; apply by {apply_end:%b %-d}."
    if apply_start <= today <= apply_end:
        return f"Lottery is OPEN NOW -- apply by {apply_end:%b %-d}."
    if unclaimed_date and apply_end < today < unclaimed_date:
        return (f"Lottery closed; results post ~{results_date:%b %-d}, claim & pay by "
                f"~{claim_date:%b %-d}. Unclaimed dates open first-come "
                f"{unclaimed_date:%b %-d} at 7am Pacific.")
    return (f"{year} lottery process is over -- check recreation.gov for "
            f"first-come availability (cancellations happen) up to 2 days ahead.")


def _format_walkup_share(phases: Sequence[ReleasePhase]) -> str:
    """Describe walk-up/contact-only phases that sit *alongside* reservable ones."""
    share = [p for p in phases if p.mechanism in (WALKUP, CONTACT_REQUIRED)]
    if not share:
        return ""
    pct = next((f"{int(p.allocation_pct)}%" for p in share if p.allocation_pct), "A share")
    lead = f"{pct} of" if pct.endswith("%") else f"{pct} of"
    return (f"{lead} the quota is held back for same-day, first-come permits issued in "
            f"person -- not bookable online at any point.")


def _format_release_events(
    phases: Sequence[ReleasePhase], trip_date: date, today: date
) -> str:
    """Dispatch a permit_group's applicable phases to the right renderer by mechanism.

    Mechanisms are not mutually exclusive within one season. Desolation splits
    a single zone quota between a reservable share and a same-day walk-up
    share, so a ``walkup`` phase sitting next to ``reservation`` phases
    describes *part* of the rule, not the whole of it -- letting its presence
    short-circuit to "not reservable in advance" would be exactly backwards
    for the two-thirds that is reservable. Reservable phases therefore win the
    dispatch whenever any exist, and the walk-up share is appended.
    """
    if any(p.mechanism == LOTTERY_ANNUAL for p in phases):
        return _format_annual_lottery(phases, trip_date, today)

    reservation_phases = [p for p in phases if p.mechanism == RESERVATION]
    if reservation_phases:
        status = _format_reservation_phases(reservation_phases, trip_date, today)
        walkup = _format_walkup_share(phases)
        return f"{status} {walkup}" if walkup else status

    if any(p.mechanism == WALKUP for p in phases):
        return ("Not reservable in advance -- issued in person on a first-come "
                "basis; see the reservation method for timing.")
    if any(p.mechanism == CONTACT_REQUIRED for p in phases):
        msg = "Not self-issue -- contact the agency directly to arrange a permit."
        notes = " ".join(p.notes for p in phases if p.notes)
        return f"{msg} {notes}" if notes else msg
    return _format_reservation_phases(phases, trip_date, today)


def permit_status(
    rule: PermitRule, trip_date: date, today: Optional[date] = None
) -> str:
    """Human-readable guidance for applying for this permit on ``trip_date``.

    When ``rule.release_phases`` is populated (see
    :mod:`wayproof.release_policy`), the status is computed generically
    from that structured data, filtered to whichever phases apply given
    whether ``trip_date`` falls in the quota season. Groups not yet migrated
    (currently only Yosemite -- see that module's docstring for why) fall
    back to the original coarser single-offset logic below.
    """
    today = today or date.today()

    if not rule.quota_required:
        if rule.agency:
            return "Free self-issue permit -- no reservation needed, available any time."
        return "No wilderness permit required."

    in_season = rule.in_quota_season(trip_date)
    off_season_phases = [p for p in rule.release_phases if p.season == OFF_SEASON]
    in_season_phases = [p for p in rule.release_phases if p.season != OFF_SEASON]

    if not in_season:
        if off_season_phases:
            return _format_release_events(off_season_phases, trip_date, today)
        start, end = rule.quota_season_start, rule.quota_season_end
        season = (f"{date(2001, *start):%b %-d} - {date(2001, *end):%b %-d}"
                   if start and end else "the quota season")
        return (f"Trip date is outside the {season} quota season -- permit still "
                f"required but should be free/self-issue, no reservation (confirm "
                f"with the agency for current off-season rules).")

    if in_season_phases:
        return _format_release_events(in_season_phases, trip_date, today)

    # Legacy path for permit_groups not yet migrated to data/release_policies.csv.
    if rule.reservation_window_days is None or rule.reservation_window_days == 0:
        return ("Not reservable in advance -- issued in person on a first-come "
                "basis; see the reservation method for timing.")

    opens = trip_date - timedelta(days=rule.reservation_window_days)
    if rule.permit_group == _YOSEMITE:
        if today < opens:
            return (f"Weekly lottery for your hiking-start week opens around "
                     f"{opens:%Y-%m-%d} -- apply within that week-long window "
                     f"(Sunday-Saturday), don't wait for a simple booking window "
                     f"to open.")
        return (f"Lottery window for this date has likely opened (~{opens:%Y-%m-%d}) "
                f"-- apply on recreation.gov if you haven't; if the lottery has "
                f"closed, check for unclaimed first-come spots or the 40% released "
                f"7 days out.")
    if today < opens:
        return f"Reservations open {opens:%Y-%m-%d} (7am Pacific) -- mark your calendar."
    return (f"Reservation window is OPEN (opened {opens:%Y-%m-%d}) -- book now on "
            f"recreation.gov; watch for a secondary release closer to your date.")


@dataclass
class ClusterPermitInfo:
    """Permit guidance for one cluster, given a candidate trip start date."""

    cluster_id: int
    trailhead: str
    wilderness_area: str
    agency: str
    permit_type: str
    fee_notes: str
    apply_url: str
    trip_date: date
    status: str
    notes: str = ""
    interagency_note: str = ""
    peak_note: str = ""  # e.g. "for Mount Russell only" when this overrides the default
    source_last_updated: str = ""
    verified_date: str = ""
    approach_name: str = ""    # named route this entry is specific to, if any
    approach_status: str = ""  # "confirmed" / "unconfirmed" / "" (trailhead default)


def _permit_entry(
    cluster_id: int, trailhead: str, wilderness_area: str, rule: PermitRule,
    trip_date: date, today: Optional[date], peak_note: str = "",
    approach_name: str = "", approach_status: str = "",
) -> ClusterPermitInfo:
    return ClusterPermitInfo(
        cluster_id=cluster_id,
        trailhead=trailhead,
        wilderness_area=wilderness_area,
        agency=rule.agency,
        permit_type=rule.permit_type,
        fee_notes=rule.fee_notes,
        apply_url=rule.apply_url,
        trip_date=trip_date,
        status=permit_status(rule, trip_date, today),
        notes=rule.notes,
        interagency_note=rule.interagency_note,
        peak_note=peak_note,
        source_last_updated=rule.source_last_updated,
        verified_date=rule.verified_date,
        approach_name=approach_name,
        approach_status=approach_status,
    )


def clusters_permit_info(
    clusters: Sequence[Cluster],
    trailheads: Sequence[Trailhead],
    permits: Dict[str, PermitRule],
    trip_date: date,
    today: Optional[date] = None,
    approaches: Optional[Sequence[ApproachRoute]] = None,
) -> List[ClusterPermitInfo]:
    """Resolve permit guidance for every cluster that has a chosen trailhead.

    Clusters without a trailhead (approach modeling was off) are skipped --
    there is nothing to key the permit lookup on. ``approaches`` (see
    :mod:`wayproof.access`) supplies peak-specific approach relationships:

    - A ``confirmed`` route whose permit_group differs from the trailhead
      default adds an extra, peak-specific permit entry, so a mixed trip
      (e.g. Mount Whitney + Mount Russell from Whitney Portal) surfaces both
      permits it actually needs.
    - An ``unconfirmed`` route adds a caution entry instead of asserting a
      different permit -- it flags that the trailhead default may not apply
      to that peak without inventing an unverified answer.

    A route naming a different ``trailhead`` than the cluster's chosen one is
    skipped -- it describes an approach from somewhere else.
    """
    th_by_name = {t.name: t for t in trailheads}
    by_peak: Dict[str, List[ApproachRoute]] = {}
    for route in approaches or []:
        by_peak.setdefault(route.peak_name, []).append(route)

    rows: List[ClusterPermitInfo] = []
    for c in clusters:
        if not c.trailhead:
            continue
        th = th_by_name.get(c.trailhead)
        if th is None or not th.permit_group:
            continue
        rule = permits.get(th.permit_group)
        if rule is None:
            continue
        rows.append(_permit_entry(c.cluster_id, c.trailhead, th.wilderness_area,
                                   rule, trip_date, today))

        seen = set()
        for peak in c.peaks:
            for route in by_peak.get(peak.name, []):
                if route.trailhead and route.trailhead != c.trailhead:
                    continue  # this known approach starts from a different trailhead

                if not route.confirmed:
                    key = ("unconfirmed", peak.name, route.approach_name)
                    if key in seen:
                        continue
                    seen.add(key)
                    caution = (
                        f"UNCERTAIN for {peak.name}: approach may be "
                        f"{route.approach_name or 'a different route'}, not "
                        f"confirmed against a source -- do not assume the "
                        f"{c.trailhead} default above applies without "
                        f"verifying independently."
                    )
                    if route.notes:
                        caution += f" {route.notes}"
                    rows.append(_permit_entry(
                        c.cluster_id, c.trailhead, th.wilderness_area, rule,
                        trip_date, today, peak_note=caution,
                        approach_name=route.approach_name,
                        approach_status=route.status,
                    ))
                    continue

                if not route.permit_group or route.permit_group == th.permit_group:
                    continue
                if route.permit_group in seen:
                    continue  # avoid duplicate entries when >1 peak shares an approach
                override_rule = permits.get(route.permit_group)
                if override_rule is None:
                    continue
                seen.add(route.permit_group)
                note = f"for {peak.name} only"
                if route.approach_name:
                    note += f" -- via {route.approach_name}"
                rows.append(_permit_entry(
                    c.cluster_id, c.trailhead, th.wilderness_area, override_rule,
                    trip_date, today, peak_note=note,
                    approach_name=route.approach_name, approach_status=route.status,
                ))
    return rows


def format_permit_entry_body(r: ClusterPermitInfo) -> List[str]:
    """Render one permit entry's detail lines (no header) -- shared by
    :func:`format_permit_report` and :mod:`wayproof.plan`."""
    lines = []
    if r.wilderness_area:
        lines.append(f"  Wilderness: {r.wilderness_area}  |  Agency: {r.agency}")
    lines.append(f"  Permit: {r.permit_type}")
    lines.append(f"  Status: {r.status}")
    if r.fee_notes:
        lines.append(f"  Fee: {r.fee_notes}")
    if r.apply_url:
        lines.append(f"  Apply: {r.apply_url}")
    if r.notes:
        lines.append(f"  Note: {r.notes}")
    if r.interagency_note:
        lines.append(f"  Crosses into other land: {r.interagency_note}")
    if r.verified_date:
        src = f"source last updated {r.source_last_updated}" if r.source_last_updated else "source's own update date not shown"
        lines.append(f"  Provenance: {src}; we last checked this against the "
                      f"source on {r.verified_date}.")
    else:
        lines.append("  Provenance: NOT independently verified against a primary "
                      "source (web-search synthesis only) -- treat with extra caution.")
    return lines


def format_permit_report(rows: Sequence[ClusterPermitInfo]) -> str:
    """Render permit guidance as readable text, one block per cluster."""
    if not rows:
        return ("No permit info to show -- run with --include-approach (or "
                "--permits, which implies it) so trips have a trailhead.")

    lines = []
    for r in rows:
        suffix = f"  [{r.peak_note}]" if r.peak_note else ""
        lines.append(f"Group #{r.cluster_id} -- {r.trailhead}  "
                      f"(trip date {r.trip_date:%Y-%m-%d}){suffix}")
        lines.extend(format_permit_entry_body(r))
        lines.append("")
    lines.append(
        "Permit rules and dates change year to year -- verify against the "
        "linked official source before relying on any date above. Interagency "
        "reciprocity assumes one continuous trip that starts and ends at the "
        "listed trailhead -- a fresh trip starting inside the neighboring "
        "wilderness/park still needs its own permit."
    )
    return "\n".join(lines)


_CONFLICT_VERDICT = "unresolved-conflict"
_VALID_VERDICTS = {"new-group", "confirms-existing", "corrects-existing", _CONFLICT_VERDICT}


@dataclass
class SourceLogEntry:
    """One row of ``data/permit_source_log.csv``: a single verification event.

    The log is append-only -- never edit or delete a past entry, even to fix
    a conflict. Append a new entry that resolves it instead, so the sequence
    of checks (and any disagreement between them) stays visible.
    """

    date_checked: str
    permit_group: str
    source_url: str
    source_last_updated: str
    method: str
    verdict: str
    summary: str
    conflict_id: str = ""
    """Names the specific disagreement this entry opens, restates, or closes.

    Free-form but stable, e.g. ``desolation-sma-distance``. Leave blank for
    an ordinary verification that isn't about a disagreement; blank entries
    share one per-group bucket, so a group with at most one live conflict
    needs no ids at all.
    """

    conflict_kind: str = ""
    """``internal`` when one document disagrees with itself, ``cross_source``
    when two documents disagree.

    It decides how to resolve the conflict, so it is worth recording rather
    than rediscovering. A self-contradicting document has already told you its
    blanket statement is unreliable, and needs no ranking of publishers -- two
    of the three conflicts opened in one week turned out to be this, wearing
    the costume of a cross-source dispute. See :mod:`wayproof.provenance`.
    """

    entry_id: str = ""
    """Stable, sayable handle for this check: ``group-date-seq``.

    Claims cite it, so a reader can walk from one sentence on a page to the
    verification event behind it, and a changed source can name the rows that
    depend on it. See :mod:`wayproof.evidence`.
    """


@dataclass
class OpenConflict:
    """One disagreement that is still open: sources conflict and nothing
    logged since has closed it."""

    permit_group: str
    conflict_id: str
    kind: str = ""
    """``internal`` or ``cross_source`` -- how this one has to be resolved."""
    opened: str = ""
    """``date_checked`` of the entry that first opened this disagreement."""
    last_checked: str = ""
    entries: List[SourceLogEntry] = field(default_factory=list)
    """Every entry in this thread, chronologically -- the resolved ones too."""

    @property
    def label(self) -> str:
        """``"desolation (desolation-fee-tier)"``, or just the group when the
        thread carries no id."""
        return f"{self.permit_group} ({self.conflict_id})" if self.conflict_id else self.permit_group

    @property
    def summary(self) -> str:
        """What the most recent entry says the disagreement is."""
        return self.entries[-1].summary if self.entries else ""


def load_source_log(
    path: str | Path = "data/permit_source_log.csv",
) -> List[SourceLogEntry]:
    """Load the append-only permit source-verification log, in file order.

    Returns an empty list if the file doesn't exist -- the log is an
    optional audit trail, not a required input for permit lookups.
    """
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    return [
        SourceLogEntry(
            date_checked=_str_field(row, "date_checked"),
            permit_group=_str_field(row, "permit_group"),
            source_url=_str_field(row, "source_url"),
            source_last_updated=_str_field(row, "source_last_updated"),
            method=_str_field(row, "method"),
            verdict=_str_field(row, "verdict"),
            summary=_str_field(row, "summary"),
            conflict_id=_str_field(row, "conflict_id"),
            conflict_kind=_str_field(row, "conflict_kind"),
            entry_id=_str_field(row, "entry_id"),
        )
        for _, row in df.iterrows()
    ]


def open_conflicts(log: Sequence[SourceLogEntry]) -> List[OpenConflict]:
    """Every disagreement whose thread still ends in ``unresolved-conflict``.

    Threads are keyed on ``(permit_group, conflict_id)``, so several can be
    open on one permit group at once and close independently. Assumes ``log``
    is in chronological order, as loaded from the file: within a thread the
    last entry wins, so a later ``corrects-existing`` closes an earlier
    ``unresolved-conflict``.

    Crossing threads never closes anything. An entry naming one
    ``conflict_id`` leaves the group's other threads exactly as they were,
    and an entry naming none closes only the unkeyed bucket -- a routine
    re-check of a permit's fee cannot quietly resolve an open argument about
    its season. Returned in the order each thread first appears in the log.
    """
    threads: Dict[tuple, List[SourceLogEntry]] = {}
    for entry in log:
        threads.setdefault((entry.permit_group, entry.conflict_id), []).append(entry)

    out: List[OpenConflict] = []
    for (group, conflict_id), entries in threads.items():
        if entries[-1].verdict != _CONFLICT_VERDICT:
            continue
        disagreements = [e for e in entries if e.verdict == _CONFLICT_VERDICT]
        out.append(OpenConflict(
            permit_group=group,
            conflict_id=conflict_id,
            kind=next((e.conflict_kind for e in reversed(entries) if e.conflict_kind), ""),
            opened=disagreements[0].date_checked,
            last_checked=entries[-1].date_checked,
            entries=list(entries),
        ))
    return out


def unresolved_conflicts(log: Sequence[SourceLogEntry]) -> List[str]:
    """permit_groups with at least one open conflict, first-seen order.

    A roll-up of :func:`open_conflicts` for callers that only need to know
    whether a group is disputed at all. Use ``open_conflicts`` where the
    answer matters -- one group can be carrying several unrelated arguments.
    """
    groups: List[str] = []
    for conflict in open_conflicts(log):
        if conflict.permit_group not in groups:
            groups.append(conflict.permit_group)
    return groups


def format_source_log(
    log: Sequence[SourceLogEntry], permit_group: Optional[str] = None
) -> str:
    """Render the source log as readable text, optionally filtered to one group."""
    rows = [e for e in log if permit_group is None or e.permit_group == permit_group]
    if not rows:
        return f"No source log entries{f' for {permit_group}' if permit_group else ''}."

    lines = []
    conflicts = [c for c in open_conflicts(log)
                 if permit_group is None or c.permit_group == permit_group]
    open_keys = {(c.permit_group, c.conflict_id) for c in conflicts}
    open_per_group: Dict[str, int] = {}
    for c in conflicts:
        open_per_group[c.permit_group] = open_per_group.get(c.permit_group, 0) + 1
    if conflicts:
        lines.append("UNRESOLVED CONFLICTS: "
                     + ", ".join(sorted(c.label for c in conflicts)))
        lines.append("")

    current_group = None
    for e in rows:
        if e.permit_group != current_group:
            current_group = e.permit_group
            count = open_per_group.get(current_group, 0)
            flag = ""
            if count == 1:
                flag = "  <-- UNRESOLVED CONFLICT"
            elif count > 1:
                flag = f"  <-- {count} UNRESOLVED CONFLICTS"
            lines.append(f"=== {current_group}{flag} ===")
        marker = {"new-group": "NEW", "confirms-existing": "CONFIRMS",
                   "corrects-existing": "CORRECTS", _CONFLICT_VERDICT: "CONFLICT"}.get(e.verdict, e.verdict)
        url = e.source_url or "(no single URL -- web search / general knowledge)"
        updated = f", source updated {e.source_last_updated}" if e.source_last_updated else ""
        thread = ""
        if e.conflict_id:
            state = "still open" if (e.permit_group, e.conflict_id) in open_keys else "closed"
            thread = f", conflict {e.conflict_id} ({state})"
        lines.append(f"  [{e.date_checked}] {marker} via {e.method}{updated}{thread}")
        lines.append(f"    {url}")
        lines.append(f"    {e.summary}")
    return "\n".join(lines)
