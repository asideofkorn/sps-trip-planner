"""Permit requirements for planned trips.

Wilderness permit rules (issuing agency, quota season, reservation window) are
curated in ``data/permits.csv``, keyed by the ``permit_group`` each trailhead
in ``data/trailheads.csv`` is tagged with. This module joins a cluster's
trailhead to its permit rule and, given a candidate trip start date, works out
whether that date falls in the quota season and when the reservation window
opens.

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
North Fork of Lone Pine Creek trail for Mount Russell, and the Meysan Lakes
Trail for several other peaks). ``data/permit_overrides.csv`` lists specific
peaks whose actual required permit differs from their trailhead's default;
:func:`clusters_permit_info` emits an extra, peak-specific entry for those.
This file is deliberately conservative -- only peaks with a directly-named
source are listed. Known-likely-but-unconfirmed cases (e.g. the Meysan Lakes
Trail peaks, or Mount Carillon) are intentionally left off rather than
guessed at; treat any peak sharing a trailhead with a lottery/special
permit as worth double-checking if its standard route isn't the trailhead's
main trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .model import Cluster, Trailhead

# Special-cased because it's a lottery, not a rolling reservation window.
_WHITNEY_ZONE = "whitney_zone"
# Special-cased because its off-season isn't self-issue -- it's in-person/email
# only, unlike the generic "free/self-issue off-season" assumption below.
_CPMA = "cpma"


@dataclass
class PermitRule:
    """One row of ``data/permits.csv``: the permit rule for a permit_group."""

    permit_group: str
    agency: str
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
    source_last_updated: str = ""  # the source page/doc's own "last updated" date, if shown
    verified_date: str = ""        # date this row was last checked against that source

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


def load_permits(path: str | Path = "data/permits.csv") -> Dict[str, PermitRule]:
    """Load the curated permit-rule table, keyed by ``permit_group``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Permit rules file not found: {path}")
    df = pd.read_csv(path)

    rules: Dict[str, PermitRule] = {}
    for _, row in df.iterrows():
        group = _str_field(row, "permit_group")
        window = row.get("reservation_window_days")
        rules[group] = PermitRule(
            permit_group=group,
            agency=_str_field(row, "agency"),
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
            source_last_updated=_str_field(row, "source_last_updated"),
            verified_date=_str_field(row, "verified_date"),
        )
    return rules


def load_permit_overrides(
    path: str | Path = "data/permit_overrides.csv",
) -> Dict[str, str]:
    """Load peak-name -> permit_group overrides (see module docstring).

    Returns an empty dict if the file doesn't exist -- overrides are opt-in
    extra precision, not a required input.
    """
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return {
        _str_field(row, "peak_name"): _str_field(row, "permit_group_override")
        for _, row in df.iterrows()
        if _str_field(row, "peak_name") and _str_field(row, "permit_group_override")
    }


def _whitney_lottery_status(trip_date: date, today: date) -> str:
    year = trip_date.year
    apply_start = date(year, 2, 1)
    apply_end = date(year, 3, 1)
    results = date(year, 3, 15)
    claim_deadline = date(year, 4, 21)
    unclaimed_release = date(year, 4, 22)

    if today < apply_start:
        return (f"Lottery for {year} opens {apply_start:%b %-d}; apply by "
                f"{apply_end:%b %-d}.")
    if apply_start <= today <= apply_end:
        return f"Lottery is OPEN NOW -- apply by {apply_end:%b %-d}."
    if apply_end < today < unclaimed_release:
        return (f"Lottery closed; results post ~{results:%b %-d}, claim & pay by "
                f"~{claim_deadline:%b %-d}. Unclaimed dates open first-come "
                f"{unclaimed_release:%b %-d} at 7am Pacific.")
    return (f"{year} lottery process is over -- check recreation.gov for "
            f"first-come availability (cancellations happen) up to 2 days ahead.")


def permit_status(
    rule: PermitRule, trip_date: date, today: Optional[date] = None
) -> str:
    """Human-readable guidance for applying for this permit on ``trip_date``."""
    today = today or date.today()

    if not rule.quota_required:
        if rule.agency:
            return "Free self-issue permit -- no reservation needed, available any time."
        return "No wilderness permit required."

    if rule.permit_group == _WHITNEY_ZONE:
        base = _whitney_lottery_status(trip_date, today)
        if not rule.in_quota_season(trip_date):
            base += " (Trip date is outside the May 1 - Nov 1 quota season.)"
        return base

    if not rule.in_quota_season(trip_date):
        start, end = rule.quota_season_start, rule.quota_season_end
        season = (f"{date(2001, *start):%b %-d} - {date(2001, *end):%b %-d}"
                   if start and end else "the quota season")
        if rule.permit_group == _CPMA:
            return (f"Trip date is outside the {season} quota season -- the Carson "
                    f"Pass Information Station is closed. Permit is still required "
                    f"but is NOT self-issue: get it in person at the Amador Ranger "
                    f"District office or by emailing SM.FS.mowilderness@usda.gov "
                    f"the week of your trip (see notes).")
        return (f"Trip date is outside the {season} quota season -- permit still "
                f"required but should be free/self-issue, no reservation (confirm "
                f"with the agency for current off-season rules).")

    if rule.reservation_window_days is None or rule.reservation_window_days == 0:
        return ("Not reservable in advance -- issued in person on a first-come "
                "basis; see the reservation method for timing.")

    opens = trip_date - timedelta(days=rule.reservation_window_days)
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


def _permit_entry(
    cluster_id: int, trailhead: str, wilderness_area: str, rule: PermitRule,
    trip_date: date, today: Optional[date], peak_note: str = "",
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
    )


def clusters_permit_info(
    clusters: Sequence[Cluster],
    trailheads: Sequence[Trailhead],
    permits: Dict[str, PermitRule],
    trip_date: date,
    today: Optional[date] = None,
    overrides: Optional[Dict[str, str]] = None,
) -> List[ClusterPermitInfo]:
    """Resolve permit guidance for every cluster that has a chosen trailhead.

    Clusters without a trailhead (approach modeling was off) are skipped --
    there is nothing to key the permit lookup on. When ``overrides`` names a
    peak in the cluster whose actual permit_group differs from the
    trailhead's default (see :func:`load_permit_overrides`), an additional
    peak-specific entry is emitted alongside the trailhead's default one, so
    a mixed trip (e.g. Mount Whitney + Mount Russell from Whitney Portal)
    surfaces both permits it actually needs.
    """
    th_by_name = {t.name: t for t in trailheads}
    overrides = overrides or {}
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

        seen_override_groups = set()
        for peak in c.peaks:
            override_group = overrides.get(peak.name)
            if not override_group or override_group == th.permit_group:
                continue
            if override_group in seen_override_groups:
                continue  # avoid duplicate entries when >1 peak shares an override
            override_rule = permits.get(override_group)
            if override_rule is None:
                continue
            seen_override_groups.add(override_group)
            rows.append(_permit_entry(
                c.cluster_id, c.trailhead, th.wilderness_area, override_rule,
                trip_date, today, peak_note=f"for {peak.name} only -- see notes",
            ))
    return rows


def format_permit_report(rows: Sequence[ClusterPermitInfo]) -> str:
    """Render permit guidance as readable text, one block per cluster."""
    if not rows:
        return ("No permit info to show -- run with --include-approach (or "
                "--permits, which implies it) so trips have a trailhead.")

    lines = []
    for r in rows:
        suffix = f"  [{r.peak_note}]" if r.peak_note else ""
        lines.append(f"Cluster #{r.cluster_id} -- {r.trailhead}  "
                      f"(trip date {r.trip_date:%Y-%m-%d}){suffix}")
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
        lines.append("")
    lines.append(
        "Permit rules and dates change year to year -- verify against the "
        "linked official source before relying on any date above. Interagency "
        "reciprocity assumes one continuous trip that starts and ends at the "
        "listed trailhead -- a fresh trip starting inside the neighboring "
        "wilderness/park still needs its own permit."
    )
    return "\n".join(lines)
