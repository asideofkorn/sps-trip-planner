"""Linking a stored claim to the verification events behind it.

``data/permit_source_log.csv`` has always recorded *why* this project believes
things. What it could not do is tell you which belief a given entry supports,
or which entries stand behind a given claim. The log was a diary, not an index,
so a reader who doubted one sentence on a page had no way to reach the evidence
for that sentence, and a maintainer who found a source had changed had no way
to learn which rows depended on it.

Both are the same missing edge, traversed in opposite directions:

- **Forward**, for a reader: claim -> entries -> sources. "Where does this come
  from, and is anyone arguing about it?"
- **Backward**, for ingestion: source URL -> entries -> claims. "This page
  changed overnight. What do I have to re-check?"

So every log entry now carries a stable ``entry_id`` (``group-date-seq``,
sayable out loud and sortable), and a claim cites the ids that established it.
:func:`evidence_for` walks forward, :func:`claims_citing_url` walks back.

The status a claim gets is deliberately three-valued rather than a boolean.
``SETTLED`` means verified with nothing open against it. ``CONTESTED`` means a
cited entry belongs to a conflict still open, so the value is this project's
best pick and a reader should know that before acting. ``UNVERIFIED`` means no
entry is cited at all, which is different from "checked and fine" and must not
render as if it were. A fourth state is folded into ``SETTLED`` on purpose: a
claim whose conflict was opened and then closed is settled, but
:attr:`ClaimEvidence.closed_conflicts` keeps the argument visible, because "we
considered this and resolved it" is more reassuring to a sceptical reader than
silence, and more useful to the next maintainer than a clean slate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .permits import SourceLogEntry, open_conflicts
from .provenance import Source, source_for

SETTLED = "settled"
CONTESTED = "contested"
UNVERIFIED = "unverified"

_STATUS_LABELS = {
    SETTLED: "Verified",
    CONTESTED: "Sources disagree",
    UNVERIFIED: "Not independently verified",
}


def parse_ids(value: str) -> tuple:
    """``"a; b"`` -> ``("a", "b")``. Blank yields ``()``."""
    return tuple(p.strip() for p in str(value or "").split(";") if p.strip())


@dataclass
class CitedEntry:
    """One verification event behind a claim, resolved for display."""

    entry_id: str
    date_checked: str
    verdict: str
    source_url: str
    publisher: str = ""
    conflict_id: str = ""
    conflict_kind: str = ""
    conflict_open: bool = False
    summary: str = ""

    @property
    def headline(self) -> str:
        """One line a person can read without opening anything."""
        who = self.publisher or self.source_url or "unrecorded source"
        if self.conflict_id:
            state = "still open" if self.conflict_open else "resolved"
            return f"{self.date_checked} · {who} · {self.conflict_id} ({state})"
        return f"{self.date_checked} · {who} · {self.verdict}"


@dataclass
class ClaimEvidence:
    """Everything known about where one stored claim came from."""

    status: str
    entries: List[CitedEntry] = field(default_factory=list)
    missing_ids: tuple = ()
    """Cited ids with no matching log entry -- a dangling citation, which is
    worse than none because it looks like evidence."""

    @property
    def label(self) -> str:
        return _STATUS_LABELS.get(self.status, self.status)

    @property
    def open_conflicts(self) -> List[CitedEntry]:
        return [e for e in self.entries if e.conflict_open]

    @property
    def closed_conflicts(self) -> List[CitedEntry]:
        return [e for e in self.entries if e.conflict_id and not e.conflict_open]

    @property
    def source_urls(self) -> List[str]:
        """Every source behind this claim, first-cited order, de-duplicated."""
        seen: List[str] = []
        for e in self.entries:
            if e.source_url and e.source_url not in seen:
                seen.append(e.source_url)
        return seen

    @property
    def last_checked(self) -> str:
        return max((e.date_checked for e in self.entries), default="")

    def as_dict(self) -> dict:
        """The machine-readable form, published on every JSON page."""
        return {
            "status": self.status,
            "label": self.label,
            "last_checked": self.last_checked,
            "sources": self.source_urls,
            "entries": [
                {"entry_id": e.entry_id, "date_checked": e.date_checked,
                 "verdict": e.verdict, "source_url": e.source_url,
                 "publisher": e.publisher, "conflict_id": e.conflict_id,
                 "conflict_kind": e.conflict_kind, "conflict_open": e.conflict_open}
                for e in self.entries
            ],
            "open_conflicts": [e.conflict_id for e in self.open_conflicts],
            "resolved_conflicts": [e.conflict_id for e in self.closed_conflicts],
            "dangling_citations": list(self.missing_ids),
        }


def index_log(log: Sequence[SourceLogEntry]) -> Dict[str, SourceLogEntry]:
    """``{entry_id: entry}``, skipping entries that predate stable ids."""
    return {e.entry_id: e for e in log if e.entry_id}


def evidence_for(cited: str | Sequence[str], log: Sequence[SourceLogEntry],
                 sources: Sequence[Source] = ()) -> ClaimEvidence:
    """Walk a claim's citations forward to its sources and their arguments.

    ``cited`` takes the raw ``"a; b"`` cell or an already-split sequence.
    """
    ids = parse_ids(cited) if isinstance(cited, str) else tuple(cited)
    if not ids:
        return ClaimEvidence(status=UNVERIFIED)

    by_id = index_log(log)
    live = {(c.permit_group, c.conflict_id) for c in open_conflicts(log)}

    entries: List[CitedEntry] = []
    missing: List[str] = []
    for entry_id in ids:
        entry = by_id.get(entry_id)
        if entry is None:
            missing.append(entry_id)
            continue
        src = source_for(entry.source_url, sources) if sources else None
        entries.append(CitedEntry(
            entry_id=entry.entry_id,
            date_checked=entry.date_checked,
            verdict=entry.verdict,
            source_url=entry.source_url,
            publisher=src.publisher if src else "",
            conflict_id=entry.conflict_id,
            conflict_kind=entry.conflict_kind,
            conflict_open=bool(entry.conflict_id)
                and (entry.permit_group, entry.conflict_id) in live,
            summary=entry.summary,
        ))

    if not entries:
        # Every citation dangled. Claiming verification on ids that resolve to
        # nothing is worse than claiming none.
        return ClaimEvidence(status=UNVERIFIED, missing_ids=tuple(missing))
    status = CONTESTED if any(e.conflict_open for e in entries) else SETTLED
    return ClaimEvidence(status=status, entries=entries, missing_ids=tuple(missing))


def entries_for_url(url: str, log: Sequence[SourceLogEntry]) -> List[SourceLogEntry]:
    """Every logged check of one source URL, oldest first."""
    return [e for e in log if e.source_url == url]


def claims_citing_url(url: str, log: Sequence[SourceLogEntry],
                      claims: Sequence[tuple]) -> List[str]:
    """The claims that would need re-checking if ``url`` changed.

    This is the edge that makes ingestion actionable. A diff on a watched page
    is only useful if it can name the rows that depend on it, and without the
    claim-to-entry citations the only honest answer was "something, somewhere".

    ``claims`` is ``[(claim_key, cited_ids), ...]`` -- whatever the caller
    considers a claim, so permits, regulations and future tables can all be
    passed in together.
    """
    touched = {e.entry_id for e in entries_for_url(url, log) if e.entry_id}
    if not touched:
        return []
    out: List[str] = []
    for key, cited in claims:
        ids = parse_ids(cited) if isinstance(cited, str) else tuple(cited)
        if touched.intersection(ids):
            out.append(key)
    return out


def dangling_citations(log: Sequence[SourceLogEntry],
                       claims: Sequence[tuple]) -> List[tuple]:
    """``[(claim_key, bad_id), ...]`` for citations naming no real entry."""
    known = set(index_log(log))
    out: List[tuple] = []
    for key, cited in claims:
        ids = parse_ids(cited) if isinstance(cited, str) else tuple(cited)
        out.extend((key, i) for i in ids if i not in known)
    return out
