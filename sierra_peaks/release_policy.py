"""Structured, computable permit release rules.

Historically, the mechanics of *when* a permit's reservation inventory
actually becomes available lived only as prose in ``permits.csv``'s
``reservation_method`` column (e.g. "60% ... reservable ... starting 6 months
... before entry ... remaining 40% released 2 weeks before entry"), with only
the *first* release date ever computed -- the second phase existed only as a
sentence a human had to read, never as a date the tool itself could act on.

``data/release_policies.csv`` records each permit_group's release cycle as an
ordered list of phases instead: one row per dated event, with an explicit
``mechanism`` describing what kind of event it is. Loaded via
:func:`load_release_policies` and attached to each :class:`~sierra_peaks.permits.PermitRule`
via ``load_permits``, this lets :func:`sierra_peaks.permits.permit_status`
compute every phase's actual date generically instead of special-casing each
permit_group's mechanics in Python.

Four mechanisms cover every phase seen in this dataset:

- ``reservation`` -- opens at a computed date (from ``offset_days`` before the
  trip, or a fixed ``fixed_month_day`` each year) and is then first-come
  online. A permit_group can have more than one ``reservation`` phase (e.g.
  Inyo NF's 60% at 6 months, 40% at 2 weeks) -- each with its own
  ``allocation_pct``.
- ``lottery_annual`` -- a fixed calendar-date phase (``fixed_month_day``) that
  recurs every year regardless of the trip date, e.g. Mount Whitney Zone's
  Feb 1 - Mar 1 application window. A group's ``lottery_annual`` phases should
  include ``apply_start`` and ``apply_end`` labels at minimum.
- ``walkup`` -- issued in person, day-of, first-come, no advance reservation.
- ``contact_required`` -- not self-issue and not walk-up; call or email the
  agency directly (see ``notes`` for how).

A phase can be scoped to ``season`` = ``"in_season"`` or ``"off_season"``
when a permit_group's mechanics genuinely differ depending on whether the
trip date falls in its quota season (e.g. Mount Whitney Zone's annual lottery
only governs in-season trips; a winter trip uses a completely different,
simpler reservation mechanism). Leave ``season`` blank when a phase applies
regardless.

Not every permit_group is migrated here. Yosemite's weekly lottery cycle is
deliberately left on its own special-cased logic in
:mod:`sierra_peaks.permits` -- its own source is explicit that exact
per-area reservation dates come from a downloadable dataset that hasn't been
retrieved, so forcing weekday-precise computed dates onto an already-fuzzy
source would manufacture false precision rather than remove it. A
permit_group simply absent from this file falls back to the older, coarser
single-offset logic.

This intentionally never fabricates a date. When a source states an
allocation split without a specific release offset (e.g. Sierra NF's
remaining ~40% "released for shorter-notice/walk-up-style booking", with no
exact day given), that phase's ``offset_days`` and ``fixed_month_day`` are
both left blank -- :meth:`ReleasePhase.event_date` returns ``None`` rather
than guessing, and the caller must fall back to the phase's ``notes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

RESERVATION = "reservation"
LOTTERY_ANNUAL = "lottery_annual"
WALKUP = "walkup"
CONTACT_REQUIRED = "contact_required"
_VALID_MECHANISMS = {RESERVATION, LOTTERY_ANNUAL, WALKUP, CONTACT_REQUIRED}

IN_SEASON = "in_season"
OFF_SEASON = "off_season"
_VALID_SEASONS = {"", IN_SEASON, OFF_SEASON}


@dataclass
class ReleasePhase:
    """One row of ``data/release_policies.csv``: one dated event in a permit
    group's release cycle."""

    permit_group: str
    phase_order: int
    mechanism: str
    season: str = ""  # "", "in_season", or "off_season"
    offset_days: Optional[int] = None
    fixed_month_day: Optional[Tuple[int, int]] = None
    time_of_day: str = ""
    timezone: str = ""
    allocation_pct: Optional[float] = None
    label: str = ""
    notes: str = ""

    def event_date(self, trip_date: date) -> Optional[date]:
        """This phase's actual calendar date for a given trip.

        ``None`` when the source gives no exact offset (see module docstring)
        -- callers must not invent a date in that case.
        """
        if self.fixed_month_day:
            month, day = self.fixed_month_day
            return date(trip_date.year, month, day)
        if self.offset_days is not None:
            return trip_date - timedelta(days=self.offset_days)
        return None


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _parse_mmdd(value) -> Optional[Tuple[int, int]]:
    if pd.isna(value) or not str(value).strip():
        return None
    month, day = str(value).strip().split("-")
    return (int(month), int(day))


def _int_or_none(value) -> Optional[int]:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return int(value)


def _float_or_none(value) -> Optional[float]:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return float(value)


def load_release_policies(
    path: str | Path = "data/release_policies.csv",
) -> Dict[str, List[ReleasePhase]]:
    """Load structured permit release phases, grouped by permit_group and ordered.

    Returns an empty dict if the file doesn't exist. A permit_group with no
    phases here simply hasn't been migrated off the older generic
    reservation-window fallback in :func:`sierra_peaks.permits.permit_status`.
    """
    path = Path(path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)

    by_group: Dict[str, List[ReleasePhase]] = {}
    for _, row in df.iterrows():
        group = _str_field(row, "permit_group")
        if not group:
            continue
        mechanism = _str_field(row, "mechanism")
        if mechanism not in _VALID_MECHANISMS:
            raise ValueError(
                f"Invalid release mechanism {mechanism!r} for {group!r}; "
                f"expected one of {sorted(_VALID_MECHANISMS)}"
            )
        season = _str_field(row, "season")
        if season not in _VALID_SEASONS:
            raise ValueError(
                f"Invalid season {season!r} for {group!r}; expected one of "
                f"{sorted(s for s in _VALID_SEASONS if s) + ['(blank)']}"
            )
        by_group.setdefault(group, []).append(ReleasePhase(
            permit_group=group,
            phase_order=int(row["phase_order"]),
            mechanism=mechanism,
            season=season,
            offset_days=_int_or_none(row.get("offset_days")),
            fixed_month_day=_parse_mmdd(row.get("fixed_month_day")),
            time_of_day=_str_field(row, "time_of_day"),
            timezone=_str_field(row, "timezone"),
            allocation_pct=_float_or_none(row.get("allocation_pct")),
            label=_str_field(row, "label"),
            notes=_str_field(row, "notes"),
        ))

    for phases in by_group.values():
        phases.sort(key=lambda p: p.phase_order)
    return by_group
