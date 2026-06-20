#!/usr/bin/env python3
"""Command-line interface for the Sierra Peaks clustering toolkit.

Examples
--------
Basic run on the sample data::

    python cli.py --input data/sps_sample.csv --output out.json

Tune the trip budget and DBSCAN radius, force a group together, exclude a peak::

    python cli.py --input data/sps_sample.csv \\
        --eps-mi 8 --miles-per-day 12 --max-days 2 \\
        --force-together "North Palisade,Polemonium Peak,Mount Sill,Thunderbolt Peak" \\
        --exclude "Mount Muir" \\
        --viz clusters.png

Manually merge clusters #4 and #5 from the first pass, then re-plan::

    python cli.py --input data/sps_sample.csv --merge 4,5
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from sierra_peaks.data_loader import load_peaks, load_trailheads
from sierra_peaks.clustering import ClusterConfig, cluster_peaks
from sierra_peaks.pipeline import build_itineraries, rank_clusters
from sierra_peaks import manual
from sierra_peaks.export import save_json, clusters_to_payload


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cluster Sierra Peaks into efficient 1-3 day peak-bagging trips.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", "-i", required=True, help="SPS peak CSV or JSON file")
    p.add_argument("--output", "-o", help="Write ranked itineraries to this JSON file")
    p.add_argument("--eps-mi", type=float, default=6.0,
                   help="Spatial grouping radius in horizontal miles (default 6)")
    p.add_argument("--min-samples", type=int, default=1,
                   help="DBSCAN min_samples (default 1)")
    p.add_argument("--miles-per-day", type=float, default=15.0,
                   help="Effective hiking miles per day (default 15)")
    p.add_argument("--max-days", type=int, default=3,
                   help="Maximum days per trip (default 3)")
    p.add_argument("--method", choices=["dbscan", "agglomerative"], default="dbscan",
                   help="Spatial grouping method (default dbscan)")
    p.add_argument("--exclude", default="",
                   help="Comma-separated peak names to exclude")
    p.add_argument("--force-together", action="append", default=[],
                   help="Comma-separated peaks to keep in one trip "
                        "(repeatable for multiple groups)")
    p.add_argument("--by-trailhead", action="store_true",
                   help="Keep peaks that share a trailhead in the same trip "
                        "(then eps still merges nearby trailheads)")
    p.add_argument("--trailhead-field", default="trailhead",
                   help="Metadata column to group on with --by-trailhead "
                        "(e.g. 'nearest_trailhead'; default 'trailhead')")
    p.add_argument("--trailhead-max-mi", type=float, default=None,
                   help="With --by-trailhead, only link same-trailhead peaks "
                        "within this straight-line distance (splits long trails "
                        "like the PCT)")
    p.add_argument("--merge", action="append", default=[],
                   help="Comma-separated cluster IDs to merge after the first pass "
                        "(repeatable)")
    p.add_argument("--split", action="append", default=[],
                   help="Split a cluster: ID:K (e.g. 2:3). Applied after merges. "
                        "(repeatable)")
    p.add_argument("--include-approach", action="store_true",
                   help="Model the trailhead approach (walk in to the first peak "
                        "and out from the last), folding it into distance, effort, "
                        "days and score")
    p.add_argument("--trailheads", default="data/trailheads.csv",
                   help="Trailhead CSV used with --include-approach "
                        "(default data/trailheads.csv)")
    p.add_argument("--list", default="SPS",
                   help="If the data has a 'list' column, keep only this list "
                        "(default SPS; use 'all' to keep everything)")
    p.add_argument("--viz", help="Write a matplotlib PNG of clusters/routes here")
    return p.parse_args(argv)


def _split_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _print_summary(clusters) -> None:
    payload = clusters_to_payload(clusters)
    s = payload["summary"]
    print(
        f"\n{len(clusters)} trips | {s['total_peaks']} peaks | "
        f"{s['total_estimated_days']} trip-days | "
        f"{s['total_distance_mi']} horiz mi | "
        f"{int(s['total_elevation_gain_ft'])} ft gain\n"
    )
    show_th = any(c.trailhead for c in clusters)
    th_head = f"  {'trailhead':>24}" if show_th else ""
    header = (f"{'#':>2}  {'pk':>2}  {'days':>4}  {'horiz_mi':>8}  {'eff_mi':>7}  "
              f"{'gain_ft':>8}  {'score':>6}{th_head}  route")
    print(header)
    print("-" * len(header))
    for c in clusters:
        route = " -> ".join(c.order)
        th = f"  {c.trailhead[:24]:>24}" if show_th else ""
        print(
            f"{c.cluster_id:>2}  {c.num_peaks:>2}  {c.estimated_days:>4}  "
            f"{c.total_distance_mi:>8.1f}  {c.total_effective_mi:>7.1f}  "
            f"{c.total_elevation_gain_ft:>8.0f}  {c.score:>6.2f}{th}  {route}"
        )
    print()


def main(argv=None) -> int:
    args = _parse_args(argv)

    config = ClusterConfig(
        eps_mi=args.eps_mi,
        min_samples=args.min_samples,
        miles_per_day=args.miles_per_day,
        max_days=args.max_days,
        method=args.method,
        exclude=_split_csv(args.exclude),
        force_together=[_split_csv(g) for g in args.force_together],
        by_trailhead=args.by_trailhead,
        trailhead_field=args.trailhead_field,
        trailhead_max_mi=args.trailhead_max_mi,
        include_approach=args.include_approach,
    )

    list_filter = None if args.list.lower() == "all" else args.list
    peaks = load_peaks(args.input, list_filter=list_filter)
    print(f"Loaded {len(peaks)} peaks from {args.input}"
          + (f" (list={args.list})" if list_filter else ""))

    trailheads = None
    if args.include_approach:
        trailheads = load_trailheads(args.trailheads)
        print(f"Loaded {len(trailheads)} trailheads from {args.trailheads} "
              f"(modeling approach)")

    groups = cluster_peaks(peaks, config)
    clusters = rank_clusters(build_itineraries(groups, config, trailheads))

    # Manual merges (applied to the first-pass cluster IDs).
    for spec in args.merge:
        ids = [int(x) for x in _split_csv(spec)]
        groups = manual.merge_clusters(clusters, ids)
        clusters = rank_clusters(build_itineraries(groups, config, trailheads))
        print(f"Merged clusters {ids} -> re-planned into {len(clusters)} trips")

    # Manual splits (applied to current cluster IDs, after merges).
    for spec in args.split:
        cid_str, _, k_str = spec.partition(":")
        cid, k = int(cid_str), int(k_str or 2)
        groups = manual.split_cluster(clusters, cid, k)
        clusters = rank_clusters(build_itineraries(groups, config, trailheads))
        print(f"Split cluster {cid} into {k} -> re-planned into {len(clusters)} trips")

    _print_summary(clusters)

    if args.output:
        save_json(clusters, args.output, config)
        print(f"Wrote itineraries to {args.output}")

    if args.viz:
        from sierra_peaks.visualize import plot_clusters
        plot_clusters(clusters, output_path=args.viz)
        print(f"Wrote visualization to {args.viz}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
