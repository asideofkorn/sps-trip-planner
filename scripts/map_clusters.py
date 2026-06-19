"""Render SPS clusters onto an interactive topographic map (Leaflet / folium).

Produces a self-contained ``.html`` file you can open in any browser and pan /
zoom around the Sierra. Basemaps are switchable in the top-right layer control:

  * **OpenTopoMap** — OpenStreetMap-based topo with contours AND the hiking-trail
    network (JMT, PCT, use-trails, etc.), so you can see trips against real
    trails and terrain.
  * **OpenStreetMap** — standard street/path map.
  * **Esri World Imagery** — satellite.

Layers (toggleable): trip routes, peaks (coloured by trip), benchmark peaks,
and trailheads.

Tiles are fetched by the browser when the file is opened — no network is needed
to *generate* the HTML.

Usage:
    python scripts/map_clusters.py -i data/sps_peaks.csv -o map.html
    python scripts/map_clusters.py -i data/sps_peaks.csv -o map.html \
        --by-trailhead --trailhead-field nearest_trailhead --trailhead-max-mi 15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import folium
import pandas as pd

from sierra_peaks.data_loader import load_peaks
from sierra_peaks.clustering import ClusterConfig
from sierra_peaks.pipeline import plan_trips

# A repeating palette of visually distinct colours for trips.
PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
    "#f032e6", "#bcf60c", "#fabebe", "#008080", "#9a6324", "#800000",
    "#808000", "#000075", "#e6beff", "#aaffc3", "#ffd8b1", "#808080",
]


def _basemaps(fmap: folium.Map) -> None:
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="Map data: © OpenStreetMap contributors, SRTM | "
             "Style: © OpenTopoMap (CC-BY-SA)",
        name="OpenTopoMap (trails + contours)", max_zoom=17,
    ).add_to(fmap)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
              "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri", name="Esri World Imagery (satellite)",
    ).add_to(fmap)


def _peak_popup(p, trip_id: int) -> str:
    m = p.meta
    rows = [f"<b>{p.name}</b>", f"Trip #{trip_id}",
            f"{int(p.elevation_ft):,} ft"]
    if m.get("class"):
        rows.append(f"Class {m['class']}")
    if m.get("benchmark_rating"):
        rows.append(f"Benchmark: {m['benchmark_rating']}")
    if m.get("nearest_trailhead"):
        d = m.get("nearest_trailhead_mi")
        rows.append(f"Nearest TH: {m['nearest_trailhead']}"
                    + (f" (~{d} mi)" if d is not None else ""))
    return "<br>".join(str(r) for r in rows)


def build_map(clusters, trailheads: pd.DataFrame | None, out: Path) -> None:
    all_lat = [p.latitude for c in clusters for p in c.peaks]
    all_lon = [p.longitude for c in clusters for p in c.peaks]
    center = [sum(all_lat) / len(all_lat), sum(all_lon) / len(all_lon)]

    fmap = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
    _basemaps(fmap)

    routes = folium.FeatureGroup(name="Trip routes", show=True)
    peaks_fg = folium.FeatureGroup(name="Peaks (by trip)", show=True)
    bench_fg = folium.FeatureGroup(name="Benchmark peaks", show=True)

    for c in clusters:
        color = PALETTE[c.cluster_id % len(PALETTE)]
        ordered = [(p.latitude, p.longitude) for p in c.peaks]
        if len(ordered) > 1:
            folium.PolyLine(
                ordered, color=color, weight=3, opacity=0.8,
                tooltip=f"Trip #{c.cluster_id}: {c.num_peaks} peaks, "
                        f"{c.estimated_days}d, {c.total_distance_mi:.0f} mi",
            ).add_to(routes)
        for p in c.peaks:
            folium.CircleMarker(
                location=(p.latitude, p.longitude), radius=5,
                color="#222", weight=1, fill=True, fill_color=color,
                fill_opacity=0.9,
                popup=folium.Popup(_peak_popup(p, c.cluster_id), max_width=260),
                tooltip=p.name,
            ).add_to(peaks_fg)
            if p.meta.get("benchmark"):
                folium.Marker(
                    location=(p.latitude, p.longitude),
                    icon=folium.Icon(color="green", icon="star", prefix="fa"),
                    tooltip=f"Benchmark {p.meta.get('benchmark_rating','')}: {p.name}",
                ).add_to(bench_fg)

    routes.add_to(fmap)
    peaks_fg.add_to(fmap)
    bench_fg.add_to(fmap)

    if trailheads is not None:
        th_fg = folium.FeatureGroup(name="Trailheads", show=True)
        for _, t in trailheads.iterrows():
            folium.Marker(
                location=(t["latitude"], t["longitude"]),
                icon=folium.Icon(color="black", icon="home", prefix="fa"),
                tooltip=f"{t['name']} ({t['side']}, {int(t['elevation_ft']):,} ft)",
                popup=folium.Popup(
                    f"<b>{t['name']}</b><br>{t['side']} side<br>"
                    f"{int(t['elevation_ft']):,} ft<br>{t.get('notes','')}",
                    max_width=260),
            ).add_to(th_fg)
        th_fg.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.save(str(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Interactive topo map of SPS clusters.")
    ap.add_argument("--input", "-i", default="data/sps_peaks.csv")
    ap.add_argument("--output", "-o", default="charts/sps_map.html")
    ap.add_argument("--trailheads", default="data/trailheads.csv")
    ap.add_argument("--eps-mi", type=float, default=6.0)
    ap.add_argument("--list", default="SPS")
    ap.add_argument("--by-trailhead", action="store_true")
    ap.add_argument("--trailhead-field", default="trailhead")
    ap.add_argument("--trailhead-max-mi", type=float, default=None)
    args = ap.parse_args(argv)

    list_filter = None if args.list.lower() == "all" else args.list
    peaks = load_peaks(args.input, list_filter=list_filter)
    config = ClusterConfig(
        eps_mi=args.eps_mi, by_trailhead=args.by_trailhead,
        trailhead_field=args.trailhead_field, trailhead_max_mi=args.trailhead_max_mi,
    )
    clusters = plan_trips(peaks, config)

    th = None
    th_path = Path(args.trailheads)
    if th_path.exists():
        th = pd.read_csv(th_path)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    build_map(clusters, th, out)
    print(f"Wrote interactive map with {len(clusters)} trips to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
