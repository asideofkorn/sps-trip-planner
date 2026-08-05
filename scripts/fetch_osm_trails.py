#!/usr/bin/env python3
"""Fetch the Sierra Nevada trail network from OpenStreetMap.

This is the network-dependent companion to ``sierra_peaks/trails.py``. It
pulls path/footway/track/bridleway/steps ways from OpenStreetMap (via the
Overpass API, through the ``osmnx`` package) over the same Sierra bounding
box used elsewhere in the pipeline (``scripts/build_gnis_gaps.py``,
``scripts/merge_passes.py``), and writes the result as a static GraphML
artifact at ``data/trails.graphml``.

Deliberately **not** filtered to osmnx's "hike" network-type preset, which
excludes informal/unofficial use-trails -- those are common on SPS class 2-3
approaches and dropping them would make the graph sparser than the terrain
actually is. ``sac_scale``/``trail_visibility``/``informal``/``surface`` are
carried through as edge attributes for possible future difficulty-weighted
routing, even though ``sierra_peaks/trails.py`` only uses plain ``length_mi``
today.

Requires ``osmnx`` (``pip install -e .[trails]``) -- a fetch-only dependency;
the runtime library (``sierra_peaks/trails.py``) loads the resulting GraphML
file with plain ``networkx`` and never imports ``osmnx``.

Network is required. Overpass queries over a region this size can take
several minutes; be considerate of the public Overpass API's usage policy
(this is a one-off, manually-run fetch, not something the CLI/library ever
calls automatically).

Usage:
    python scripts/fetch_osm_trails.py
    python scripts/fetch_osm_trails.py --bbox 35.0,41.5,-121.0,-117.0 \\
        --out data/trails.graphml
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "trails.graphml"

# (lat_min, lat_max, lon_min, lon_max) -- matches sierra_peaks.trails.SIERRA_BBOX,
# scripts/build_gnis_gaps.py, and scripts/merge_passes.py.
SIERRA_BBOX = (35.0, 41.5, -121.0, -117.0)

CUSTOM_FILTER = '["highway"~"path|footway|track|bridleway|steps"]["area"!~"yes"]'

EDGE_TAGS_TO_KEEP = ("name", "ref", "sac_scale", "trail_visibility",
                     "informal", "surface", "highway")


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "--bbox must be 'lat_min,lat_max,lon_min,lon_max'"
        )
    return tuple(parts)  # type: ignore[return-value]


def fetch_graph(bbox: tuple[float, float, float, float]):
    """Fetch the trail network over ``bbox`` as a plain (non-multi, undirected)
    networkx.Graph with float ``y``/``x`` node attrs and float ``length_mi``
    edge attrs -- the shape ``sierra_peaks.trails.load_trail_graph`` expects.
    """
    import networkx as nx
    import osmnx as ox

    lat_min, lat_max, lon_min, lon_max = bbox
    raw = ox.graph_from_bbox(
        (lon_min, lat_min, lon_max, lat_max),
        custom_filter=CUSTOM_FILTER,
        simplify=True,
        retain_all=False,
    )
    raw = ox.distance.add_edge_lengths(raw)  # adds edge "length" in meters
    undirected = ox.convert.to_undirected(raw)

    graph = nx.Graph()
    for node, data in undirected.nodes(data=True):
        graph.add_node(node, y=float(data["y"]), x=float(data["x"]))
    for u, v, data in undirected.edges(data=True):
        length_mi = float(data.get("length", 0.0)) / 1609.344
        attrs = {"length_mi": length_mi}
        for tag in EDGE_TAGS_TO_KEEP:
            val = data.get(tag)
            if val is not None:
                # osmnx sometimes carries list-valued tags (e.g. multiple refs).
                attrs[tag] = str(val[0]) if isinstance(val, list) else str(val)
        if graph.has_edge(u, v):
            if graph[u][v]["length_mi"] <= length_mi:
                continue
        graph.add_edge(u, v, **attrs)
    return graph


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bbox", type=_parse_bbox, default=SIERRA_BBOX,
                    help="lat_min,lat_max,lon_min,lon_max (default: Sierra bbox)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"Output GraphML path (default {DEFAULT_OUT})")
    args = p.parse_args(argv)

    try:
        import osmnx  # noqa: F401
    except ImportError:
        print("error: osmnx is required to fetch trail data. "
              "Install with: pip install -e .[trails]")
        return 1

    print(f"Fetching OSM trail network for bbox {args.bbox} ...")
    graph = fetch_graph(args.bbox)
    print(f"Fetched {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    import networkx as nx
    args.out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, args.out)
    size_mb = args.out.stat().st_size / (1024 * 1024)
    print(f"Wrote {args.out} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
