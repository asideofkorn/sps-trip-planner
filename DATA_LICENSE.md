# Data provenance & licensing

The MIT `LICENSE` covers the **source code**. The data files shipped in this
repository come from a mix of sources with different terms. Read this before
redistributing or relying on the bundled data.

## Source policy

This project is Sierra Nevada- and SPS-focused today, but the architecture is
meant to extend to other U.S. public lands without carrying a private-data
dependency into that expansion (see the README's project thesis). That means
being deliberate about where data comes from, not just what it says.

Every source this project uses, or would consider using, falls into one of
three tiers:

- **Tier A -- preferred foundational sources.** U.S. federal (and, where a
  state/local source's license is explicit, state/local) public data: USGS
  GNIS, USGS 3DEP, NPS data/API, USFS data, BLM data, Recreation.gov/RIDB.
  This is the project's backbone -- free, generally public domain, and
  explicitly intended for reuse by outside developers.
- **Tier B -- openly licensed community sources.** OpenStreetMap and other
  datasets under an explicit, compatible open license. Usable, but with real
  obligations (e.g. OSM's ODbL requires attribution and share-alike for a
  derived database) that must be honored deliberately, not assumed away.
  This is also why trail-corridor/route-network geometry isn't part of the
  canonical dataset yet -- importing a major external trail graph means
  inheriting its license regime, not just its GIS complexity.
- **Tier C -- reference-only sources.** Sierra Club publications,
  Peakbagger, SummitPost, AllTrails, guidebooks, blogs. Useful for a human
  contributor to discover or verify a fact, and citable as *evidence* in a
  `notes` or source-log field. Never copied wholesale into this project's
  own database, and a source document itself is never redistributed, unless
  its license explicitly allows it.

Every data file below is also classified by what that means for reuse:

| Classification | Meaning |
|-----------------|---------|
| `public_domain` | A U.S. government work; no use restrictions. |
| `open_license` | Third-party data under an explicit open license (e.g. ODbL); usable subject to that license's terms. |
| `project_created` | Facts, relationships, or corrections this project compiled, verified, or derived itself (a permit rule, a release-phase date, an approach relationship, a source-log entry). Not independently copyrightable subject matter in most cases, but distinguished from `public_domain` because its accuracy rests on this project's own verification work, not a government guarantee -- see each file's own provenance fields (`verified_date`, `status`, etc.). |
| `third_party_reference_only` | A private (Tier C) source consulted for a specific fact not otherwise available. The individual fact extracted this way isn't copyrightable, but the source itself isn't redistributed, and the fact is flagged for eventual independent re-verification against a Tier A source rather than treated as equally solid. |

## Summary

| File(s) | Source | Classification | Terms |
|---------|--------|-----------------|-------|
| `data/source/gnis_sierra_summits.txt` | USGS Geographic Names Information System (GNIS) | `public_domain` | U.S. Government work |
| Sierra Club SPS PDFs/XLS (`sps_list_29th_ed_2025.pdf`, `sps_list_with_mileage.xls`, `scrambler_ratings_non_sps_2025.pdf`, `benchmark_routes.pdf`) | Sierra Club — Angeles Chapter, Sierra Peaks Section (SPS) | `third_party_reference_only` | **© Sierra Club. NOT redistributed in this repo** (removed from the tree and git history). Download from the SPS site to rebuild — see below. |
| `data/sps_peaks.csv`, `data/benchmark_routes.csv` | Derived: factual data (names, elevations, coordinates, class, mileage) extracted from the sources above | `public_domain` for GNIS-sourced coordinates (`coord_source=GNIS`, 454 of 601 rows); `third_party_reference_only` for the 7 rows with `coord_source=peakbagger` (unofficially-named summits with no GNIS entry); `project_created`/derived for everything else | Facts are not copyrightable; the *compilation* draws on the SPS list. Attribute the Sierra Club SPS and USGS GNIS. The peakbagger-sourced coordinates are tracked for independent re-verification against a Tier A source (topo/3DEP) rather than treated as equally solid -- see "Known follow-ups" below. |
| `data/trailheads.csv` | Curated by this project from public sources (PCTA, NPS, USFS, Wikipedia); coordinates are facts. `wilderness_area`/`land_agency`/`permit_group` columns added July 2026, cross-referenced against the agency sources below | `project_created` | Provided under the project license; verify before navigational use |
| `data/permits.csv` | Curated by this project from official sources (recreation.gov, nps.gov, fs.usda.gov) as of July 2026 | `project_created` | Facts (agency, fees, dates) are not copyrightable; provided under the project license. Quota seasons, reservation windows and lottery dates change annually — treat as a planning aid and verify against the listed `apply_url` before relying on any date. |
| `data/release_policies.csv` | Derived by this project from the same official sources as `data/permits.csv`, restructured from prose into discrete dated phases | `project_created` | Same terms as `data/permits.csv` above. A phase with no exact release offset in the source is left unresolved rather than guessed at. |
| `data/approaches.csv` | Curated by this project from official sources (recreation.gov, fs.usda.gov) as of July 2026, plus this project's own peak-source-data cross-references | `project_created` | Same terms as `data/permits.csv` above. Deliberately conservative — `confirmed` rows require a directly-named source; `unconfirmed` rows flag a suspected discrepancy without asserting an unverified permit. |
| `data/permit_source_log.csv` | Compiled by this project as an audit trail of its own verification process (web searches and user-provided screenshots/text of the sources above) | `project_created` | Append-only by design — never edit a past entry, only add new ones. Facts are not copyrightable; provided under the project license. |
| `charts/*` (basemap tiles, when rendered) | © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA); Esri | `open_license` (OSM/OpenTopoMap, ODbL/CC-BY-SA) and third-party terms (Esri) | Tiles are fetched client-side; attribution is shown on the map |

## Known follow-ups

This classification pass surfaced two things worth fixing, tracked as
separate work rather than rushed here:

- **The 7 peakbagger-sourced coordinates should be independently
  re-verified** (via USGS 3DEP/topo, with this project's own documented
  determination) rather than carried indefinitely as a third-party
  dependency. That's real per-peak geographic verification work, not a
  find-and-replace -- doing it carelessly risks introducing a wrong
  coordinate for a real mountain feature, which is worse than the current
  honestly-labeled dependency.
- **`data/sps_peaks.csv` mixes public-domain geography (name, coordinates,
  elevation) with SPS-specific curated fields (`list`, `section`, `emblem`,
  `mountaineers`, `mileage_rt`/`gain_ft`, benchmark rating) in one file.**
  A cleaner long-term architecture separates a public-domain core dataset
  (peak ID, coordinates, elevation -- sourced from USGS alone) from optional
  collection layers like SPS (`section`, `emblem`, etc., keyed to that core
  ID) -- so a mountain's existence in this project never depends on the
  Sierra Club compilation, only its *membership in the SPS collection*
  does. This also directly serves national expansion: a future California
  or Colorado collection would layer onto the same core dataset the same
  way. Not done in this pass -- it's a real data-model migration touching
  the loader, scripts, and JSON export schema, not a documentation change.

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
- Seven unofficially-named summit coordinates (no GNIS entry): peakbagger.com
- Map tiles: © OpenStreetMap contributors, OpenTopoMap (CC-BY-SA), Esri
