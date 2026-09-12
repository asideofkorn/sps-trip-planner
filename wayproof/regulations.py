"""Rules that govern what you may do once you hold a permit.

``data/permits.csv`` answers *how do I get and keep a permit* -- quota, release
dates, fees, cancellation, what makes the document valid. This module answers
the separate question of *what rules apply while I'm out there*: fire, food
storage, waste, pets, stock, group size, and so on.

Splitting them apart fixed a real problem rather than a theoretical one. The
California Campfire Permit requirement is state law (PRC 4433), restated by
every forest, and it had been copy-pasted into seven ``permits.csv`` rows --
which promptly drifted. Five of the seven described it as covering a "stove"
when it actually covers campfires, stoves, lanterns and barbeques; they
offered three different URLs between them; and none carried the 18-and-over
signer requirement or the legal citation. A fact asserted in seven places is
a fact maintained in none of them.

So a regulation is stored once and *inherited*, via ``scope_type``:

- ``jurisdiction`` -- state law, applying to every permit group in that state
  (``scope_value`` matches ``PermitRule.jurisdiction``)
- ``agency`` -- a forest- or park-wide rule (matches ``PermitRule.agency``)
- ``permit_group`` -- specific to one permit product

``regulations_for`` resolves all three layers for a given permit group. The
jurisdiction layer is why ``permits.csv`` carries an explicit ``jurisdiction``
column even though every group in the dataset is currently Californian: "all
our groups are in California" is true today by coincidence of coverage, and
inheriting statewide law off that coincidence would break silently the first
time a Nevada or Oregon group is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

JURISDICTION = "jurisdiction"
AGENCY = "agency"
PERMIT_GROUP = "permit_group"
_VALID_SCOPES = {JURISDICTION, AGENCY, PERMIT_GROUP}

# Ordered for presentation: the ones that carry a fine or ruin a trip first.
CATEGORY_ORDER = [
    "fire", "food_storage", "group_size", "camping", "waste", "water",
    "fishing", "pets", "stock", "weapons", "aircraft", "natural_features",
    "commercial",
]

CATEGORY_LABELS = {
    "fire": "Fire",
    "food_storage": "Food storage",
    "group_size": "Group size",
    "camping": "Camping",
    "waste": "Waste",
    "water": "Water",
    "fishing": "Fishing",
    "pets": "Pets",
    "stock": "Stock and livestock",
    "weapons": "Firearms",
    "aircraft": "Drones and aircraft",
    "natural_features": "Natural features",
    "commercial": "Commercial use",
}


@dataclass
class Regulation:
    """One row of ``data/regulations.csv``."""

    regulation_id: str
    scope_type: str
    scope_value: str
    category: str
    summary: str
    detail: str = ""
    citation: str = ""
    source_url: str = ""
    source_last_updated: str = ""
    verified_date: str = ""
    scope_display: str = ""
    """How to name this rule's scope to a reader, when the key isn't readable.

    ``scope_value`` is a matching key, not prose: an agency scope reads
    ``eldorado_nf``. Set this to ``Eldorado National Forest`` and the surfaces
    show that instead.
    """

    @property
    def inherited(self) -> bool:
        """True when this rule comes from state law or an agency-wide policy
        rather than from the permit product itself."""
        return self.scope_type != PERMIT_GROUP

    @property
    def scope_label(self) -> str:
        if self.scope_type == JURISDICTION:
            return f"{self.scope_display or self.scope_value} state law"
        if self.scope_type == AGENCY:
            return self.scope_display or self.scope_value
        return "this permit"


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def load_regulations(path: str | Path = "data/regulations.csv") -> List[Regulation]:
    """Load every regulation, in file order.

    Returns an empty list if the file doesn't exist -- regulations are layered
    context on top of a permit lookup, not required input for one.
    """
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)

    out: List[Regulation] = []
    for _, row in df.iterrows():
        regulation_id = _str_field(row, "regulation_id")
        if not regulation_id:
            continue
        scope_type = _str_field(row, "scope_type")
        if scope_type not in _VALID_SCOPES:
            raise ValueError(
                f"Invalid scope_type {scope_type!r} for {regulation_id!r}; "
                f"expected one of {sorted(_VALID_SCOPES)}"
            )
        out.append(Regulation(
            regulation_id=regulation_id,
            scope_type=scope_type,
            scope_value=_str_field(row, "scope_value"),
            category=_str_field(row, "category"),
            summary=_str_field(row, "summary"),
            detail=_str_field(row, "detail"),
            citation=_str_field(row, "citation"),
            source_url=_str_field(row, "source_url"),
            source_last_updated=_str_field(row, "source_last_updated"),
            verified_date=_str_field(row, "verified_date"),
            scope_display=_str_field(row, "scope_display"),
        ))
    return out


def regulations_for(
    regulations: Sequence[Regulation],
    permit_group: str = "",
    agency: "str | Sequence[str]" = "",
    jurisdiction: str = "",
) -> List[Regulation]:
    """Every regulation applying to one permit group, all three scopes resolved.

    Ordered by :data:`CATEGORY_ORDER`, then by how specific the rule is, so a
    wilderness's own fire ban reads before the statewide permit requirement it
    sits on top of. Unknown categories sort last rather than being dropped.

    ``agency`` takes one key or several. Pass ``PermitRule.agency_ids``, never
    ``PermitRule.agency`` -- the latter is a display string. Several because a
    wilderness can be co-managed, as Desolation is by Eldorado NF and the Lake
    Tahoe Basin Management Unit; a rule from either manager applies.
    """
    agencies = {agency} if isinstance(agency, str) else set(agency)
    agencies.discard("")

    def applies(reg: Regulation) -> bool:
        if reg.scope_type == PERMIT_GROUP:
            return bool(permit_group) and reg.scope_value == permit_group
        if reg.scope_type == AGENCY:
            return reg.scope_value in agencies
        return bool(jurisdiction) and reg.scope_value == jurisdiction

    specificity = {PERMIT_GROUP: 0, AGENCY: 1, JURISDICTION: 2}

    def sort_key(reg: Regulation):
        category_rank = (CATEGORY_ORDER.index(reg.category)
                         if reg.category in CATEGORY_ORDER else len(CATEGORY_ORDER))
        return (category_rank, specificity.get(reg.scope_type, 3), reg.regulation_id)

    return sorted((r for r in regulations if applies(r)), key=sort_key)


def group_by_category(regulations: Sequence[Regulation]) -> List[tuple]:
    """``[(label, [Regulation, ...]), ...]`` in :data:`CATEGORY_ORDER`."""
    grouped: dict = {}
    for reg in regulations:
        grouped.setdefault(reg.category, []).append(reg)
    return [
        (CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize()),
         grouped[category])
        for category in sorted(
            grouped,
            key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else len(CATEGORY_ORDER),
        )
    ]
