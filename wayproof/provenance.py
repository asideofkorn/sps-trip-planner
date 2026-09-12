"""Who is allowed to answer which question, and whether their answer is current.

Every other table here records *what* a source said. This one records *whose
claim it was to make*, because reconciling two official sources turned out to
need three separate judgements and only one of them was ever written down.

**Authority is per topic, not a ranking.** The Forest Service regulates; when
it says a day-use permit is needed only in quota season, that settles it.
Recreation.gov is the booking system; when it says the fee tier is $10 for
2-14 nights, that settles it, because it is the thing that charges you. Neither
outranks the other globally. :data:`TOPICS` names the claim types and
``Source.regulates`` says which each publisher owns.

**A deferral is observed, not asserted.** Rather than declaring the Forest
Service authoritative, watch for a publisher declining a question: recreation.gov's
own permit page says a day use permit comes "from a local Forest Service
office", handing the question back. ``data/source_deferrals.csv`` records those
with the sentence that establishes them. A deferral is far stronger evidence
than an opinion about who ought to win, and it ages honestly -- if the wording
changes, the evidence no longer matches.

Not every outbound link is a deferral. The same page links a 2022 trip-planning
guide, which endorses a document rather than handing over a question, and
inherits that document's staleness instead of transferring authority. Telling
the two apart needs the sentence, not the URL, which is why deferrals are
recorded by hand with their evidence rather than scraped.

**A source that contradicts itself is checked before anyone is ranked.** This
was learned the expensive way. Desolation's day-use conflict was resolved by
ranking the forest above the booking platform -- correctly, but unnecessarily.
recreation.gov's overview says a permit is required for day visits year-round
while its own operational section says day use permits come from a Forest
Service office "or at trailheads in the summer". It disagreed with itself, and
had already told us which of its statements not to trust. Same for the Carson
Pass site count, where one document says 13 and its own breakdown sums to 14.
Two of three conflicts that week were self-contradictions wearing the costume
of a cross-source dispute, so :data:`INTERNAL_FIRST` runs before any ranking.

**Authority and currency are different axes and can point opposite ways.** The
governing body can be stale: two permit rows here rest on Forest Service pages
last updated in 2021. A stale regulator page is exactly how a superseded rule
survives online, so when the more authoritative source is materially older than
the less authoritative one, :func:`resolve` refuses to pick. That is a real
open question, not a tie to be broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

# -- claim topics -----------------------------------------------------------
REGULATION = "regulation"            # what you may do on the ground
PERMIT_REQUIREMENT = "permit_requirement"  # whether and when a permit is needed
BOOKING_MECHANICS = "booking_mechanics"    # release windows, changes, cancellation
FEES = "fees"                        # what is actually charged
AVAILABILITY = "availability"        # quota counts and calendars
ACCESS = "access"                    # trailheads, roads, conditions

TOPICS = (REGULATION, PERMIT_REQUIREMENT, BOOKING_MECHANICS, FEES, AVAILABILITY, ACCESS)

# -- source roles -----------------------------------------------------------
REGULATOR = "regulator"
BOOKING_PLATFORM = "booking_platform"
SECONDARY = "secondary"
_VALID_ROLES = {REGULATOR, BOOKING_PLATFORM, SECONDARY}

# -- resolution rules, in the order they are tried --------------------------
INTERNAL_FIRST = "internal-contradiction"
DEFERRAL = "deferral"
ROLE = "topic-authority"
RECENCY = "recency"
UNRESOLVED_STALE_AUTHORITY = "unresolved-stale-authority"
UNRESOLVED = "unresolved"

#: A source page older than this is treated as possibly superseded. Two years
#: is long enough that a season, a fee or a quota has plausibly changed without
#: the page being touched.
STALE_DAYS = 730

#: How much older the more authoritative source may be before its authority
#: stops settling the question on its own.
MATERIALLY_OLDER_DAYS = 365


@dataclass
class Source:
    """One publisher whose pages this project cites."""

    source_id: str
    publisher: str
    url_prefix: str
    role: str
    regulates: tuple = ()
    """Topics this publisher owns. Empty means it owns none -- a secondary
    source repeats other people's claims and settles nothing."""
    notes: str = ""

    def owns(self, topic: str) -> bool:
        return topic in self.regulates


@dataclass
class Deferral:
    """One publisher observed handing a question to another.

    ``evidence`` is the sentence that does it. Without the sentence this is an
    opinion about who ought to win; with it, it is a quotable fact that stops
    being true if the wording changes.
    """

    from_source: str
    to_source: str
    topic: str
    evidence: str
    evidence_url: str = ""
    observed_date: str = ""


@dataclass
class Claim:
    """A stored answer, with where it came from -- the unit :func:`resolve` compares."""

    topic: str
    source_url: str
    source_last_updated: str = ""
    self_contradictory: bool = False
    """True when the cited source disagrees with itself on this topic."""
    label: str = ""


@dataclass
class Resolution:
    """Which claim stands, under which rule, and why."""

    winner: Optional[Claim]
    rule: str
    reason: str

    @property
    def settled(self) -> bool:
        return self.winner is not None


def _str_field(row, col: str) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def _split(value: str) -> tuple:
    return tuple(p.strip() for p in value.split(";") if p.strip())


def load_sources(path: str | Path = "data/sources.csv") -> List[Source]:
    """Load the source registry, in file order. Missing file yields ``[]``."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    out: List[Source] = []
    for _, row in df.iterrows():
        source_id = _str_field(row, "source_id")
        if not source_id:
            continue
        role = _str_field(row, "role")
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role {role!r} for {source_id!r}; "
                             f"expected one of {sorted(_VALID_ROLES)}")
        regulates = _split(_str_field(row, "regulates"))
        unknown = [t for t in regulates if t not in TOPICS]
        if unknown:
            raise ValueError(f"Unknown topic(s) {unknown} for {source_id!r}; "
                             f"expected from {list(TOPICS)}")
        out.append(Source(source_id=source_id, publisher=_str_field(row, "publisher"),
                          url_prefix=_str_field(row, "url_prefix"), role=role,
                          regulates=regulates, notes=_str_field(row, "notes")))
    return out


def load_deferrals(path: str | Path = "data/source_deferrals.csv") -> List[Deferral]:
    """Load observed deferrals, in file order. Missing file yields ``[]``."""
    path = Path(path)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    out: List[Deferral] = []
    for _, row in df.iterrows():
        evidence = _str_field(row, "evidence")
        if not evidence:
            # A deferral with no quoted sentence is an assertion, not an
            # observation, and is exactly what this table exists to avoid.
            continue
        out.append(Deferral(
            from_source=_str_field(row, "from_source"),
            to_source=_str_field(row, "to_source"),
            topic=_str_field(row, "topic"),
            evidence=evidence,
            evidence_url=_str_field(row, "evidence_url"),
            observed_date=_str_field(row, "observed_date"),
        ))
    return out


def source_for(url: str, sources: Sequence[Source]) -> Optional[Source]:
    """The registry entry whose ``url_prefix`` best matches ``url``.

    Longest prefix wins, so a specific section can be registered separately
    from the domain it sits on. Returns ``None`` for an unregistered URL, which
    ``open_questions()`` reports rather than silently treating as trustworthy.
    """
    if not url:
        return None
    matches = [s for s in sources if s.url_prefix and url.startswith(s.url_prefix)]
    return max(matches, key=lambda s: len(s.url_prefix)) if matches else None


def deferral_for(source_id: str, topic: str,
                 deferrals: Sequence[Deferral]) -> Optional[Deferral]:
    """The deferral by which ``source_id`` hands ``topic`` to someone else."""
    for d in deferrals:
        if d.from_source == source_id and d.topic == topic:
            return d
    return None


def age_days(source_last_updated: str, today: Optional[date] = None) -> Optional[int]:
    """Days since the source's own last-updated date, or ``None`` if undatable.

    A bare year is a document stamp rather than a page date and cannot be
    compared with a full date, so it is treated as undatable.
    """
    if not source_last_updated or len(source_last_updated) != 10:
        return None
    try:
        stamped = date.fromisoformat(source_last_updated)
    except ValueError:
        return None
    return ((today or date.today()) - stamped).days


def resolve(topic: str, a: Claim, b: Claim, sources: Sequence[Source],
            deferrals: Sequence[Deferral] = (), today: Optional[date] = None) -> Resolution:
    """Decide between two claims on the same topic, or decline to.

    The rules, in order:

    1. **Self-contradiction first.** A source disagreeing with itself has
       already told you not to trust its blanket statement; the other claim
       stands without anyone being ranked.
    2. **Observed deferral.** If one source has handed this topic to the
       other in its own words, that is the answer.
    3. **Topic authority**, unless the authoritative source is materially
       older -- a stale regulator page is how a superseded rule survives, so
       that combination is left open rather than broken by rank.
    4. **Recency**, for two sources of equal standing.
    5. Otherwise unresolved, which is a real answer and not a failure.
    """
    if a.self_contradictory != b.self_contradictory:
        winner = b if a.self_contradictory else a
        loser = a if a.self_contradictory else b
        return Resolution(winner, INTERNAL_FIRST, (
            f"{loser.label or loser.source_url} contradicts itself on {topic}, so its "
            "blanket statement settles nothing and no ranking is needed."))

    # Which claim is the owner's, and on what evidence. A deferral is stronger
    # than a role assignment, because the publisher said it rather than us.
    src_a, src_b = source_for(a.source_url, sources), source_for(b.source_url, sources)
    owner = weak = owner_src = weak_src = None
    rule = evidence = ""
    if src_a and src_b and src_a.source_id != src_b.source_id:
        d_a = deferral_for(src_a.source_id, topic, deferrals)
        d_b = deferral_for(src_b.source_id, topic, deferrals)
        if d_a and d_a.to_source == src_b.source_id:
            owner, weak, owner_src, weak_src, rule = b, a, src_b, src_a, DEFERRAL
            evidence = (f"{src_a.publisher} hands {topic} to {src_b.publisher}: "
                        f"\u201c{d_a.evidence}\u201d")
        elif d_b and d_b.to_source == src_a.source_id:
            owner, weak, owner_src, weak_src, rule = a, b, src_a, src_b, DEFERRAL
            evidence = (f"{src_b.publisher} hands {topic} to {src_a.publisher}: "
                        f"\u201c{d_b.evidence}\u201d")
        elif src_a.owns(topic) != src_b.owns(topic):
            if src_a.owns(topic):
                owner, weak, owner_src, weak_src = a, b, src_a, src_b
            else:
                owner, weak, owner_src, weak_src = b, a, src_b, src_a
            rule = ROLE
            evidence = f"{owner_src.publisher} owns {topic}; {weak_src.publisher} does not."

    if owner is not None:
        # Authority and currency are separate axes, so establishing who owns
        # the question does not establish that their page is current. A stale
        # page from the owner is exactly how a superseded rule survives online,
        # and that applies just as much when they were handed the question.
        age_owner = age_days(owner.source_last_updated, today)
        age_weak = age_days(weak.source_last_updated, today)
        if age_owner is not None and age_weak is not None and \
                age_owner - age_weak > MATERIALLY_OLDER_DAYS:
            return Resolution(None, UNRESOLVED_STALE_AUTHORITY, (
                f"{owner_src.publisher} owns {topic} but its page is {age_owner - age_weak} "
                f"days older than {weak_src.publisher}'s. A stale page from the owner is how a "
                "superseded rule survives online, so authority alone does not settle this."))
        return Resolution(owner, rule, evidence)

    age_a, age_b = age_days(a.source_last_updated, today), age_days(b.source_last_updated, today)
    if age_a is not None and age_b is not None and age_a != age_b:
        newer = a if age_a < age_b else b
        return Resolution(newer, RECENCY,
                          "Equal standing on this topic, so the more recently updated source wins.")

    return Resolution(None, UNRESOLVED, (
        "Equal standing and no usable dates to separate them. Needs a first-hand check, "
        "not a tie-break."))
