# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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

### Notes
- This is the initial open-source preparation of the Sierra Peaks trip planner.
