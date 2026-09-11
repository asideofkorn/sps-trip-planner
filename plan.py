#!/usr/bin/env python3
"""Resolve trip logistics for specific, named objectives.

Unlike ``cli.py``'s experimental geographic clustering, this does not
discover or group objectives -- it assumes you already know what you want to
do and answers: what access applies, what permit governs it, when do you
need to act, and what evidence backs the answer?

Examples
--------
Access and permit logistics for a single objective::

    python plan.py "Mount Whitney" --date 2027-07-15

A mixed trip from a shared trailhead, including a peak-specific approach
override::

    python plan.py "Mount Whitney" "Mount Russell" --date 2027-07-01

Write the resolved plan as structured JSON::

    python plan.py "Mount Williamson" "Mount Tyndall" --date 2027-07-15 \\
        --output plan.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys

from sierra_peaks.access import load_approaches
from sierra_peaks.data_loader import load_peaks, load_trailheads
from sierra_peaks.permits import load_permits
from sierra_peaks.plan import resolve_plan, format_plan_summary


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=("Resolve access, permit, and evidence logistics for specific, "
                     "named objectives on a given trip date."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("objectives", nargs="+", help="One or more objective (peak) names")
    p.add_argument("--date", required=True, help="Planned trip date (YYYY-MM-DD)")
    p.add_argument("--peaks-file", default="data/peaks.csv",
                   help="Core peak dataset: name, coordinates, elevation -- "
                        "collection-agnostic (default data/peaks.csv)")
    p.add_argument("--collections-file", default="data/collections/sps.csv",
                   help="Collection metadata (list, section, official mileage, etc.) "
                        "joined onto --peaks-file by name (default data/collections/sps.csv). "
                        "Pass '' to resolve objectives from core geography alone, "
                        "with no collection metadata.")
    p.add_argument("--list", default="all",
                   help="If the collection data has a 'list' column, keep only this "
                        "list (default 'all', so both SPS and non-SPS-tracked "
                        "objectives resolve; pass 'SPS' to restrict to the 247-peak list)")
    p.add_argument("--trailheads-file", default="data/trailheads.csv",
                   help="Trailhead dataset (default data/trailheads.csv)")
    p.add_argument("--permits-file", default="data/permits.csv",
                   help="Permit rules dataset (default data/permits.csv)")
    p.add_argument("--release-policies-file", default="data/release_policies.csv",
                   help="Structured permit release-phase dataset "
                        "(default data/release_policies.csv)")
    p.add_argument("--approaches-file", default="data/approaches.csv",
                   help="Peak-specific approach/permit relationships "
                        "(default data/approaches.csv)")
    p.add_argument("--output", "-o", help="Write the resolved plan to this JSON file")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    trip_date = datetime.date.fromisoformat(args.date)

    list_filter = None if args.list.lower() == "all" else args.list
    peaks = load_peaks(args.peaks_file, list_filter=list_filter,
                        collections_path=args.collections_file or None)
    trailheads = load_trailheads(args.trailheads_file)
    permits = load_permits(args.permits_file, args.release_policies_file)
    approaches = load_approaches(args.approaches_file)

    result = resolve_plan(args.objectives, trip_date, peaks, trailheads, permits,
                           approaches=approaches)

    print(format_plan_summary(result))

    if args.output:
        with open(args.output, "w") as fh:
            json.dump(result.to_dict(), fh, indent=2)
        print(f"\nWrote plan to {args.output}")

    return 0 if result.objectives else 1


if __name__ == "__main__":
    sys.exit(main())
