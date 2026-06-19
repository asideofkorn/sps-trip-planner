# Data provenance & licensing

The MIT `LICENSE` covers the **source code**. The data files shipped in this
repository come from third parties and are **not** covered by the MIT license.
Read this before redistributing or relying on the bundled data.

## Summary

| File(s) | Source | Terms |
|---------|--------|-------|
| `data/source/gnis_sierra_summits.txt` | USGS Geographic Names Information System (GNIS) | **Public domain** (U.S. Government work) |
| `data/source/sps_list_29th_ed_2025.pdf`, `sps_list_with_mileage.xls`, `scrambler_ratings_non_sps_2025.pdf`, `benchmark_routes.pdf` | Sierra Club — Angeles Chapter, Sierra Peaks Section (SPS) | **© Sierra Club. All rights reserved.** Redistribution likely requires permission — see warning below. |
| `data/sps_peaks.csv`, `data/benchmark_routes.csv` | Derived: factual data (names, elevations, coordinates, class, mileage) extracted from the sources above | Facts are not copyrightable; the *compilation* draws on the SPS list. Attribute the Sierra Club SPS and USGS GNIS. |
| `data/trailheads.csv` | Curated by this project from public sources (PCTA, NPS, USFS, Wikipedia); coordinates are facts | Provided under the project license; verify before navigational use |
| `charts/*` (basemap tiles, when rendered) | © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA); Esri | Tiles are fetched client-side; attribution is shown on the map |

## ⚠️ Important: the Sierra Club source documents

`data/source/` includes **Sierra Club Sierra Peaks Section publications** (the
official peak list, scrambler ratings, and benchmark routes). These are
copyrighted works. Hosting them in a **public** repository may infringe the
Sierra Club's copyright even though the underlying facts (peak names,
elevations, classes) are freely usable.

Recommended options before making this repository public:

1. **Remove the source documents** from the repo and instead document where to
   obtain them (the SPS publishes the list via
   <https://angeles.sierraclub.org/sierra_peaks>). The derived CSVs in `data/`
   are sufficient to run the tool; only the rebuild scripts
   (`scripts/build_dataset.py`, `scripts/parse_benchmarks.py`) need the
   originals. This is the default recommendation.
2. **Obtain written permission** from the Sierra Club SPS to redistribute.
3. **Keep the repository private.**

The factual datasets derived from these documents (`data/sps_peaks.csv`,
`data/benchmark_routes.csv`) can remain regardless, with attribution.

## Attribution

- Sierra Peaks list & ratings: Sierra Club, Angeles Chapter, Sierra Peaks
  Section — <https://angeles.sierraclub.org/sierra_peaks>
- Coordinates: U.S. Geological Survey, Geographic Names Information System
  (GNIS), public domain
- Six unofficially-named summit coordinates: peakbagger.com
- Map tiles: © OpenStreetMap contributors, OpenTopoMap (CC-BY-SA), Esri
