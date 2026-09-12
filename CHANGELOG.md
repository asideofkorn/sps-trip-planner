# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
