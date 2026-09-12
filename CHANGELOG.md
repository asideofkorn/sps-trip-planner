# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Scoped regulations** (`data/regulations.csv`, `wayproof/regulations.py`):
  what applies *while you're out there* — fire, food storage, waste, pets,
  stock, group size — separated from `permits.csv`, which answers how you get
  and keep a permit. A regulation is stored once and inherited via
  `scope_type`: `jurisdiction` (state law), `agency` (forest- or park-wide), or
  `permit_group`. `regulations_for()` resolves all three, sorting specific
  before general so a wilderness's own fire ban reads above the statewide rule
  it sits on top of, and both surfaces label inherited rules with their scope.
  - `permits.csv` gains an explicit `jurisdiction` column. Every group in the
    dataset is currently Californian, but that's a coincidence of coverage —
    inheriting statewide law off it would break silently on the first non-CA
    group, so the column states it rather than assuming it. Tested.

### Fixed
- **An agency-scoped regulation inherited to zero permit groups.** The Eldorado
  NF 10-day dispersed-camping limit was scoped to the agency string
  `Eldorado National Forest`, which no permit group carries: `permits.csv`'s
  `agency` column is a display name with ranger-district and co-management
  detail (`Eldorado NF / LTBMU`, `Eldorado NF (Amador Ranger District)`). The
  rule looked filed and applied to nobody — the same failure mode as the
  campfire drift it was meant to fix, one layer up.
  - `permits.csv` gains `agency_id`: a stable matching key beside the prose,
    semicolon-separated because co-management is real (Desolation is jointly
    administered by Eldorado NF and the Lake Tahoe Basin Management Unit, and a
    rule from either applies). `regulations_for()` takes one key or several.
  - `regulations.csv` gains an optional `scope_display`, so a scope matched as
    `eldorado_nf` still reads as "Eldorado National Forest" on both surfaces.
  - A test now asserts every regulation's scope reaches at least one permit
    group, and another asserts the display string does *not* match — a dead
    scope fails the build rather than quietly reading as covered. The rule now
    reaches all three Eldorado groups and appears on 22 trailhead pages.
- **Resolving one conflict silently closed every other conflict on the same
  permit group.** `unresolved_conflicts()` read only each group's most recent
  log entry, so a group could carry at most one live disagreement. Desolation
  opened three in one session (day-use season, fee tier, and the 25-vs-30 ft
  Special Management Area setback) and the limitation bit twice the same day;
  the workaround both times was to log a settled question under a deliberately
  dirty `unresolved-conflict` verdict so the still-open ones stayed visible,
  which does not survive a third. Closing a live conflict is worse than not
  tracking it -- it converts a known unknown into a confident wrong answer.
  - `permit_source_log.csv` gains a `conflict_id` column, and conflicts are now
    tracked per `(permit_group, conflict_id)`. New `open_conflicts()` reports
    each disagreement separately, with when it opened and what the latest entry
    says; `unresolved_conflicts()` stays as a roll-up to the affected groups.
  - Crossing threads never closes anything: an entry naming one `conflict_id`
    leaves the group's others untouched, and an unkeyed entry cannot close a
    keyed one, so a routine fee re-check can't settle an argument about a
    season. Blank ids share one per-group bucket -- the previous behaviour,
    which is still right for a group with one conflict at a time.
  - `open_questions()` now derives a gap per open conflict, so they surface in
    `--open-questions` and on the website instead of only in the source-log
    report. Nine historical rows were keyed retroactively, and an appended
    `corrects-existing` entry closes `desolation-fee-tier` on evidence already
    logged -- the deliberately dirty entry stands unedited, since the log is
    append-only and the workaround is part of the history.
  - `cli.py --open-questions` was also missing `regulations`, so the inherited
    fire-rule gaps never appeared there. Both are now passed.
- **An inherited rule can read as permission.** The statewide campfire rule,
  rendered alone on a page with no local fire rule beside it, said "a permit is
  required for any campfire" and nothing else -- which reads as *campfires are
  allowed here if you have one*. CAL FIRE's own guidance says the opposite: the
  permit is a precondition, and local rules override it. Reworded to say so,
  and `open_questions()` now derives a gap for any group that inherits a
  broader fire rule with no local one on file (currently 10 groups, including
  `whitney_zone` and all three Inyo groups). The absence is stated rather than
  left to imply permission.
- **The California Campfire Permit rule was wrong in five places and
  inconsistent across seven.** It's state law (PRC 4433) restated by every
  forest, and had been copy-pasted into seven `permits.csv` rows, where it
  drifted: five described it as covering a "stove" when it covers campfires,
  stoves, **lanterns and barbeques**; all treated "outside a developed
  campground" as the trigger when the issuing forest says it's also required
  *in some developed campgrounds*; they carried three different URLs between
  them; and none had the 18-and-over signer requirement or the citation
  (36 CFR 261.52(k), PRC 4433). Now stored once, scoped to CA, inherited by all
  15 groups, with a test asserting no permit row restates it.
  - URL corrected too: Eldorado NF's own camping page cites
    `www.preventwildfiresca.org`, which doesn't resolve. The working path is
    `readyforwildfire.org/prevent-wildfire/campfire-safety`, which links
    through to the permit portal at `permit.preventwildfiresca.org` — meaning
    the `gtw_free` row's link was the closest to correct all along.

### Changed
- **Desolation's `notes` field cut from ~3,500 characters to 955.** Its
  wilderness regulations moved to `regulations.csv`; what stays in `permits.csv`
  is permit mechanics — quota season, what makes the permit valid, cancellation
  and change policy, and the unresolved day-use question.
- Added an Eldorado NF-wide rule from its camping page: dispersed camping
  outside a developed campground is capped at 10 days per ranger district per
  calendar year.
- **Destination zones** (`data/permit_zones.csv`, `wayproof/permit_zones.py`), and a
  substantial Desolation Wilderness reconciliation behind them. Desolation's
  quota attaches to *where you go* rather than *where you enter*: you book one
  of 45 numbered destination zones and must spend your first night in it. All
  45 are now recorded, plus the separate "Tahoe Rim Trail (Thru Hike Only)"
  option, which is selectable alongside them but isn't a numbered zone.
  - The count is now corroborated by four independent sources: the
    recreation.gov booking dropdown (2026), the permit page text (2026), the
    USFS trip-planning guide (2022), and the official Eldorado NF zone map
    (2011), whose labels also show the numbering is contiguous 1-45.
  - **Which zone serves a given objective is deliberately not asserted.** Zone
    names frequently match a lake or peak, but a zone is a mapped boundary and
    a name is not that boundary -- and Mount Tallac, the trailhead that
    prompted this work, has no zone named for it at all. Both the HTML and
    agent surfaces state this non-claim explicitly, since an LLM matching
    "Ralston Peak" to zone "45 Ralston" is exactly the inference the data
    doesn't support.

### Fixed
- **`permit_status()` treated release mechanisms as mutually exclusive.** Any
  `walkup` phase short-circuited a permit group to "not reservable in advance,"
  which was fine while every migrated group was homogeneous but is backwards
  for Desolation, where roughly two-thirds of each zone's quota *is* reservable
  online and only the remaining third is same-day. Reservable phases now win
  the dispatch whenever they exist, with the walk-up share appended.
- **Desolation's off-season answer was wrong.** With no `off_season` phase on
  file, `permit_status()` fell back to asserting off-season permits are
  "free/self-issue, no reservation" -- but recreation.gov states they are still
  booked through it, merely bookable and printable on the day of entry. This is
  the *second* group where that assumption proved wrong against a real source
  (Whitney Zone was the first), so `open_questions()` now derives the same gap
  for every remaining quota'd group carrying it (currently `hoover`,
  `inyo_jmw_aaw`, `inyo_gtw`, `sierra_nf`, `seki`) rather than leaving five
  unevidenced claims in place. They're surfaced as questions, not silently
  "fixed" -- each needs its own source check.

### Changed
- **`data/permits.csv`'s `desolation` row substantially corrected and expanded**
  against the live recreation.gov permit page, with five new
  `permit_source_log.csv` entries recording what each source confirmed. Newly
  captured hard requirements that were missing entirely: bear canister required
  with fines up to $5,000 under 36 CFR 261.58(cc); a signed *printed* permit
  must be carried and a reservation confirmation is explicitly not a valid
  permit; permits print starting 7 days before entry; campfires prohibited
  year-round though camp stoves are permitted; the four Special Management
  Areas with designated campsites; the $20 annual pass; and the "exit by the
  last date booked" limit on roaming after the first night.
  - Fees corrected from per-*person* to per-*adult* -- children 12 and under
    are free, an omission that materially over-quoted a family.
  - Two conflicts are recorded as `unresolved-conflict` rather than silently
    resolved: the upper fee tier (2-14 nights per recreation.gov 2026 vs 2-13
    per the 2022 USFS guide), and whether a day-use permit is required
    year-round (recreation.gov and the zone map say yes; Eldorado NF's own
    day-use page says only during quota season -- and that reading came from a
    search snippet rather than a direct fetch, so it explicitly needs a
    first-hand read before anything is changed on it).
- **Trailhead pages on wayproof.dev, led by permit content** (`wayproof/views.py`,
  `wayproof/render.py`): one page per trailhead (88 today), each published in
  three representations from a single view model -- HTML for people,
  Markdown for agents, JSON for programs. Because all three render from the
  same resolved dict, no surface can assert a fact another one doesn't, which
  is the point: a site claiming its facts are sourced and consistent can't
  afford its agent surface to disagree with its human one.
  - Each page leads with the permit that governs *entry* there: agency, quota
    season, fees, reservation mechanics, the `interagency_note` for continuous
    travel into neighbouring units, and the append-only verification history
    from `permit_source_log.csv` -- including entries that record a conflict
    and its later resolution.
  - **Key dates** are computed relative to the build date, in the two honest
    shapes the data supports: fixed-calendar phases (a lottery window) get an
    absolute next date, while rolling-offset phases get the inverse framing --
    which entry date today's booking window covers. A phase whose source
    publishes neither still resolves to no date at all rather than a guess,
    and season-scoped phases say so inline (Whitney Zone's off-season
    reservation is not a fallback for its in-season lottery).
  - `data/approaches.csv`'s sourced route-level exceptions are first-class
    content; `nearest_trailhead` peak lists are explicitly labelled as
    unverified geometric proximity, because permits attach to where you enter
    rather than to whichever summit is closest -- a distinction a long
    point-to-point route (a JMT entry at Happy Isles) makes unavoidable.
  - Site plumbing: shared `/style.css`, `sitemap.xml` (indexable pages only),
    `robots.txt`, `rel=alternate` links, JSON-LD, canonical URLs, and a
    `noindex` gate for pages without a resolved permit rule.
  - `pages.yml` now also rebuilds daily, since date-relative content on a
    push-only build would quietly go stale.
- **First pass at the wayproof.dev website** (`scripts/build_site.py`,
  `.github/workflows/pages.yml`): a static site built and deployed to
  GitHub Pages on every push to `main`. Its "Help us confirm" section is
  generated live from `wayproof.reports.open_questions()` against the
  currently committed data -- there's no separate hand-maintained copy to
  drift out of sync. Each item deep-links to a pre-filled GitHub issue
  (title, question, and target file already filled in) using
  `.github/ISSUE_TEMPLATE/data_report.md`'s fields, closing the loop
  between "here's a gap" and "here's how to tell us" with zero backend and
  one click. Deliberately minimal: this is a first pass to prove the
  DNS -> Pages -> live-data -> report pipeline works end to end before
  investing in real site design/content/requirements.

### Changed
- **Extracted reporting out of `plan.py` into a standalone `report.py`.**
  Reporting isn't planning: a claim isn't tied to a trip date, and its
  target doesn't need to already exist, so forcing every report through
  `plan.py`'s objective/date-resolution flow (including a required `--date`
  that had nothing to do with the claim) was the wrong coupling.
  `report.py submit <target_file> <target_key> <claim>` replaces
  `plan.py ... --report`; new `report.py list` and `report.py resolve
  <report_id> <status>` subcommands give the whole reviewed lifecycle a
  single dedicated tool for the first time, rather than `resolve_report()`
  only being reachable by writing a one-off script. `wayproof-report`
  console-script entry point added alongside `wayproof`/`wayproof-cluster`.
  Built `.github/ISSUE_TEMPLATE/data_report.md` (replacing the older,
  narrower `data_correction.md`), whose fields map directly onto
  `submit_report()`'s parameters and cover confirmation/missing-peak
  reports, not just corrections -- the first of the four documented
  future channels for #7 to actually get built. `CONTRIBUTING.md` and the
  README's "The Scavenger Hunt" section updated accordingly.

### Added
- **`plan` now surfaces facilities data itself, not just its gaps**
  (`PlanResult.facilities`, new `wayproof.plan.FacilitiesInfo`, also in the
  JSON export and a new `Facilities` section in `format_plan_summary()`).
  `python plan.py "Rose Peak" --date ...` now shows the trailhead's water
  sources and their last-checked status, nearby campgrounds (reservation
  method, fee, nightly cutoff), and the park's entrance fee/hours/exemptions
  -- previously only the gaps in that data ("Help us confirm") were shown,
  not the data itself.
  - New `Trailhead.park` field (`data/trailheads.csv` gained a `park`
    column, populated for the two EBRPD trailheads, blank elsewhere): the
    specific park/preserve unit for vehicle-access purposes, distinct from
    `wilderness_area`'s backcountry/permit designation -- a trailhead's
    governing wilderness and its vehicle-access park aren't always the same
    name (Lichen Bark's `wilderness_area` is "Ohlone Wilderness" but its
    `park` is "Del Valle Regional Park"). Links to `data/campgrounds.csv`
    and `data/park_access.csv`'s own `park` columns.
  - This also resolves a previously-documented `open_questions()`
    limitation: campground/campsite/park-access gaps are now peak-filterable
    via the same `Trailhead.park` link, not just visible in the unfiltered
    `--open-questions` view. New park-access confidence heuristic alongside
    it: a `fee_exemptions`/`notes` field containing "verbal" is now flagged
    as an open question (previously undetected -- Del Valle's own verbally-
    confirmed fee exemption should have been caught by this from the start).
  - `resolve_plan()` gained an optional `park_access` parameter; `plan.py`
    gained `--park-access-file`; `cli.py --open-questions` gained
    `--park-access-file` too. All backward compatible.
  - Verified end-to-end against real data: Rose Peak correctly shows 5 Del
    Valle-area campgrounds and Del Valle's park access; Mission Peak shows
    only Eagle Springs and no park-access section (no `park_access.csv` row
    exists for Mission Peak Regional Preserve, and none is fabricated);
    Sierra peaks show no `Facilities` section at all (no `park` link exists
    for any Sierra trailhead).
  - New tests in `tests/test_plan.py`, `tests/test_reports.py`, and
    `tests/test_pipeline.py`. Full suite passes (162/162).
- **Reporting a peak missing entirely, and a real first case (Mount
  Carillon).** `plan.py --report` now works when the objective name doesn't
  resolve at all -- `--target-file` defaults to `data/peaks.csv` in that
  case instead of `unspecified`, since that's exactly how someone reports
  "this peak doesn't exist in the dataset yet" rather than a fact about a
  peak already in it. New `wayproof.reports.format_pending_reports()`, and
  `cli.py --open-questions` now prints the pending-review queue
  (`data/pending_reports.csv`, new `--pending-reports-file` flag) alongside
  the derived gaps, so a submission is visible in the same backlog as
  everything else. Submitted a real report for Mount Carillon -- absent
  from `data/peaks.csv`/`data/collections/sps.csv` entirely, believed to be
  a real SPS peak near Mount Russell but not independently confirmed here
  -- replacing the old plan of the maintainer just adding it directly.
  This is the previously-tracked "add Mount Carillon as an unconfirmed
  approach row" item, reframed: instead of the maintainer doing the
  research and asserting an answer, it's now a `status=pending` claim
  awaiting confirmation, the same as any future community submission would
  be. New tests in `tests/test_reports.py` for `format_pending_reports()`.
- **Migrated every previously session-tracked data-quality item onto the
  live `open_questions()` system**, plus a new `cli.py --open-questions`
  flag printing the full backlog across the whole dataset (not scoped to a
  trip, unlike `plan`'s per-objective nudge):
  - Broadened `open_questions()`'s peak-coordinate heuristic to flag
    `coord_source == "peakbagger"` (Tier C) for independent re-verification,
    not just the literal string "unconfirmed" -- this alone surfaces all 7
    previously peakbagger-sourced SPS peaks with no further data changes.
  - New `data/peaks.csv` `notes` column (also added to
    `wayproof.data_loader`'s meta columns and `scripts/split_collections.py`'s
    core columns). `_dedupe_by_name()` now writes the SPS/non-SPS conflict
    it resolves into the kept row's `notes` (previously only in a code
    comment and `DATA_LICENSE.md`), so the Mount Johnson/Thunder Mountain
    elevation dispute is now surfaced live instead of living only in prose.
    `split()`'s column-presence check treats `notes` as optional, like
    `name`, since it's project-added rather than a raw source field.
  - New `timed_entry` parameter on `open_questions()`, flagging
    `data/timed_entry.csv` rows whose `notes` mention "secondary"/"aggregator"
    sourcing (global view only, same reasoning as campground/campsite gaps).
  - New `tests/test_split_collections.py` (loads the script by file path,
    since `scripts/` isn't a package) covering the note-writing behavior
    directly; `tests/test_reports.py` extended for the new heuristics.
  `DATA_LICENSE.md`'s Known follow-ups now point to `--open-questions`/`plan`
  as the live, current view rather than duplicating tracking as static prose.
- **The scavenger-hunt data loop** (new `wayproof/reports.py`: `OpenQuestion`,
  `Report`, `open_questions`, `submit_report`, `pending_reports`,
  `resolve_report`): a channel-agnostic core for surfacing what's unconfirmed
  or missing, and for recording a claim about it, designed so CLI is only the
  *first* caller, not the only one. `open_questions()` derives its list live
  from confidence signals already in the data (`unconfirmed` approach status,
  a water source with no coordinates, two availability checks that disagree,
  an "approximate" note) rather than a separately hand-maintained list that
  could drift out of sync. `plan.py` now surfaces objective-relevant gaps
  under a new "Help us confirm" section (`PlanResult.open_questions`, also in
  the JSON export), and a new `--report TEXT` flag (plus `--evidence`,
  `--confidence`) appends a claim to a new append-only intake queue,
  `data/pending_reports.csv` -- deliberately separate from the resolved
  domain ledgers, since a submission is a claim to review, not yet a fact.
  `resolve_plan()` gained optional `water_sources`/`water_source_log`/
  `campgrounds`/`campsites` parameters (all backward compatible; omitting
  them yields `open_questions == []` exactly as before). Peak-scoped
  filtering is deliberately conservative -- only approach status, a peak's
  own coordinate flag, and water sources linked by trailhead name currently
  qualify; campground/campsite gaps only appear in the unfiltered view (see
  `DATA_LICENSE.md`'s Known follow-ups for why). A GitHub issue template, an
  MCP tool for Claude, a ChatGPT Action, and a website form are documented in
  the README as future additional callers of the same two functions, not
  built in this change. New `tests/test_reports.py`; `tests/test_plan.py`
  gained end-to-end coverage against the real Rose Peak/Mission Peak data.
- **`data/timed_entry.csv`** (new `wayproof/timed_entry.py`: `TimedEntryPolicy`,
  `load_timed_entry`, `policy_for_year`, `latest_policy`): year-scoped vehicle
  timed-entry/reservation requirements, generalizing `park_access.csv` to a
  policy some agencies re-decide annually rather than hold fixed. Populated
  with Yosemite National Park's full recorded history (2020's pandemic-era
  day-use permit through 2026's elimination of reservations entirely), which
  genuinely varies year to year (required in 2020-2022, not in 2023, required
  again with different date windows in 2024-2025, not in 2026) -- exactly the
  case a single "current state" field would silently overwrite on each
  change. `policy_for_year()` deliberately returns `None` for a year not on
  file rather than assuming a neighboring year's policy still applies.
  2024-2026 rows cite an official nps.gov page directly; 2020-2023 rows are
  secondary-sourced (flagged in their own `notes` and in `DATA_LICENSE.md`'s
  Known follow-ups) since this project hasn't independently retrieved each
  of those years' original NPS announcements. New `tests/test_timed_entry.py`.
- **Rose Peak and Mission Peak (Diablo Range, Alameda County)**: this
  project's first peaks outside the Sierra Nevada / SPS collection, added to
  `data/peaks.csv` with a new `region` field and no `data/collections/sps.csv`
  row, proving out the core/collection split's actual purpose. Both sit on
  East Bay Regional Park District land with a genuinely different access
  model than anything in the Sierra data, which surfaced three new concepts:
  - `data/campgrounds.csv` / `data/campsites.csv` (new `wayproof/camping.py`,
    `Campground`, `Campsite`, `load_campgrounds`, `load_campsites`,
    `campsites_by_campground`): a campground's shared facilities vs. an
    individually-bookable site within it, since some campgrounds (Sunol
    Backpack Camp) contain several named sites with a genuinely different
    proximity to shared water/restroom facilities (Hawks Nest is closer to
    both than the campground's other six sites).
  - `data/water_sources.csv` / `data/water_source_log.csv` (new
    `wayproof/water.py`, `WaterSource`, `WaterSourceLogEntry`,
    `load_water_sources`, `load_water_source_log`, `log_by_source`,
    `latest_status_by_source`): an append-only ledger for facts that decay
    with no announcement (a spigot can go dry with no notice), generalizing
    `permit_source_log.csv`'s confirms/conflicts pattern beyond permits. An
    official EBRPD page and this project's own trip notes currently disagree
    on whether Boyd Camp has water -- both entries are kept rather than one
    silently overwriting the other; see `DATA_LICENSE.md`'s "Known
    follow-ups."
  - `data/park_access.csv` (new `wayproof/park_access.py`, `ParkAccess`,
    `load_park_access`): a park-level vehicle entrance fee and gate hours,
    distinct from both a wilderness permit and a campsite reservation --
    some EBRPD land gates vehicle access independently of either. Confidence
    is tracked per field: Del Valle's posted fee/hours are independently
    verifiable, but its fee exemption for backpackers retrieving a shuttled
    car was confirmed only verbally, in person, by gate staff -- recorded
    with correspondingly lower confidence rather than presented as
    equally solid.
  Sourced from this project's own Ohlone Wilderness Trail trip (Sep 2026),
  official EBRPD pages, and one independently-verified policy change
  (the Ohlone Wilderness Trail's day-use permit was discontinued
  2026-01-01 -- the dataset reflects post-change reality). Two new
  trailheads (`Del Valle (Lichen Bark)`, `Stanford Ave Staging Area`) were
  added to `data/trailheads.csv` accordingly. None of this is wired into
  `plan`'s output yet -- that's a natural next step, not this one.
  New `tests/test_facilities.py`.

### Changed
- **Renamed the project to Wayproof**, completing the rename tracked as
  follow-up work since the initial repositioning pass. GitHub repo
  `sps-trip-planner` -> `wayproof`; Python package `sierra_peaks/` ->
  `wayproof/`; distribution name `sierra-peaks-clustering` -> `wayproof`;
  CLI entry points `sps-plan` -> `wayproof` (the flagship command now gets
  the bare name) and `sps-cluster` -> `wayproof-cluster` (kept distinct
  since clustering remains explicitly experimental). `cli.py` and `plan.py`
  keep their filenames; only the installed console-script names changed.
  Data files and identifiers referring to the actual Sierra Club Sierra
  Peaks Section program (`data/collections/sps.csv`, `list=SPS`, etc.) are
  unaffected -- that's a real third-party program name, not project
  branding.
- **Split the peak dataset into a public-domain-first core plus an optional
  SPS collection**, closing the architectural follow-up from the source
  policy pass: `data/peaks.csv` (name, coordinates, elevation, and the
  project-computed `nearest_trailhead*` access signal -- collection-agnostic,
  no dependency on the Sierra Club compilation) and
  `data/collections/sps.csv` (`list`, `section`, `class`, `emblem`,
  `mountaineers`, `mileage_rt`/`gain_ft`/`loss_ft`, `trailhead`, `quad`,
  `benchmark`/`benchmark_rating` -- everything specific to the SPS program's
  own source documents), joined by `name`. `data/sps_peaks.csv` becomes a
  git-ignored, rebuild-only staging file, no longer the runtime dataset.
  `load_peaks()` gained an optional `collections_path` argument that
  left-joins a collection onto the core dataset by name and validates it
  doesn't redefine core columns; omitting it loads the core dataset
  standalone. New `scripts/split_collections.py` performs the split as the
  final rebuild step. `cli.py`, `plan.py`, and `scripts/map_clusters.py`
  gained a `--collections-file` flag (default `data/collections/sps.csv`).
  Verified byte-identical JSON output and full per-peak fidelity (247/247
  SPS peaks, zero field mismatches) against the old single-file load.
  This also resolved the operational half of the "duplicate peak names"
  follow-up: `split_collections.py` applies a documented, conservative
  tie-break (two names -- "Mount Johnson", "Thunder Mountain" -- appearing
  under both `list=SPS` and `list=non-SPS` with conflicting data now keep
  their SPS-list entry), so `plan.py`'s `--list` default changes from `SPS`
  to `all` since loading the unfiltered dataset no longer crashes.
  Independently determining which of the conflicting values is actually
  correct remains a separate, open follow-up.
- `DATA_LICENSE.md`: added an explicit Source Policy section (Tier A federal
  data / Tier B openly-licensed community data / Tier C reference-only
  data) and classified every data file as `public_domain`, `open_license`,
  `project_created`, or `third_party_reference_only`. Fixed a factual drift
  bug found in the process: the dataset actually has 240 GNIS-sourced and
  7 peakbagger-sourced SPS peak coordinates (Rogers Peak had been added to
  `sps_peaks.csv` without updating the documented "241 GNIS / 6
  peakbagger" counts in the README and here). Documented two follow-ups
  surfaced by the classification pass rather than rushed into this change:
  independently re-verifying the 7 peakbagger-sourced coordinates against a
  Tier A source, and splitting `sps_peaks.csv`'s public-domain geography
  from its SPS-specific curated fields into a core-dataset-plus-optional-
  collections architecture.

### Added
- `plan.py` (new standalone CLI, `sps-plan` entry point) and
  `wayproof/plan.py` (`PlanResult`, `resolve_plan`, `format_plan_summary`):
  resolves access, permit, and evidence logistics for a specific, named set
  of objectives and a trip date, e.g.
  `python plan.py "Mount Williamson" "Mount Tyndall" --date 2027-07-15`. This
  is the first end-to-end delivery of the project's core thesis -- objective
  -> approach -> access -> permit -> timing -> evidence -- without going
  through the experimental clustering/TSP pipeline at all. Reuses existing
  machinery rather than duplicating it: `choose_trailhead` picks the shared
  trailhead, the named objectives are wrapped in a single-use `Cluster` and
  handed to `clusters_permit_info` (so approach overrides, unconfirmed-case
  cautions, and computed release-phase dates all apply for free), and each
  objective's official `mileage_rt`/`gain_ft` is surfaced directly rather
  than computing a new geometric estimate. `PlanResult.to_dict()` gives
  structured JSON output (`--output plan.json`) from day one. Objectives
  that don't share a single trailhead aren't rejected -- `plan` resolves its
  best guess and reports the mismatch as an explicit warning. Refactored
  `format_permit_report`'s per-entry rendering into a shared
  `format_permit_entry_body` so `plan`'s output doesn't duplicate that
  formatting logic.
- `data/release_policies.csv` and new `wayproof/release_policy.py`
  (`ReleasePhase`, `load_release_policies`): structured, computable permit
  release rules, replacing per-group special-cased Python for 8 of 9
  quota-required permit groups. Previously, a group with a percentage-split
  release (e.g. Inyo NF's 60% at 6 months, 40% at 2 weeks) only ever had its
  *first* release date computed -- the second release existed only as prose
  in `reservation_method`. `permit_status()` now resolves every phase
  generically by `mechanism` (`reservation`, `lottery_annual`, `walkup`,
  `contact_required`), correctly surfacing every dated phase, e.g. both the
  60% and 40% Inyo NF dates. Mount Whitney Zone's annual lottery (previously
  hardcoded as Python `date(year, 2, 1)` literals) and CPMA's walk-up/contact
  split are now data-driven too; a phase can be scoped to `season =
  in_season`/`off_season` for groups whose mechanics genuinely differ (a
  winter Whitney trip now correctly gets simple off-season reservation
  language instead of lottery wording with a footnote, which is what the
  source actually describes but the old code didn't implement). A phase with
  no exact release offset in the source (Sierra NF's ~40% second allocation)
  is left unresolved rather than assigned a fabricated date. Yosemite's
  weekly lottery is deliberately NOT migrated -- its own source states exact
  per-area dates come from a downloadable dataset that hasn't been
  retrieved, so this remains on its original special-cased logic rather than
  manufacture false precision. New `--release-policies-file` CLI flag
  (default `data/release_policies.csv`); `load_permits()` now also accepts a
  `release_policies_path` argument and attaches each group's phases to its
  `PermitRule.release_phases`.
- `data/approaches.csv` and new `wayproof/access.py` (`ApproachRoute`,
  `load_approaches`): structured peak -> approach -> permit relationships,
  replacing the flat `data/permit_overrides.csv` peak-name -> permit-group
  string map. Each row now carries the named approach/route, the trailhead it
  starts from, and a `status` of `confirmed` (a source directly states the
  peak's real permit product) or `unconfirmed` (a different approach is
  plausible -- e.g. the peak's own source-listed trailhead names a different
  trail -- but no source confirms which permit governs it). `--permits` (via
  `clusters_permit_info`) now emits an explicit `UNCERTAIN` caution for
  unconfirmed peaks instead of silently assuming the trailhead default or
  silently omitting them, which the old override file could not represent.
  `--permit-overrides-file` is now `--approaches-file`. This is the first
  concrete piece of the project's longer-term planning graph (objective ->
  approach -> entry point -> land unit -> permit product -> rule); `LandUnit`
  and `PermitProduct` remain simple inline fields on trailheads/`permits.csv`
  for now, a deliberate scope decision while coverage stays Sierra-only.
- `Peak.collection` property (reads `meta["list"]`): a small step toward
  treating `Peak` as one *type* of place-based objective and a named list
  like SPS as one collection of objectives, rather than the project's whole
  ontology. No behavior change -- existing `--list` filtering already worked
  this way; this just gives it a name on the model.
- `--permit-sources [GROUP]`: prints `data/permit_source_log.csv`, a new
  append-only audit trail of every source checked per permit_group (source
  URL, the source's own update date, how it was checked, and a verdict of
  `new-group`/`confirms-existing`/`corrects-existing`/`unresolved-conflict`).
  Unlike `permits.csv` (which only holds the current best answer and gets
  overwritten on each edit), this log preserves every check, so a later
  source that disagrees with an earlier one is visible rather than silently
  replacing it. `unresolved_conflicts()` flags any permit_group whose most
  recent logged entry hasn't been reconciled yet. New
  `wayproof/permits.py` (`SourceLogEntry`, `load_source_log`,
  `unresolved_conflicts`, `format_source_log`). Backfilled with this
  project's actual verification history to date, including one real
  screenshot-resolution ambiguity (Whitney lottery results date) that was
  logged as a conflict and then resolved by a follow-up entry, demonstrating
  the intended workflow.
- Provenance tracking for `data/permits.csv`: two new columns,
  `source_last_updated` (the source page/document's own "last updated" date,
  e.g. an fs.usda.gov footer or a PDF's filename date) and `verified_date`
  (when this repo last checked that row against the source). The two are
  independent -- a row can trace to an old source that's still the best
  available data, or to a fresh-looking page that was never independently
  checked here. `--permits` now prints a `Provenance:` line per trip showing
  both, or flags rows with no `verified_date` as web-search-only /
  not independently verified. Surfaced that the Inyo NF trailhead/quota PDF
  used for the `inyo_gtw` and `inyo_hoover_nonquota` groups is dated
  2021-06-13 -- the agency/quota-status facts are unlikely to have changed,
  but the exact quota numbers should be re-verified before relying on them.
- `--permits`: per-trip permit report (implies `--include-approach`). Every
  trailhead in `data/trailheads.csv` is tagged with a `wilderness_area`,
  `land_agency`, and `permit_group`; the new `data/permits.csv` maps each
  `permit_group` to its permit type, quota season, reservation window/method,
  fees, and official apply URL (Inyo NF, Sierra NF, Sequoia NF, Stanislaus NF,
  Eldorado NF/LTBMU, Humboldt-Toiyabe NF, Yosemite NP, and Sequoia & Kings
  Canyon NP, including the separate Mt. Whitney Zone lottery). Given
  `--trip-date`, it reports whether that date falls in the quota season and
  when the reservation window opens. New `wayproof/permits.py`
  (`load_permits`, `permit_status`, `clusters_permit_info`,
  `format_permit_report`) and `tests/test_permits.py`.
- Peak-level permit overrides (`data/permit_overrides.csv`,
  `load_permit_overrides`, `--permit-overrides-file`): some trailheads serve
  more than one permitted trail with different rules -- e.g. Whitney Portal's
  classic Mt. Whitney Trail is lottery-only, but Mount Russell (Mountaineers
  Route / North Fork of Lone Pine Creek) is explicitly excluded from that
  lottery and uses the regular Inyo NF John Muir Wilderness permit instead.
  `clusters_permit_info` now emits an extra `[for <peak> only]` entry when a
  cluster mixes peaks needing different permits. Populated conservatively --
  only peaks with a directly-named source, e.g. Mount Russell; other likely
  candidates (Thor Peak, Mount Irvine, Mount McAdie, Mount Mallory, Mount
  LeConte, Mount Corcoran, Mount Carillon) are flagged in the README rather
  than guessed at.
- Two new Inyo NF permit groups, `inyo_gtw` and `inyo_hoover_nonquota`,
  correcting two trailheads that were tagged to the wrong permit_group:
  `Horseshoe Meadows (Cottonwood)` (Golden Trout Wilderness entries have a
  shorter quota season -- late June to Sep 15 -- than Inyo's general John
  Muir/Ansel Adams May 1 - Nov 1 season) and `Lundy Canyon` / `Saddlebag
  Lake` (both actually Inyo NF-administered and non-quota, not
  Humboldt-Toiyabe NF's quota'd Hoover Wilderness system as previously
  tagged). All confirmed against Inyo NF's official trail/quota table.
- Approach-aware capacity splitting: with `--include-approach`, the trip budget
  is enforced including the trailhead approach. Splitting starts from the
  inter-peak floor and tightens only when an extra split actually makes trips fit
  once the walk-in is counted; approach-dominated clusters are kept whole rather
  than fragmented (which would only re-pay the approach). `cluster_peaks` and
  `plan_trips` now accept `trailheads`.
- `--approach-report`: approach-amortization diagnostic ranking trailheads that
  serve multiple trips by recoverable approach effort (implies
  `--include-approach`). New `wayproof/diagnostics.py`
  (`approach_amortization`, `format_approach_report`).
- `--include-approach`: model the trailhead approach (walk in to the first
  summit and out from the last) using `data/trailheads.csv`. Anchors each trip
  to its best-serving trailhead, re-routes it as a closed tour
  (`solve_tsp_cycle`) so entry/exit summits minimize the whole loop, and folds
  the approach into distance, effort, days and score. New `approach.py` module,
  `load_trailheads`, and `Trailhead` model; approach is off by default so
  existing output is unchanged.
- MIT `LICENSE`, `DATA_LICENSE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `pyproject.toml`, GitHub issue/PR templates, and a CI workflow running the
  test suite on Python 3.9–3.12.
- `--by-trailhead` clustering, with `--trailhead-max-mi` distance cap and
  `--trailhead-field` to group on any metadata column.
- `data/trailheads.csv` (curated east/west/crest Sierra trailheads) and
  `scripts/assign_trailheads.py` to tag each peak with its nearest trailhead.
- Benchmark route data: `scripts/parse_benchmarks.py`,
  `data/benchmark_routes.csv`, and difficulty-progression charts.
- Interactive topo map (`scripts/map_clusters.py`) with OpenTopoMap /
  OpenStreetMap / Esri basemaps.
- Versioned cluster and benchmark charts under `charts/` (rendered at 300 DPI).

### Changed
- Repositioned the project around source-backed trip logistics rather than
  geographic clustering. The README, `cli.py`, `wayproof/__init__.py`, and
  `pyproject.toml` description now lead with the actual product question --
  "I want to do this objective on this date; what do I need to know and do to
  make it happen?" -- ahead of installation and algorithm details, using the
  Mount Williamson / Mount Tyndall shared-approach-and-permit example to make
  that concrete before any code is shown.
- Demoted DBSCAN/TSP-based grouping from the project's headline feature to an
  explicitly experimental discovery aid. Added a dedicated "Experimental:
  Geographic Trip Discovery" section and a terminology list (candidate
  grouping, candidate sequence, known approach, verified rule,
  unresolved/uncertain) so generated output is never described as a verified
  route. The JSON schema keeps historical field names (`clusters`,
  `cluster_id`, `recommended_order`) for compatibility, now documented as
  such rather than implied to be authoritative.
- This is a positioning and documentation change; no CLI flags, JSON schema
  fields, or public function signatures were removed or renamed. The package
  name (`sierra-peaks-clustering`), CLI entry point (`sps-cluster`), and repo
  name are intentionally unchanged for now -- a full rename is tracked as
  separate future work.

### Notes
- This is the initial open-source preparation of the Sierra Peaks trip planner.
