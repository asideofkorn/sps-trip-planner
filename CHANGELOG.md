# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
