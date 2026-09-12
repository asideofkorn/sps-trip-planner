"""Crowd-reported mobile coverage for a permit area.

This is the first dataset here whose source is a *crowd* rather than an
agency, and it is kept separate for that reason. Every other table in this
project answers "what does the managing agency say"; this one answers "what
do several hundred visitors report", which is a different kind of claim and
must never be rendered as if it were the first kind.

Three things about the shape of the data drive the design:

**It is attached to a permit area, not to a point.** recreation.gov publishes
the rating against the permit product, so the honest scope is the permit
group. Signal inside a wilderness varies by ridge, drainage and aspect far
more than it varies between wildernesses, so a single number for Desolation
cannot predict the bar count at any particular lake. It answers a coarser
and more useful question: should I plan as though I will be out of contact?

**The numeric rating has no stated scale.** The page shows "0.8 - Major
Issues" beside a five-bar icon with one bar filled, and states neither the
maximum nor how the average is computed. So :attr:`Coverage.rating_label` is
the interpretable field and the number is recorded as-is, with
:attr:`rating_scale_known` false until a source states it. Rendering the raw
number as a fraction of five would be inventing precision.

**A carrier with reports but no rating on file is a gap, not an absence.**
recreation.gov lists several carriers; a screenshot may cut off below the
first. A row with a ``sample_size`` and no ``rating`` says "this exists and
we have not read it", which ``open_questions()`` surfaces, rather than
letting silence imply no data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

PERMIT_GROUP = "permit_group"


@dataclass
class Coverage:
    """One carrier's crowd-reported coverage for one area."""

    area_type: str
    area_id: str
    carrier: str
    rating: Optional[float] = None
    rating_label: str = ""
    """The page's own words for the rating, e.g. ``"Major Issues"``."""
    sample_size: Optional[int] = None
    rating_scale_known: bool = False
    """False while no source states what the rating is out of."""
    source_url: str = ""
    verified_date: str = ""
    notes: str = ""

    @property
    def unread(self) -> bool:
        """True when the area has reports on file whose rating we haven't read."""
        return self.rating is None

    @property
    def display(self) -> str:
        """How to state this to a reader, without inventing a denominator."""
        if self.unread:
            return f"{self.carrier}: rating not read ({self.sample_size or 0} reports on file)"
        label = f" ({self.rating_label})" if self.rating_label else ""
        scale = f"{self.rating:g}" if self.rating_scale_known else f"{self.rating:g}, scale unstated"
        return f"{self.carrier}: {scale}{label}"


def _opt_float(row, col: str) -> Optional[float]:
    val = row.get(col)
    if val is None or pd.isna(val) or str(val).strip() == "":
        return None
    return float(val)


def _opt_int(row, col: str) -> Optional[int]:
    val = _opt_float(row, col)
    return None if val is None else int(val)


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def load_connectivity(path: str | Path = "data/connectivity.csv") -> List[Coverage]:
    """Load crowd-reported coverage, in file order.

    Returns an empty list if the file doesn't exist -- coverage is advisory
    context, never required for a permit lookup.
    """
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    out: List[Coverage] = []
    for _, row in df.iterrows():
        carrier = _str_field(row, "carrier")
        if not carrier:
            continue
        out.append(Coverage(
            area_type=_str_field(row, "area_type"),
            area_id=_str_field(row, "area_id"),
            carrier=carrier,
            rating=_opt_float(row, "rating"),
            rating_label=_str_field(row, "rating_label"),
            sample_size=_opt_int(row, "sample_size"),
            rating_scale_known=str(_str_field(row, "rating_scale_known")).lower()
                in {"true", "yes", "1"},
            source_url=_str_field(row, "source_url"),
            verified_date=_str_field(row, "verified_date"),
            notes=_str_field(row, "notes"),
        ))
    return out


def coverage_for(coverage: Sequence[Coverage], permit_group: str) -> List[Coverage]:
    """This permit group's carriers, worst reported coverage first.

    Worst first on purpose: the planning decision this informs is whether to
    carry a satellite communicator, and that is driven by the carrier you
    actually have, not by the best one somebody else has. Carriers whose
    rating hasn't been read sort last, since they support no conclusion.
    """
    if not permit_group:
        return []
    mine = [c for c in coverage
            if c.area_type == PERMIT_GROUP and c.area_id == permit_group]
    return sorted(mine, key=lambda c: (c.unread, c.rating if c.rating is not None else 0,
                                       c.carrier))


def coverage_by_group(coverage: Sequence[Coverage]) -> Dict[str, List[Coverage]]:
    """``{permit_group: [Coverage, ...]}`` for every group with any rows."""
    groups: Dict[str, List[Coverage]] = {}
    for c in coverage:
        if c.area_type == PERMIT_GROUP and c.area_id:
            groups.setdefault(c.area_id, []).append(c)
    return groups
