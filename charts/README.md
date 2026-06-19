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

## Benchmark progression charts

Derived from the SPS **Benchmark Routes** sheet (`data/source/benchmark_routes.pdf`),
which anchors each Scrambler Rating category (S-1.0 … S-4.2) with reference
climbs. Useful for picking starter objectives and building up by difficulty.

| File | What it shows |
|------|---------------|
| `benchmark_progression_ladder_2026-06-19.png` | All 24 benchmark routes laid out easiest→hardest (one peak can appear at several ratings, e.g. Mount Whitney at S-1.0 and S-3.1). |
| `benchmark_peaks_map_2026-06-19.png` | The 23 benchmark peaks plotted geographically, coloured by YDS class, labelled with each peak's easiest benchmark rating. |

## Regenerate

```bash
# Cluster charts
python cli.py -i data/sps_peaks.csv \
  --eps-mi 6 --miles-per-day 15 \
  --viz charts/sps_clusters_balanced_6mi-15mpd_$(date +%F).png

# Benchmark data + charts
python scripts/parse_benchmarks.py        # -> data/benchmark_routes.csv
python scripts/plot_benchmarks.py         # -> charts/benchmark_*_<date>.png
```
