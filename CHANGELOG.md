# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `data/approaches.csv` and new `sierra_peaks/access.py` (`ApproachRoute`,
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
  `sierra_peaks/permits.py` (`SourceLogEntry`, `load_source_log`,
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
  when the reservation window opens. New `sierra_peaks/permits.py`
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
  `--include-approach`). New `sierra_peaks/diagnostics.py`
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
  geographic clustering. The README, `cli.py`, `sierra_peaks/__init__.py`, and
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
