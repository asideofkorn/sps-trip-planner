# data/source/

Raw source inputs used to *rebuild* the processed datasets. You don't need
these to run the tool — the built results (`data/sps_peaks.csv`,
`data/benchmark_routes.csv`) are committed.

## Bundled here

- `gnis_sierra_summits.txt` — trimmed Sierra subset of the USGS Geographic
  Names Information System (GNIS). **Public domain.**

## NOT bundled (copyrighted — download yourself)

The following Sierra Club Sierra Peaks Section publications are **not**
redistributed in this repository for copyright reasons (see
[`../../DATA_LICENSE.md`](../../DATA_LICENSE.md)). Download them from the SPS
site — <https://angeles.sierraclub.org/sierra_peaks> — and place them here only
if you want to rebuild the datasets from scratch:

- `sps_list_29th_ed_2025.pdf`
- `sps_list_with_mileage.xls`
- `scrambler_ratings_non_sps_2025.pdf`
- `benchmark_routes.pdf`

The rebuild scripts (`scripts/build_dataset.py`, `scripts/parse_benchmarks.py`)
will print a download reminder if a file is missing. These formats are
git-ignored so they are not accidentally re-committed.
