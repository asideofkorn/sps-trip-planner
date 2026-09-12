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
| `data/peaks.csv` (core: name, coordinates, elevation, region, nearest-trailhead access signal, `notes`) | GNIS for 454 of 601 rows (incl. Rose Peak, Alameda County); peakbagger.com for 7 unofficially-named SPS summits with no GNIS entry; USGS topo (GNIS ID unconfirmed) for Mission Peak; 139 rows have no coordinates yet (non-SPS peaks not yet independently located) | `public_domain` for GNIS-sourced coordinates; `third_party_reference_only` for the 7 peakbagger-sourced rows and for Mission Peak pending GNIS confirmation; `project_created` for the derived `nearest_trailhead*` access signal and the `region` field | Facts are not copyrightable. Attribute USGS GNIS. Rose Peak and Mission Peak (Diablo Range, Alameda County) are this dataset's first peaks outside the Sierra Nevada / SPS collection -- added with no `data/collections/sps.csv` row, since neither is SPS-tracked, demonstrating the core/collection split's actual purpose. The peakbagger-sourced coordinates and Mission Peak's GNIS ID are tracked for independent re-verification -- see "Known follow-ups" below. Collection-agnostic: this file has no dependency on the Sierra Club compilation. |
| `data/collections/sps.csv` (the SPS collection: list, section, class, mileage/gain, benchmark rating), `data/benchmark_routes.csv` | Derived: factual data extracted from the Sierra Club SPS list and non-SPS scrambler ratings | `project_created`/derived | Facts are not copyrightable; the *compilation* draws on the SPS list. Attribute the Sierra Club SPS. Two names ("Mount Johnson", "Thunder Mountain") appeared under both `list=SPS` and `list=non-SPS` with conflicting data; the SPS-list entry was kept for both this file and `data/peaks.csv` -- see "Known follow-ups". |
| `data/trailheads.csv` | Curated by this project from public sources (PCTA, NPS, USFS, Wikipedia); coordinates are facts. `wilderness_area`/`land_agency`/`permit_group` columns added July 2026, cross-referenced against the agency sources below. `park` column added alongside Rose Peak/Mission Peak: the specific park/preserve unit for vehicle-access purposes, distinct from `wilderness_area`'s backcountry/permit designation -- links to `data/campgrounds.csv` and `data/park_access.csv`'s own `park` columns. | `project_created` | Provided under the project license; verify before navigational use |
| `data/permits.csv` | Curated by this project from official sources (recreation.gov, nps.gov, fs.usda.gov) as of July 2026 | `project_created` | Facts (agency, fees, dates) are not copyrightable; provided under the project license. Quota seasons, reservation windows and lottery dates change annually — treat as a planning aid and verify against the listed `apply_url` before relying on any date. |
| `data/release_policies.csv` | Derived by this project from the same official sources as `data/permits.csv`, restructured from prose into discrete dated phases | `project_created` | Same terms as `data/permits.csv` above. A phase with no exact release offset in the source is left unresolved rather than guessed at. |
| `data/approaches.csv` | Curated by this project from official sources (recreation.gov, fs.usda.gov) as of July 2026, plus this project's own peak-source-data cross-references | `project_created` | Same terms as `data/permits.csv` above. Deliberately conservative — `confirmed` rows require a directly-named source; `unconfirmed` rows flag a suspected discrepancy without asserting an unverified permit. |
| `data/permit_source_log.csv` | Compiled by this project as an audit trail of its own verification process (web searches and user-provided screenshots/text of the sources above) | `project_created` | Append-only by design — never edit a past entry, only add new ones. Facts are not copyrightable; provided under the project license. |
| `data/campgrounds.csv`, `data/campsites.csv` | Curated by this project from official East Bay Regional Park District (EBRPD) sources (ebparks.org, ReserveAmerica) plus this project's own firsthand trip notes (Ohlone Wilderness Trail, Sep 2026) | `project_created` | Facts are not copyrightable; provided under the project license. Some fields (e.g. a campground's exact nightly vehicle-gate cutoff) are reported from a single firsthand near-miss experience, not a confirmed posted policy — see each field's own notes. |
| `data/water_sources.csv`, `data/water_source_log.csv` | `water_sources.csv`: curated by this project. `water_source_log.csv`: a mix of EBRPD's own published "Water Availability Update" page and this project's firsthand trip reports | `project_created` | Append-only ledger by design, same pattern as `permit_source_log.csv` — a water source's status can change with no announcement, so a later check never overwrites an earlier one. See "Known follow-ups" for a real official-vs-firsthand discrepancy already on file (Boyd Camp). |
| `data/park_access.csv` | Curated by this project from EBRPD's official page (entrance fee, gate hours) plus a verbal, in-person staff confirmation (a fee exemption not found in writing) | `project_created` | The fee-exemption field carries deliberately lower confidence than the fee/hours fields — see the row's own `notes`. |
| `data/pending_reports.csv` | Submitted by this project's maintainer (today) or, in the future, community members, via `plan.py --report` or another intake channel described in the README's "The Scavenger Hunt" section | `project_created` | An intake queue, not a source of truth: a claim here has `status=pending` until a maintainer reviews it and (if accepted) transcribes it into the relevant domain file, citing the report ID. Never treated as confirmed data on its own. |
| `data/timed_entry.csv` | NPS's own announcements for 2024–2026; secondary/aggregator press coverage (Yosemite Conservancy, Afar) for 2020–2023, since this project has not independently retrieved each year's original NPS announcement | `project_created` (compiled history) | One row per (park, year) by design — never overwrite a prior year's recorded policy with the current year's, since whether a reservation is required is a decision NPS re-makes annually, not a standing rule. Confidence varies by row: 2024–2026 rows cite an official nps.gov page directly; 2020–2023 rows are flagged in their own `notes` as secondary-sourced. |

## Known follow-ups

As of the scavenger-hunt data loop (see README's "The Scavenger Hunt"),
every item below is tracked *live*, not just here: run
`python cli.py --open-questions` for the full current backlog across the
whole dataset, or `python plan.py "<peak>" --date ...` for the subset
relevant to a specific objective. This section stays as the durable record
of *why* each one exists and how it was classified; it deliberately doesn't
try to duplicate `open_questions()`'s output, which can drift as new gaps
are found or existing ones resolved.

- **`data/timed_entry.csv`'s 2020–2023 Yosemite rows are secondary-sourced**
  (cited to aggregator/press coverage rather than each year's original
  nps.gov announcement, which this project has not independently
  retrieved) -- surfaced live by `open_questions()`'s scan of each row's
  `notes` for "secondary"/"aggregator". The 2024–2026 rows already cite
  nps.gov directly.
- **Mission Peak's GNIS feature ID is unconfirmed** (coordinates come from
  USGS topo/Wikipedia, not a directly-cited GNIS feature ID) -- surfaced
  live via `data/peaks.csv`'s `coord_source` field.
- **Boyd Camp's water availability has an unresolved conflict on file** in
  `data/water_source_log.csv`: EBRPD's official page listed it as available
  (checked 2026-09-02), while this project's own trip-planning notes for
  the same period marked it as having no water -- neither has been
  independently confirmed on the ground. Surfaced live by comparing a water
  source's most recent log entries; left as an open, visible disagreement
  rather than picking one silently, per the ledger's own append-only design.
- **The 7 peakbagger-sourced coordinates should be independently
  re-verified** (via USGS 3DEP/topo, with this project's own documented
  determination) rather than carried indefinitely as a third-party
  dependency -- surfaced live via `coord_source == "peakbagger"`. That's
  real per-peak geographic verification work, not a find-and-replace --
  doing it carelessly risks introducing a wrong coordinate for a real
  mountain feature, which is worse than the current honestly-labeled
  dependency. Not yet done.
- **Two names ("Mount Johnson", "Thunder Mountain") appear under both
  `list=SPS` and `list=non-SPS` with conflicting elevation data** in the
  underlying Sierra Club source documents. `scripts/split_collections.py`
  applies a documented, conservative tie-break (prefer the primary SPS-list
  entry) so both `data/peaks.csv` and `data/collections/sps.csv` have a
  unique `name` key -- required for the core/collection join to be
  meaningful at all, and now also writes that conflict into the kept row's
  `notes` field, so it's surfaced live by `open_questions()` rather than
  living only in this file and a code comment. That tie-break resolves the
  operational issue (an unfiltered load no longer crashes) but is not the
  same as determining *which value is actually correct*; that independent
  investigation is still open.

### Resolved: campground/campsite/park-access linking

Campground/campsite/park-access gaps used to only surface in
`open_questions()`'s unfiltered view: `data/trailheads.csv`'s
`wilderness_area` ("Ohlone Wilderness") and `data/campgrounds.csv`'s `park`
("Del Valle Regional Park") used different naming granularity for the same
corridor, so there was no reliable link from a specific peak to "which
campgrounds/park fees are near it." `data/trailheads.csv` now has a `park`
column (the specific park/preserve unit, distinct from `wilderness_area`'s
backcountry/permit designation), populated for the two EBRPD trailheads and
blank elsewhere. Both `open_questions()` and `wayproof.plan`'s new
`PlanResult.facilities` use it, so `plan.py "Rose Peak"` now shows its
campground/park-access facts and gaps directly, not just in the global
backlog.

### Resolved by the core/collection split

Peak data used to mix public-domain geography (name, coordinates,
elevation) with SPS-specific curated fields (`list`, `section`, `emblem`,
`mountaineers`, `mileage_rt`/`gain_ft`, benchmark rating) in one file
(`data/sps_peaks.csv`). It's now split into `data/peaks.csv` (core,
collection-agnostic -- a mountain's existence here never depends on the
Sierra Club compilation) and `data/collections/sps.csv` (everything that
does, keyed to the core dataset by `name`). `scripts/split_collections.py`
performs the split as the final step of the rebuild pipeline (see
`data/source/README.md`); `data/sps_peaks.csv` is now a git-ignored,
rebuild-only staging file, not the runtime dataset. This also directly
serves national expansion: a future California or Colorado collection would
layer onto the same core dataset the same way.

## The Sierra Club source documents (removed)

The **Sierra Club Sierra Peaks Section publications** (the official peak list,
scrambler ratings, and benchmark routes) are copyrighted. To avoid infringing
that copyright in a public repository, they have been **removed from the working
tree and purged from git history**. Only the underlying *facts* (peak names,
elevations, classes, coordinates) live on, in the derived datasets
`data/peaks.csv`, `data/collections/sps.csv`, and `data/benchmark_routes.csv`,
which are not copyrightable and remain with attribution.

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
