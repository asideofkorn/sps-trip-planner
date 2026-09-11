"""Peak-specific approach relationships: which named route a peak is climbed
by, and which permit product actually governs that route.

A trailhead's ``permit_group`` (see :mod:`wayproof.permits`) is a useful
default, but it is not a guarantee for every peak reached from that
trailhead. Some trailheads serve more than one named approach, and different
approaches from the same trailhead can fall under different permit products.

Whitney Portal is the clearest example. The classic Mt. Whitney Trail is
subject to the lottery-only Whitney Zone permit. Mount Russell, though
reached from the same trailhead, is commonly climbed via the Mountaineers
Route / North Fork of Lone Pine Creek -- a separate trail that Inyo National
Forest explicitly excludes from the Whitney Zone lottery and instead governs
under the regular Inyo NF wilderness permit.

``data/approaches.csv`` records these peak-specific approach relationships as
first-class, sourced data rather than an opaque peak-name -> permit-group
patch:

- ``status=confirmed`` -- a directly-named source states this peak's real
  approach uses a different permit product than its trailhead's default.
  :func:`~wayproof.permits.clusters_permit_info` emits an extra,
  peak-specific permit entry for these.
- ``status=unconfirmed`` -- a different approach is plausible (for example,
  the dataset's own source-listed trailhead for the peak names a different
  trail than the trailhead's main route) but no source has been found
  confirming which permit product actually governs it. Rather than silently
  assuming the trailhead default applies, or silently omitting the peak,
  these surface as an explicit caution alongside the default permit entry.

This intentionally does not attempt to enumerate every peak's approach --
only the cases where trailhead-default inheritance is known or suspected to
be wrong. A peak absent from this file simply uses its trailhead's default
permit_group, with no caveat.

This is deliberately conservative: a peak should only appear here when there
is a concrete reason (a named alternate trail, a source, or both) to
question the trailhead default. Don't add speculative rows for peaks that
merely share a trailhead with a lottery/special permit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

CONFIRMED = "confirmed"
UNCONFIRMED = "unconfirmed"
_VALID_STATUSES = {CONFIRMED, UNCONFIRMED}


@dataclass
class ApproachRoute:
    """One row of ``data/approaches.csv``: a peak's known (or suspected) approach.

    ``permit_group`` is the permit product this approach is confirmed to use.
    It is blank when ``status`` is ``unconfirmed`` -- the point of an
    unconfirmed row is to flag uncertainty, not to assert an unverified
    answer.
    """

    peak_name: str
    trailhead: str
    approach_name: str
    permit_group: str
    status: str
    source_url: str = ""
    verified_date: str = ""
    notes: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status == CONFIRMED


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def load_approaches(path: str | Path = "data/approaches.csv") -> List[ApproachRoute]:
    """Load known peak-specific approach relationships.

    Returns an empty list if the file doesn't exist -- approaches are opt-in
    extra precision layered on top of a trailhead's default permit_group, not
    a required input.
    """
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    routes: List[ApproachRoute] = []
    for _, row in df.iterrows():
        peak_name = _str_field(row, "peak_name")
        if not peak_name:
            continue
        status = _str_field(row, "status") or CONFIRMED
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid approach status {status!r} for {peak_name!r}; "
                f"expected one of {sorted(_VALID_STATUSES)}"
            )
        routes.append(ApproachRoute(
            peak_name=peak_name,
            trailhead=_str_field(row, "trailhead"),
            approach_name=_str_field(row, "approach_name"),
            permit_group=_str_field(row, "permit_group"),
            status=status,
            source_url=_str_field(row, "source_url"),
            verified_date=_str_field(row, "verified_date"),
            notes=_str_field(row, "notes"),
        ))
    return routes


def approaches_by_peak(routes: Sequence[ApproachRoute]) -> Dict[str, List[ApproachRoute]]:
    """Index approach routes by peak name (a peak may have more than one known approach)."""
    by_peak: Dict[str, List[ApproachRoute]] = {}
    for r in routes:
        by_peak.setdefault(r.peak_name, []).append(r)
    return by_peak
