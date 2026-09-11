#!/usr/bin/env python3
"""Command-line interface for Sierra trip logistics and candidate grouping.

Examples
--------
Basic run on the sample data::

    python cli.py --input data/sps_sample.csv --output out.json

Tune the candidate-group budget and DBSCAN radius, force a group together, exclude a peak::

    python cli.py --input data/sps_sample.csv \\
        --eps-mi 8 --miles-per-day 12 --max-days 2 \\
        --force-together "North Palisade,Polemonium Peak,Mount Sill,Thunderbolt Peak" \\
        --exclude "Mount Muir" \\
        --viz clusters.png

Manually merge groups #4 and #5 from the first pass, then recompute metrics::

    python cli.py --input data/sps_sample.csv --merge 4,5
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.clustering import ClusterConfig, cluster_peaks
from wayproof.pipeline import build_itineraries, rank_clusters
from wayproof import manual
from wayproof.export import save_json, clusters_to_payload


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=("Source-backed Sierra trip logistics, with experimental "
                     "geographic candidate grouping for SPS peaks."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", "-i", help="SPS peak CSV or JSON file "
                   "(not required with --permit-sources, which doesn't touch peak data)")
    p.add_argument("--output", "-o", help="Write ranked candidate groupings to this JSON file")
    p.add_argument("--eps-mi", type=float, default=6.0,
                   help="Spatial grouping radius in horizontal miles (default 6)")
    p.add_argument("--min-samples", type=int, default=1,
                   help="DBSCAN min_samples (default 1)")
    p.add_argument("--miles-per-day", type=float, default=15.0,
                   help="Effective hiking miles per day (default 15)")
    p.add_argument("--max-days", type=int, default=3,
                   help="Maximum estimated days per candidate group (default 3)")
    p.add_argument("--method", choices=["dbscan", "agglomerative"], default="dbscan",
                   help="Spatial grouping method (default dbscan)")
    p.add_argument("--exclude", default="",
                   help="Comma-separated peak names to exclude")
    p.add_argument("--force-together", action="append", default=[],
                   help="Comma-separated peaks to keep in one candidate group "
                        "(repeatable for multiple groups)")
    p.add_argument("--by-trailhead", action="store_true",
                   help="Keep peaks that share a trailhead in the same candidate group "
                        "(then eps still merges nearby trailheads)")
    p.add_argument("--trailhead-field", default="trailhead",
                   help="Metadata column to group on with --by-trailhead "
                        "(e.g. 'nearest_trailhead'; default 'trailhead')")
    p.add_argument("--trailhead-max-mi", type=float, default=None,
                   help="With --by-trailhead, only link same-trailhead peaks "
                        "within this straight-line distance (splits long trails "
                        "like the PCT)")
    p.add_argument("--merge", action="append", default=[],
                   help="Comma-separated group IDs to merge after the first pass "
                        "(repeatable)")
    p.add_argument("--split", action="append", default=[],
                   help="Split a group: ID:K (e.g. 2:3). Applied after merges. "
                        "(repeatable)")
    p.add_argument("--include-approach", action="store_true",
                   help="Model the trailhead approach (walk in to the first peak "
                        "and out from the last), folding it into distance, effort, "
                        "days and score")
    p.add_argument("--approach-report", action="store_true",
                   help="Print an approach-amortization report (trailheads serving "
                        "multiple candidate groups, ranked by recoverable approach effort). "
                        "Implies --include-approach.")
    p.add_argument("--trailheads", default="data/trailheads.csv",
                   help="Trailhead CSV used with --include-approach "
                        "(default data/trailheads.csv)")
    p.add_argument("--permits", action="store_true",
                   help="Print a permit report per candidate group (agency, permit type, "
                        "quota season, and when to apply for --trip-date). "
                        "Implies --include-approach.")
    p.add_argument("--trip-date", default=None,
                   help="Planned trip start date (YYYY-MM-DD) for --permits "
                        "(default: today)")
    p.add_argument("--permits-file", default="data/permits.csv",
                   help="Permit rules dataset for --permits (default data/permits.csv)")
    p.add_argument("--release-policies-file", default="data/release_policies.csv",
                   help="Structured permit release-phase dataset for --permits "
                        "(default data/release_policies.csv)")
    p.add_argument("--approaches-file", default="data/approaches.csv",
                   help="Peak-specific approach relationships for --permits, for "
                        "peaks whose actual permit differs from (or is uncertain "
                        "against) their trailhead's default (default "
                        "data/approaches.csv)")
    p.add_argument("--permit-sources", nargs="?", const="__all__", default=None,
                   metavar="PERMIT_GROUP",
                   help="Print the permit source-verification log (audit trail of "
                        "every source checked per permit_group, and any unresolved "
                        "conflicts between sources) and exit. Optionally pass a "
                        "permit_group name to filter to just that group.")
    p.add_argument("--permit-source-log-file", default="data/permit_source_log.csv",
                   help="Source log dataset for --permit-sources "
                        "(default data/permit_source_log.csv)")
    p.add_argument("--list", default="SPS",
                   help="If the data has a 'list' column, keep only this list "
                        "(default SPS; use 'all' to keep everything). Requires "
                        "--collections-file to actually have a 'list' column "
                        "when --input is the core dataset (data/peaks.csv).")
    p.add_argument("--collections-file", default="data/collections/sps.csv",
                   help="Collection metadata (list, section, official mileage, etc.) "
                        "joined onto --input by name (default data/collections/sps.csv). "
                        "Pass '' to load --input as a standalone, collection-agnostic "
                        "peak dataset with no collection metadata.")
    p.add_argument("--use-passes", action="store_true",
                   help="Evaluate cross-crest distance through mountain passes "
                        "instead of straight lines (uses data/passes.csv)")
    p.add_argument("--passes-file", default="data/passes.csv",
                   help="Passes dataset for --use-passes (default data/passes.csv)")
    p.add_argument("--pass-tier", type=int, default=1, choices=[1, 2],
                   help="Which passes may be used as crossings: 1 = named passes "
                        "only (default), 2 = also minor gaps/saddles")
    p.add_argument("--viz", help="Write a matplotlib PNG of candidate groups/sequences here")
    return p.parse_args(argv)


def _split_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _print_summary(clusters) -> None:
    payload = clusters_to_payload(clusters)
    s = payload["summary"]
    print(
        f"\n{len(clusters)} candidate groups | {s['total_peaks']} peaks | "
        f"{s['total_estimated_days']} estimated group-days | "
        f"{s['total_distance_mi']} horiz mi | "
        f"{int(s['total_elevation_gain_ft'])} ft gain\n"
    )
    show_th = any(c.trailhead for c in clusters)
    th_head = f"  {'trailhead':>24}" if show_th else ""
    header = (f"{'#':>2}  {'pk':>2}  {'days':>4}  {'horiz_mi':>8}  {'eff_mi':>7}  "
              f"{'gain_ft':>8}  {'score':>6}{th_head}  candidate sequence")
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

    if args.permit_sources is not None:
        from wayproof.permits import load_source_log, format_source_log
        group = None if args.permit_sources == "__all__" else args.permit_sources
        log = load_source_log(args.permit_source_log_file)
        print(format_source_log(log, permit_group=group))
        return 0

    if not args.input:
        print("error: --input is required (unless using --permit-sources)", file=sys.stderr)
        return 2

    include_approach = args.include_approach or args.approach_report or args.permits

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
        include_approach=include_approach,
    )

    if args.use_passes:
        from wayproof.passes import build_router
        config.router = build_router(args.passes_file, candidate_tier=args.pass_tier)
        n_wp = len(config.router.waypoints)
        print(f"Pass routing ON: {n_wp} crossing passes (tier<={args.pass_tier}) "
              f"from {args.passes_file}"
              + ("" if config.router.crest.usable else "  [crest model UNUSABLE — "
                 "need >=2 tier-1 passes; falling back to straight-line]"))

    list_filter = None if args.list.lower() == "all" else args.list
    peaks = load_peaks(args.input, list_filter=list_filter,
                        collections_path=args.collections_file or None)
    print(f"Loaded {len(peaks)} peaks from {args.input}"
          + (f" + {args.collections_file}" if args.collections_file else "")
          + (f" (list={args.list})" if list_filter else ""))

    trailheads = None
    if include_approach:
        trailheads = load_trailheads(args.trailheads)
        print(f"Loaded {len(trailheads)} trailheads from {args.trailheads} "
              f"(modeling approach)")

    groups = cluster_peaks(peaks, config, trailheads)
    clusters = rank_clusters(build_itineraries(groups, config, trailheads))

    # Manual merges (applied to the first-pass group IDs).
    for spec in args.merge:
        ids = [int(x) for x in _split_csv(spec)]
        groups = manual.merge_clusters(clusters, ids)
        clusters = rank_clusters(build_itineraries(groups, config, trailheads))
        print(f"Merged groups {ids} -> recomputed {len(clusters)} candidate groups")

    # Manual splits (applied to current group IDs, after merges).
    for spec in args.split:
        cid_str, _, k_str = spec.partition(":")
        cid, k = int(cid_str), int(k_str or 2)
        groups = manual.split_cluster(clusters, cid, k)
        clusters = rank_clusters(build_itineraries(groups, config, trailheads))
        print(f"Split group {cid} into {k} -> recomputed {len(clusters)} candidate groups")

    _print_summary(clusters)

    if args.approach_report:
        from wayproof.diagnostics import (
            approach_amortization, format_approach_report,
        )
        rows = approach_amortization(clusters, config)
        print("Approach-amortization report")
        print("=" * 28)
        print(format_approach_report(rows))
        print()

    if args.permits:
        import datetime
        from wayproof.access import load_approaches
        from wayproof.permits import (
            load_permits, clusters_permit_info, format_permit_report,
        )
        trip_date = (datetime.date.fromisoformat(args.trip_date) if args.trip_date
                     else datetime.date.today())
        permit_rules = load_permits(args.permits_file, args.release_policies_file)
        approaches = load_approaches(args.approaches_file)
        rows = clusters_permit_info(clusters, trailheads, permit_rules, trip_date,
                                     approaches=approaches)
        print(f"Permit report (trip date {trip_date.isoformat()})")
        print("=" * 28)
        print(format_permit_report(rows))
        print()

    if args.output:
        save_json(clusters, args.output, config)
        print(f"Wrote candidate groupings to {args.output}")

    if args.viz:
        from wayproof.visualize import plot_clusters
        plot_clusters(clusters, output_path=args.viz)
        print(f"Wrote visualization to {args.viz}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
