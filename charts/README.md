# SPS Cluster Charts

Versioned visualizations of Sierra Peaks Section (SPS) peak clusters and
suggested TSP routes. All charts cover the **247 SPS-list peaks** only
(non-SPS peaks excluded via the default `--list SPS`).

Naming convention: `sps_clusters_<profile>_<eps>mi-<miles-per-day>mpd_<YYYY-MM-DD>.png`

| File | Profile | Params | Trips | Est. days |
|------|---------|--------|-------|-----------|
| `sps_clusters_balanced_6mi-15mpd_2026-06-19.png` | Balanced | `--eps-mi 6 --miles-per-day 15` | 53 | 69 |
| `sps_clusters_dayhike_4mi-12mpd_2026-06-19.png` | Conservative day-hikes | `--eps-mi 4 --miles-per-day 12` | 72 | 87 |
| `sps_clusters_backpack_9mi-18mpd_2026-06-19.png` | Multi-day backpacks | `--eps-mi 9 --miles-per-day 18 --max-days 3` | 44 | 56 |
| `sps_clusters_by-trailhead_6mi-15mpd_2026-06-19.png` | Grouped by access trailhead | `--eps-mi 6 --by-trailhead` | 68 | 87 |

| `sps_clusters_by-nearest-trailhead_6mi-cap15_2026-06-19.png` | Grouped by nearest curated trailhead | `--by-trailhead --trailhead-field nearest_trailhead --trailhead-max-mi 15` | 35 | 64 |

`--by-trailhead` keeps every peak sharing a trailhead in one trip (then eps still
merges nearby trailheads), producing natural "basecamp at one trailhead, bag
everything reachable" expeditions (e.g. Mount Whitney Trail = 16 peaks, Shepherd
Pass = 13).

Two refinements address the messy raw `trailhead` text (which mixes point
trailheads with long trail names like **Pacific Crest Trail** — 8 peaks spanning
~240 mi):

* `--trailhead-max-mi N` only links same-trailhead peaks within N straight-line
  miles, so long trails break into sensible chunks.
* `--trailhead-field nearest_trailhead` groups on the geographically nearest
  curated trailhead (see `data/trailheads.csv`) instead, giving the cleanest
  map — 35 tidy per-trailhead expeditions, no cross-range lines.

## Benchmark progression charts

Derived from the SPS **Benchmark Routes** sheet (`data/source/benchmark_routes.pdf`),
which anchors each Scrambler Rating category (S-1.0 … S-4.2) with reference
climbs. Useful for picking starter objectives and building up by difficulty.

| File | What it shows |
|------|---------------|
| `benchmark_progression_ladder_2026-06-19.png` | All 24 benchmark routes laid out easiest→hardest (one peak can appear at several ratings, e.g. Mount Whitney at S-1.0 and S-3.1). |
| `benchmark_peaks_map_2026-06-19.png` | The 23 benchmark peaks plotted geographically, coloured by YDS class, labelled with each peak's easiest benchmark rating. |

## Interactive topo maps (HTML)

`scripts/map_clusters.py` renders trips onto a pan/zoom Leaflet map with
switchable open basemaps. The default **OpenTopoMap** layer is OpenStreetMap
data and shows the **hiking-trail network** (JMT, PCT, use-trails) plus
contours, so you can see each trip against real trails and terrain. Also
includes OpenStreetMap and Esri satellite layers, and toggleable overlays for
trip routes, peaks (coloured by trip), benchmark peaks (★), and trailheads (⌂).

Open the `.html` in any browser — tiles load client-side, so no setup is needed.

| File | Clustering |
|------|------------|
| `sps_map_balanced_6mi_2026-06-19.html` | spatial, `--eps-mi 6` (53 trips) |
| `sps_map_nearest-trailhead_2026-06-19.html` | `--by-trailhead --trailhead-field nearest_trailhead --trailhead-max-mi 15` (35 trips) |

## Regenerate

```bash
# Cluster charts
python cli.py -i data/sps_peaks.csv \
  --eps-mi 6 --miles-per-day 15 \
  --viz charts/sps_clusters_balanced_6mi-15mpd_$(date +%F).png

# Benchmark data + charts
python scripts/parse_benchmarks.py        # -> data/benchmark_routes.csv
python scripts/plot_benchmarks.py         # -> charts/benchmark_*_<date>.png

# Interactive topo map (trails + contours via OpenTopoMap)
python scripts/map_clusters.py -i data/sps_peaks.csv -o charts/sps_map.html \
  --by-trailhead --trailhead-field nearest_trailhead --trailhead-max-mi 15
```
