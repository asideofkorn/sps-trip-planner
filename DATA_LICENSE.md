# Data provenance & licensing

The MIT `LICENSE` covers the **source code**. The data files shipped in this
repository come from third parties and are **not** covered by the MIT license.
Read this before redistributing or relying on the bundled data.

## Summary

| File(s) | Source | Terms |
|---------|--------|-------|
| `data/source/gnis_sierra_summits.txt` | USGS Geographic Names Information System (GNIS) | **Public domain** (U.S. Government work) |
| Sierra Club SPS PDFs/XLS (`sps_list_29th_ed_2025.pdf`, `sps_list_with_mileage.xls`, `scrambler_ratings_non_sps_2025.pdf`, `benchmark_routes.pdf`) | Sierra Club — Angeles Chapter, Sierra Peaks Section (SPS) | **© Sierra Club. NOT redistributed in this repo** (removed from the tree and git history). Download from the SPS site to rebuild — see below. |
| `data/sps_peaks.csv`, `data/benchmark_routes.csv` | Derived: factual data (names, elevations, coordinates, class, mileage) extracted from the sources above | Facts are not copyrightable; the *compilation* draws on the SPS list. Attribute the Sierra Club SPS and USGS GNIS. |
| `data/trailheads.csv` | Curated by this project from public sources (PCTA, NPS, USFS, Wikipedia); coordinates are facts | Provided under the project license; verify before navigational use |
| `charts/*` (basemap tiles, when rendered) | © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA); Esri | Tiles are fetched client-side; attribution is shown on the map |

## The Sierra Club source documents (removed)

The **Sierra Club Sierra Peaks Section publications** (the official peak list,
scrambler ratings, and benchmark routes) are copyrighted. To avoid infringing
that copyright in a public repository, they have been **removed from the working
tree and purged from git history**. Only the underlying *facts* (peak names,
elevations, classes, coordinates) live on, in the derived datasets
`data/sps_peaks.csv` and `data/benchmark_routes.csv`, which are not copyrightable
and remain with attribution.

To rebuild the datasets from scratch, download the originals from the SPS site
(<https://angeles.sierraclub.org/sierra_peaks>) and place them under
`data/source/` (git-ignored). The rebuild scripts print a download reminder if a
file is missing.

## Attribution

- Sierra Peaks list & ratings: Sierra Club, Angeles Chapter, Sierra Peaks
  Section — <https://angeles.sierraclub.org/sierra_peaks>
- Coordinates: U.S. Geological Survey, Geographic Names Information System
  (GNIS), public domain
- Six unofficially-named summit coordinates: peakbagger.com
- Map tiles: © OpenStreetMap contributors, OpenTopoMap (CC-BY-SA), Esri
