# data/source/

Raw source inputs used to *rebuild* the processed datasets. You don't need
these to run the tool — the built results (`data/sps_peaks.csv`,
`data/benchmark_routes.csv`) are committed.

## Bundled here

- `gnis_sierra_summits.txt` — trimmed Sierra subset of the USGS Geographic
  Names Information System (GNIS), `feature_class = Summit`. **Public domain.**

## Rebuilding the passes dataset (`data/passes.csv`)

Mountain passes, saddles, and notches live in GNIS under
`feature_class = Gap` — the same gazetteer the summits come from. The committed
`gnis_sierra_summits.txt` holds only `Summit` rows, so to authoritatively fill
pass coordinates you first need a Gap-bearing extract.

1. Download the full California names file from the USGS GNIS "Domestic Names"
   download page (<https://www.usgs.gov/us-board-on-geographic-names/download-gnis-data>),
   then trim it to the columns/box this repo uses (pipe-delimited, header
   `feature_name|feature_class|state_name|map_name|prim_lat_dec|prim_long_dec`),
   keeping only `feature_class = Gap`. Save it here as `gnis_sierra_gaps.txt`.

2. Replace the seed coordinates in `data/passes.csv` with the GNIS values:

       python scripts/merge_passes.py --gnis data/source/gnis_sierra_gaps.txt
       # add --add-all to also append every named Sierra Gap

3. Backfill elevation from a DEM (GNIS pass elevations are unreliable):

       python scripts/fill_pass_elevation.py            # USGS 3DEP, feet
       python scripts/fill_pass_elevation.py --only-seed # refresh seed rows

`data/passes.csv` is committed pre-populated with a hand-curated seed of the
major Sierra crest/road passes (`coord_source = seed`) so the data is usable
without the rebuild; the steps above upgrade those rows to `coord_source = GNIS`.

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
