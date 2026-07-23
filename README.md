# Sierra Peaks Clustering

A Python tool that clusters the **Sierra Peaks Section (SPS)** list — all 247
peaks — into efficient **1–3 day peak-bagging trips**, orders each trip with a
Traveling-Salesman solver to minimize backtracking, ranks trips by efficiency,
and exports the itineraries as JSON.

It models off-trail, class 1–2 travel between summits using **great-circle
distance** for the horizontal component and **Naismith's Rule** to convert
vertical ascent into equivalent effort. A curated permit dataset (`--permits`,
see below) can tell you which agency issues the permit for each trip's
trailhead, whether it's quota season, and when to apply — but the core focus
stays the geographic/physical optimization.

Running it on the real SPS list produces mountaineering-sound groupings: the
Palisades traverse, the Evolution group, the Whitney/Williamson group, the Mono
Divide, the Sawtooth/Matterhorn cluster, and so on.

---

## Data

The bundled dataset (`data/sps_peaks.csv`) is built from the **official Sierra
Club sources** and joined to authoritative **USGS GNIS** coordinates. The
processed CSV is committed and ready to use; the copyrighted Sierra Club source
documents themselves are **not redistributed here** (download them yourself to
rebuild — see [`DATA_LICENSE.md`](DATA_LICENSE.md) and `data/source/README.md`):

| Source | Used for | Bundled? |
|--------|----------|----------|
| `sps_list_with_mileage.xls` (29th ed., 2025) | 247 SPS peaks: elevation, class, section, round-trip mileage, gain/loss, trailhead, USGS quad, emblem/mountaineers flags | No (© Sierra Club) |
| `scrambler_ratings_non_sps_2025.pdf` | 354 non-SPS High Sierra peaks (labeled `non-SPS`, out of scope for clustering but tracked) | No (© Sierra Club) |
| USGS GNIS California + Nevada state files | decimal lat/long for every peak, matched on **name + USGS quad** | Yes (public domain) |

All 247 SPS peaks have coordinates: **241 from GNIS** (incl. 14 spelling/wording
aliases like *Foerster*↔*Forester*, *Maclure*↔*MacClure*) and **6 unofficially
named peaks** (Taylor Dome, Spanish Needle, Rockhouse Peak, Cartago Peak, North
Maggie Mountain, Clyde Minaret) from peakbagger.com. Each row records its
`coord_source`.

### Rebuilding the dataset

Only needed to rebuild from scratch; requires the Sierra Club source documents
in `data/source/` (not bundled — the scripts print a download reminder if
missing).

```bash
# 1. Parse the Sierra Club sources -> data/sps_peaks.csv (coords blank)
python scripts/build_dataset.py

# 2. Join GNIS coordinates (uses the committed Sierra subset)
python scripts/merge_gnis.py
```

`scripts/merge_gnis.py` holds the curated alias map and the 6 manual
peakbagger coordinates; `data/source/gnis_sierra_summits.txt` is a trimmed
Sierra-box GNIS subset committed for reproducibility.

### Trailheads

`data/trailheads.csv` is a curated list of ~40 major east-, west-, and
crest-side Sierra trailheads with lat/long (coordinates to ~0.001° and
spot-checked against public sources such as the PCTA and NPS). Run

```bash
python scripts/assign_trailheads.py
```

to add `nearest_trailhead`, `nearest_trailhead_side`, and
`nearest_trailhead_mi` (straight-line) columns to `data/sps_peaks.csv`. The
nearest-trailhead is a cleaner access signal than the raw `trailhead` text and
can be used directly for clustering (`--trailhead-field nearest_trailhead`).

### Mountain passes (crest-aware routing)

`data/passes.csv` is the Sierra pass dataset (sourced from USGS GNIS feature
class `Gap`; see [`data/source/README.md`](data/source/README.md) to rebuild and
backfill elevations). Each pass carries a **tier**: tier 1 = named passes/cols
(default crossing set, and the points that define the crest line); tier 2 =
minor gaps/saddles.

Pass routing is **opt-in**. By default all distances are straight-line. With
`--use-passes`, a leg between two points on opposite sides of the Sierra crest
is routed over the cheapest pass instead of tunnelling through the ridge; a leg
that stays on one side is still direct (you don't always cross a pass to reach a
peak). This affects clustering, the TSP order, the reported mileage/gain, and
adds a `passes_crossed` list per trip in the JSON.

```bash
python cli.py -i data/sps_peaks.csv --use-passes            # named passes only
python cli.py -i data/sps_peaks.csv --use-passes --pass-tier 2   # also minor gaps
python scripts/assign_trailheads.py --use-passes            # crest-aware approach
```

The crest is approximated by a monotone longitude/latitude line fit over the
tier-1 passes, so peaks sitting almost *on* the crest can be assigned a side
coarsely; denser pass data (`merge_passes.py --add-all`) sharpens it.

### Input schema

Minimum required columns are `name`, `latitude`, `longitude`, `elevation_ft`
(common aliases like `lat`/`lon`/`elevation` are accepted). The full dataset
also carries `list`, `class`, `section`, `emblem`, `mountaineers`,
`mileage_rt`, `gain_ft`, `loss_ft`, `trailhead`, `quad`, `coord_source`,
`benchmark`/`benchmark_rating` (see `scripts/parse_benchmarks.py`) and
`nearest_trailhead*` (see `scripts/assign_trailheads.py`), which flow through to
the JSON export as per-peak `attributes`. JSON input is also supported (a list
of objects, or `{"peaks": [...]}`).

---

## How it works

```
peaks (CSV/JSON)
      │  (filter to one list, e.g. SPS; skip rows without coordinates)
      ▼
┌─────────────────────────┐   great-circle distance (haversine)
│ 1. Spatial grouping     │   Naismith effort adjustment for ascent
│    DBSCAN over a        │
│    distance matrix      │
└─────────────────────────┘
      │  natural geographic groups (outliers → singleton trips)
      ▼
┌─────────────────────────┐   any group whose route exceeds the trip budget
│ 2. Capacity splitting   │   (max_days × miles_per_day) is split with
│    agglomerative split  │   agglomerative clustering until every trip fits.
└─────────────────────────┘   Feasibility uses a fast nearest-neighbor upper
      │                        bound, so statewide (~250 peak) runs stay quick.
      ▼
┌─────────────────────────┐   exact brute force (≤ 8 peaks)
│ 3. TSP ordering         │   nearest-neighbor + 2-opt (larger)
│    open Hamiltonian path│
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐   score = peaks / (1 + effective_mi / 10)
│ 4. Rank + export JSON   │
└─────────────────────────┘
```

### Distance & effort model

- **Horizontal distance**: great-circle (haversine) miles between summits — a
  good proxy for off-trail class 1–2 travel.
- **Naismith's Rule**: 1 hr per 3 horizontal miles + 1 hr per 2000 ft ascent, so
  2000 ft of climbing ≈ 3 "effective" flat miles. Effective miles are summed
  leg-by-leg; descending adds no penalty (standard simple form).
- **Trip budget**: `max_effective_mi = miles_per_day × max_days` (default
  `15 × 3 = 45`). Estimated days = `ceil(effective_mi / miles_per_day)`, capped
  at `max_days`.

### Approach modeling (`--include-approach`)

By default the route covers only **summit-to-summit** travel. With
`--include-approach` the tool also models the **trailhead approach** — the walk
from the car to the first summit and the descent from the last back — using
`data/trailheads.csv`:

1. **Trailhead choice.** Each trip is anchored to the single trailhead that best
   serves it: the most common `nearest_trailhead` among its peaks (ties broken by
   proximity to the cluster centroid), falling back to the trailhead nearest the
   centroid.
2. **Re-anchored routing.** The trailhead is added as a fixed start/end node and
   the trip is solved as a **closed tour** (`solve_tsp_cycle`), so the entry and
   exit summits are chosen to minimize the whole loop — not just inter-peak
   travel.
3. **Approach cost (hybrid).** Each in/out leg is priced from the data we already
   have: when the chosen trailhead is that peak's standard `nearest_trailhead`, we
   use its authoritative `mileage_rt / 2` and one-way `gain_ft`; otherwise we fall
   back to great-circle distance × a sinuosity factor (default `1.25`) with the
   trailhead→summit elevation delta. The inbound leg ascends (Naismith penalty);
   the outbound leg descends (no penalty). A single-peak trip reduces exactly to
   the official round trip.

The approach is folded into `total_distance_mi`, `total_effective_mi`,
`total_elevation_gain_ft`, `estimated_days` and `efficiency_score`, and reported
separately as `approach_*` plus `trailhead` / `trailhead_side`. The effect is
realistic: the Palisades traverse, a "1-day / 11 effective-mi" trip on the bare
inter-peak model, becomes **~28 effective mi over 2 days** once the Glacier Lodge
approach is counted.

```bash
python cli.py -i data/sps_peaks.csv --include-approach --max-days 2 -o weekend.json
```

> **Approach-aware capacity splitting.** With `--include-approach`, the trip
> budget is enforced *including* the approach: capacity splitting starts from the
> inter-peak floor (the fewest trips the bare traverse allows) and tightens only
> if a modest extra split actually makes the trips fit once the walk-in is
> counted. Because the approach is largely a fixed per-trip cost, the splitter
> will **not** fragment a trip when splitting can't help (an approach-dominated
> cluster stays whole rather than paying the approach several times over). Net
> effect: trip counts respect the *real* day budget while still using the fewest
> feasible trips.

### Approach-amortization report (`--approach-report`)

The approach is a fixed cost paid once per trip, so when several trips share one
trailhead that cost is paid several times over. This report (which implies
`--include-approach`) ranks the trailheads serving more than one trip by how much
approach effort could be recovered by repacking their trips within the day
budget:

```bash
python cli.py -i data/sps_peaks.csv --approach-report --max-days 3
```

```
trailhead                    side  trips peaks  appr_mi per_trip min_trips  save_mi
Mineral King                 west      6    22    139.1     23.2         5     23.2
Carson Pass                  west      4     6     41.2     10.3         2     20.6
Sage Flat (Olancha)          east      3     6     48.2     16.1         2     16.1
...
16 trailheads serve multiple trips; ~133.5 effective approach-mi potentially
recoverable by repacking within the day budget.
```

`min_trips` is the fewest trips the trailhead's combined effort could occupy at
the budget; `save_mi` is the approach freed by reaching it. The report is a
*signal*, bounded by the day budget, not a promise. Raising `--max-days` unlocks
more amortization (~133 mi recoverable at 3 days vs ~80 at 2).

### Permit report (`--permits`)

Every trailhead in `data/trailheads.csv` is tagged with a wilderness area,
issuing agency, and a `permit_group` key into `data/permits.csv` — a curated
table of permit type, quota season, reservation window/method, fees, and the
official apply URL for each agency covering the SPS range (Inyo NF, Sierra NF,
Sequoia NF, Stanislaus NF, Eldorado NF/LTBMU, Humboldt-Toiyabe NF, Yosemite NP,
and Sequoia & Kings Canyon NP, including the separate Mt. Whitney Zone lottery).

`--permits` (which implies `--include-approach`, since it needs each trip's
chosen trailhead) prints, per trip, the permit type, whether `--trip-date`
falls in that area's quota season, and — if so — when the reservation window
opens relative to today:

```bash
python cli.py -i data/sps_peaks.csv --permits --trip-date 2027-07-15 --max-days 3
```

```
Cluster #2 -- Whitney Portal  (trip date 2027-07-15)
  Wilderness: Mount Whitney Zone (John Muir Wilderness)  |  Agency: Inyo National Forest
  Permit: Mount Whitney Zone Permit
  Status: Lottery for 2027 opens Feb 1; apply by Mar 1.
  Fee: $15/person plus $6 processing fee
  Apply: https://www.recreation.gov/permits/445860
```

Run it once per candidate month across your 12-month planning window (or loop
`--trip-date` over several dates) to see, trip by trip, which ones need a
lottery entry, a 6-month rolling reservation, a day-of walk-up, or nothing at
all.

**Which agency issues the permit — and interagency reciprocity.** The permit
you need is determined by the *trailhead you start from*, not by which
wilderness or park each individual peak in the trip happens to sit in. Sierra
Nevada wilderness permits are interagency: a permit issued for your starting
trailhead is honored for the whole continuous trip even where the route
crosses into a neighboring wilderness or national park, so you do **not**
need a second permit from whoever's land you pass through — as long as the
trip both starts and ends at the trailhead the permit was issued for. For
example, a free self-issue Emigrant Wilderness permit picked up for a
Stanislaus NF trailhead covers a route that crosses into Yosemite at Bond
Pass; a Sierra NF permit from Clover Meadow covers the leg over Isberg Pass
into Yosemite to reach Foerster Peak; a Hoover Wilderness permit from Twin
Lakes covers the crossing into Yosemite's Kerrick Canyon for Tower Peak. When
a trip's trailhead permit has this kind of cross-boundary reach, the report
prints a `Crosses into other land:` line explaining it — but a few boundary
crossings have their own procedural wrinkle (e.g. the Kibbie Lake/Lake
Eleanor corridor out of Stanislaus NF requires calling Yosemite's Groveland
Ranger District a day ahead), so read that line rather than assuming blanket
reciprocity everywhere.

**Per-peak permit overrides.** A trailhead's `permit_group` is a default, not
a guarantee for every peak reached from it — some trailheads serve more than
one permitted trail with different rules. Whitney Portal is the clearest
example: the classic Mt. Whitney Trail (Mount Whitney, Mount Muir) is covered
by the Whitney Zone lottery, but Mount Russell is reached via the
Mountaineers Route / North Fork of Lone Pine Creek trail, which Inyo NF
explicitly excludes from that lottery and instead permits under its regular
John Muir Wilderness system. `data/permit_overrides.csv` (peak name →
permit_group) captures known cases like this; `--permits` prints an extra
entry tagged `[for <peak> only]` alongside the trailhead's default when a
cluster mixes peaks that need different permits. This file is deliberately
conservative — only peaks with a directly-named source are listed. Other
Whitney-Portal-served peaks likely need the same treatment but aren't listed
because their exact approach trail isn't confirmed yet: **Thor Peak, Mount
Irvine, Mount McAdie, Mount Mallory, Mount LeConte, and Mount Corcoran**
(commonly reached via the separate Meysan Lakes Trail) and **Mount Carillon**
(adjacent to Mount Russell on the Mountaineers Route side). If your trip
includes any of these, verify the actual permit with Inyo NF rather than
trusting the default Whitney Zone entry the tool shows for that trailhead.

**Provenance: two dates, not one.** Every row in `data/permits.csv` carries
two separate dates, both printed as a `Provenance:` line in the report:
`source_last_updated` is the date the *source itself* says it was last
updated (e.g. an fs.usda.gov page's own "Last updated" footer, or a PDF's
filename date) — this is a fact about the source, not about this repo.
`verified_date` is the date *this dataset* was last checked against that
source. The two commonly disagree: a source can say "last updated 2021" and
still be the newest information we have, checked yesterday — or a source can
say "last updated this month" but not have been independently checked here
at all yet, in which case `verified_date` is blank and the report prints
`NOT independently verified against a primary source (web-search synthesis
only)` instead. Treat any row with an old `source_last_updated` (the Inyo NF
trailhead/quota PDF this project used is dated 2021-06-13) or a blank
`verified_date` as lower-confidence than one checked recently against a
freshly-updated source, and re-verify before relying on it for an actual
booking deadline.

**Catching disagreement between sources (`--permit-sources`).** `permits.csv`
only stores the *current best answer* per permit — each edit overwrites the
last one, so on its own it can't reveal that two sources disagreed.
`data/permit_source_log.csv` is the append-only complement: one row per
verification event (never edited, only appended to), recording the source
URL, the source's own update date, how it was checked, and a verdict —
`new-group`, `confirms-existing`, `corrects-existing`, or
`unresolved-conflict`. See the full history for one permit, or everything:

```bash
python cli.py --permit-sources whitney_zone   # one group's history
python cli.py --permit-sources                # everything, conflicts first
```

That second command prints an `UNRESOLVED CONFLICTS:` line up top listing
any permit_group whose *most recent* logged entry disagrees with an earlier
one and hasn't been reconciled yet. **The workflow when you find a new
source:** append a row to `permit_source_log.csv` describing what it says.
If it agrees with the current data, mark it `confirms-existing`. If it
disagrees, mark it `unresolved-conflict` and describe the discrepancy
*before* deciding which one is right — don't silently overwrite. Once you've
worked out which source wins (and why — more recent, more authoritative,
more specific), update `permits.csv` and append one more log row marked
`corrects-existing` explaining the resolution. Because the log is read in
chronological order, that follow-up entry is what makes the group stop
showing up as an unresolved conflict — the history of the disagreement stays
visible, it's just no longer flagged as live. `--permit-sources` doesn't
need `--input` or trip data; it's a standalone audit tool.

> **This is a planning aid, not a booking guarantee.** Quota-season dates,
> reservation windows, and lottery timing shift year to year and by trailhead.
> `data/permits.csv` was curated from official NPS/USFS/recreation.gov sources
> in July 2026 — always confirm against the linked `apply_url` before relying
> on a date.

---

## Installation

```bash
cd projects/sierra-peaks-clustering
pip install -r requirements.txt   # pandas, numpy, scikit-learn, scipy, networkx, geopy; matplotlib for --viz
```

Python 3.10+.

---

## Usage

```bash
# Cluster the full SPS list (SPS-only is the default when a 'list' column exists)
python cli.py --input data/sps_peaks.csv --output out.json --viz clusters.png
```

```
53 trips | 247 peaks | 69 trip-days | 407.43 horiz mi | 43081 ft gain

 #  pk  days  horiz_mi   eff_mi   gain_ft   score  route
 0  12     1       9.0     11.2      1479    5.66  Disappointment Peak -> Middle Palisade -> Norman Clyde Peak -> ...
 1  13     2      14.1     16.1      1332    4.98  Mount Goethe -> Mount Lamarck -> Mount Mendel -> MOUNT DARWIN -> ...
 2  11     2      12.4     15.8      2211    4.27  Mount Young -> Mount Hale -> Mount Muir -> MOUNT WHITNEY -> ...
 ...
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input, -i` | *(required)* | peak CSV or JSON file |
| `--output, -o` | – | write ranked itineraries to this JSON file |
| `--list` | `SPS` | keep only this `list` value (`all` keeps everything) |
| `--eps-mi` | `6.0` | spatial grouping radius (horizontal miles) |
| `--miles-per-day` | `15.0` | effective hiking miles per day |
| `--max-days` | `3` | maximum days per trip |
| `--include-approach` | off | model the trailhead approach (walk in/out) and fold it into distance, effort, days & score |
| `--approach-report` | off | print an approach-amortization report (implies `--include-approach`) |
| `--trailheads` | `data/trailheads.csv` | trailhead file used with `--include-approach` |
| `--permits` | off | print a permit report per trip (implies `--include-approach`) |
| `--trip-date` | today | planned trip start date (`YYYY-MM-DD`) used by `--permits` |
| `--permits-file` | `data/permits.csv` | permit rules dataset used by `--permits` |
| `--permit-overrides-file` | `data/permit_overrides.csv` | peak-level permit_group overrides used by `--permits` |
| `--permit-sources [GROUP]` | off | print the permit source-verification log (optionally filtered) and exit; doesn't need `--input` |
| `--permit-source-log-file` | `data/permit_source_log.csv` | source log dataset for `--permit-sources` |
| `--method` | `dbscan` | grouping method: `dbscan` or `agglomerative` |
| `--exclude` | – | comma-separated peak names to drop |
| `--force-together` | – | comma-separated peaks to keep in one trip (repeatable) |
| `--merge` | – | comma-separated cluster IDs to merge, then re-plan (repeatable) |
| `--split` | – | split a cluster: `ID:K` (repeatable) |
| `--viz` | – | write a matplotlib PNG (per-peak labels auto-hide above 40 peaks) |

### Manual tweaking

```bash
# Force the Palisade 14ers together, exclude a sub-peak, tighten the daily budget
python cli.py -i data/sps_peaks.csv \
    --force-together "NORTH PALISADE,Polemonium Peak,Thunderbolt Peak,Mount Sill" \
    --exclude "Mount Muir" --miles-per-day 12 --max-days 2

python cli.py -i data/sps_peaks.csv --merge 5,6      # merge trips #5 and #6, re-plan
python cli.py -i data/sps_peaks.csv --split 4:2      # split trip #4 into 2
```

`--merge` applies to first-pass IDs; `--split` applies afterward. After each
edit the trips are re-ordered (TSP) and re-ranked so metrics stay consistent.

### Python API

```python
from sierra_peaks import load_peaks, ClusterConfig
from sierra_peaks.pipeline import plan_trips
from sierra_peaks.export import save_json

peaks = load_peaks("data/sps_peaks.csv", list_filter="SPS")
clusters = plan_trips(peaks, ClusterConfig(eps_mi=6, miles_per_day=15, max_days=3))
save_json(clusters, "out.json")
```

---

## Output schema (`examples/sps_full_output.json`)

```jsonc
{
  "summary": { "num_clusters": 53, "total_peaks": 247, "total_estimated_days": 69,
               "total_distance_mi": 407.43, "total_elevation_gain_ft": 43081 },
  "clusters": [
    {
      "cluster_id": 0,
      "num_peaks": 12,
      "peaks": [ { "name": "MOUNT SILL", "latitude": 37.0942, "longitude": -118.5042,
                   "elevation_ft": 14159,
                   "attributes": { "list": "SPS", "class": "3", "section": 14.4,
                                   "emblem": false, "mountaineers": false,
                                   "mileage_rt": 11.9, "gain_ft": 7685, "trailhead": "...",
                                   "quad": "North Palisade", "coord_source": "GNIS" } } ],
      "recommended_order": ["Disappointment Peak", "Middle Palisade", "..."],
      "total_distance_mi": 9.0, "total_effective_mi": 11.2,
      "total_elevation_gain_ft": 1479, "estimated_days": 1,
      "efficiency_score": 5.66, "emblem_peaks": 1, "mountaineers_peaks": 4
    }
  ]
}
```

With `--include-approach`, each cluster also carries `trailhead`,
`trailhead_side`, `approach_distance_mi`, `approach_effective_mi` and
`approach_gain_ft`, and the `total_*` figures include that approach.

`total_distance_mi`/`total_effective_mi`/`total_elevation_gain_ft` are the
**inter-peak** route totals the optimizer computes; each peak's `attributes`
also carry the official **per-peak round-trip** `mileage_rt`/`gain_ft` from the
trailhead, for reference.

---

## Example: statewide SPS plan (default settings)

53 trips across the range. A few of the top-ranked:

| # | Peaks | Days | Eff. mi | Gain | The group |
|---|------:|-----:|--------:|-----:|-----------|
| 0 | 12 | 1 | 11.2 | 1,479 | **Palisades** — Middle Pal, Norman Clyde, Sill, N. Palisade, Thunderbolt, Agassiz, Temple Crag … |
| 1 | 13 | 2 | 16.1 | 1,332 | **Evolution** — Darwin, Mendel, Lamarck, Goethe, Huxley, Haeckel, Powell, Thompson, Goode … |
| 2 | 11 | 2 | 15.8 | 2,211 | **Whitney/Williamson** — Whitney, Muir, Russell, Williamson, Tyndall, Barnard … |
| 3 | 7 | 1 | 6.9 | 676 | **Brewer group** — Brewer, North/South Guard, Table, Midway, Milestone … |
| 6 | 16 | 3 | 33.6 | 2,710 | **Mono Divide** — Abbot, Mills, Gabb, Dade, Bear Creek Spire, Hilgard, Recess … |
| 12 | 9 | 2 | 22.5 | 793 | **Sawtooth/Matterhorn** — Matterhorn, Whorl, Virginia, Conness, North Peak, Dunderberg … |

![Statewide SPS clusters](examples/sps_full_clusters.png)

A small 30-peak demo dataset (`data/sps_sample.csv`) and its output are also
included for quick experimentation.

---

## Project layout

```
sierra-peaks-clustering/
├── cli.py                       # command-line entry point
├── requirements.txt
├── data/
│   ├── sps_peaks.csv            # authoritative 247 SPS + 354 non-SPS peaks
│   ├── sps_sample.csv           # 30-peak demo subset
│   ├── trailheads.csv           # trailheads incl. wilderness area / agency / permit_group
│   ├── permits.csv              # permit rules per permit_group (quota season, apply URL...)
│   ├── permit_overrides.csv     # peak-level permit_group overrides (see Permit report)
│   ├── permit_source_log.csv    # append-only source-verification audit trail
│   └── source/                  # official Sierra Club files + trimmed GNIS subset
├── scripts/
│   ├── build_dataset.py         # XLS + non-SPS PDF -> sps_peaks.csv
│   ├── merge_gnis.py            # join GNIS coordinates (name + quad)
│   └── merge_coords.py          # generic GPX/KML/CSV/JSON coordinate joiner
├── examples/
│   ├── sps_full_output.json     # statewide 53-trip plan
│   ├── sps_full_clusters.png    # statewide map
│   └── example_output.json      # demo-dataset output
├── sierra_peaks/
│   ├── model.py                 # Peak / Cluster
│   ├── data_loader.py           # CSV/JSON loading, list filter, metadata
│   ├── distances.py             # haversine + Naismith effort model
│   ├── clustering.py            # DBSCAN grouping + capacity splitting
│   ├── tsp.py                   # open-path TSP (brute force / 2-opt)
│   ├── pipeline.py              # cluster → order → score → rank
│   ├── manual.py                # merge / split / exclude / force-together
│   ├── export.py                # JSON export
│   ├── permits.py               # permit lookup + date-aware quota/reservation status
│   └── visualize.py             # optional matplotlib map
└── tests/
    ├── test_pipeline.py         # clustering/routing/approach unit & integration tests
    └── test_permits.py          # permit-lookup unit tests
```

Run the tests: `python -m pytest tests/` (or `python tests/test_pipeline.py`).

---

## Notes, assumptions & extension points

- **Off-trail assumption.** Inter-peak travel is straight-line great-circle
  distance, appropriate for class 1–2 ridge/basin travel. It does not model
  cliffs or technical terrain. The trailhead approach is off by default but can
  be modeled with `--include-approach` (see above), which uses the official
  per-peak `mileage_rt`/`gain_ft` and the curated `data/trailheads.csv`.
- **Trail-network distances (optional).** The distance layer is isolated in
  `distances.py`; swap `build_distance_matrix` for shortest paths over a
  `networkx` graph built from USFS/NPS trail shapefiles, and everything
  downstream is unchanged.
- **Elevation gain** is the sum of positive summit-to-summit deltas along the
  route — a lower bound that ignores intermediate ups-and-downs.
- **Permits** (`--permits`, see above) are a planning aid, not a booking
  system: `data/permits.csv` is a manually curated snapshot of quota seasons,
  reservation windows and lottery timing, which agencies change from year to
  year. It doesn't call recreation.gov or check live availability. Always
  confirm against the linked `apply_url` before relying on a date.
```

---

## License & data

The **source code** is licensed under the [MIT License](LICENSE).

The **data** has separate provenance and terms — see
[`DATA_LICENSE.md`](DATA_LICENSE.md). In particular, the Sierra Club source
documents in `data/source/` are copyrighted; review `DATA_LICENSE.md` before
making a public copy of this repository. Peak data derives from the Sierra Club
SPS list and **USGS GNIS** (public domain); map tiles are © OpenStreetMap
contributors / OpenTopoMap (CC-BY-SA) / Esri.

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) and our
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Please run the tests and cite
sources for any data corrections.
