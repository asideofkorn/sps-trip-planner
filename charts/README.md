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

## Regenerate

```bash
python cli.py -i data/sps_peaks.csv \
  --eps-mi 6 --miles-per-day 15 \
  --viz charts/sps_clusters_balanced_6mi-15mpd_$(date +%F).png
```
