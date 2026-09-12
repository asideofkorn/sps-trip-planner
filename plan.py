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

Report back on something you confirmed or corrected while there (appends to
the pending-review queue, ``data/pending_reports.csv`` -- it does not modify
any dataset directly; a maintainer reviews and transcribes accepted reports)::

    python plan.py "Rose Peak" --date 2027-06-01 \\
        --report "Sunol Backpack Camp has 2 vault-toilet restrooms, no showers"

The objective doesn't need to already be in the dataset -- a name that
doesn't resolve is exactly how someone reports a peak that's missing
entirely (``--target-file`` defaults to ``data/peaks.csv`` in that case)::

    python plan.py "Mount Carillon" --date 2027-07-01 \\
        --report "Believed to be a real SPS peak near Mount Russell, not yet in data/peaks.csv" \\
        --confidence secondhand
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys

from wayproof.access import load_approaches
from wayproof.camping import load_campgrounds, load_campsites
from wayproof.data_loader import load_peaks, load_trailheads
from wayproof.park_access import load_park_access
from wayproof.permits import load_permits
from wayproof.plan import resolve_plan, format_plan_summary
from wayproof.reports import submit_report
from wayproof.water import load_water_sources, load_water_source_log


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
    p.add_argument("--water-sources-file", default="data/water_sources.csv",
                   help="Named backcountry water sources (default data/water_sources.csv)")
    p.add_argument("--water-source-log-file", default="data/water_source_log.csv",
                   help="Append-only water-availability check ledger "
                        "(default data/water_source_log.csv)")
    p.add_argument("--campgrounds-file", default="data/campgrounds.csv",
                   help="Backpack campgrounds (default data/campgrounds.csv)")
    p.add_argument("--campsites-file", default="data/campsites.csv",
                   help="Individually-bookable campsites (default data/campsites.csv)")
    p.add_argument("--park-access-file", default="data/park_access.csv",
                   help="Park-level entrance fee/hours dataset (default data/park_access.csv)")
    p.add_argument("--output", "-o", help="Write the resolved plan to this JSON file")
    p.add_argument("--report", metavar="TEXT",
                   help="Submit a claim about these objectives to the pending-review "
                        "queue (data/pending_reports.csv) instead of/alongside printing "
                        "the plan -- e.g. something you confirmed or found wrong while "
                        "there. Reviewed and transcribed manually; does not change any "
                        "dataset by itself.")
    p.add_argument("--evidence", default="",
                   help="Optional supporting detail for --report (a link, a photo "
                        "description, who told you, etc.)")
    p.add_argument("--confidence", default="firsthand",
                   choices=["firsthand", "official_source", "told_by_staff", "secondhand"],
                   help="How solid --report's claim is (default firsthand)")
    p.add_argument("--target-file", default="",
                   help="Which dataset --report's claim is about (e.g. "
                        "data/water_sources.csv, data/approaches.csv). Defaults to "
                        "data/peaks.csv if the objective name didn't resolve to a known "
                        "peak (i.e. you're reporting a peak that's missing entirely), "
                        "otherwise 'unspecified'.")
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
    water_sources = load_water_sources(args.water_sources_file)
    water_source_log = load_water_source_log(args.water_source_log_file)
    campgrounds = load_campgrounds(args.campgrounds_file)
    campsites = load_campsites(args.campsites_file)
    park_access = list(load_park_access(args.park_access_file).values())

    result = resolve_plan(args.objectives, trip_date, peaks, trailheads, permits,
                           approaches=approaches, water_sources=water_sources,
                           water_source_log=water_source_log, campgrounds=campgrounds,
                           campsites=campsites, park_access=park_access)

    print(format_plan_summary(result))

    if args.report:
        target_key = ", ".join(p.name for p in result.objectives) or ", ".join(args.objectives)
        target_file = args.target_file or ("data/peaks.csv" if result.not_found else "unspecified")
        report = submit_report(
            target_file=target_file, target_key=target_key, claim=args.report,
            evidence=args.evidence, confidence=args.confidence, channel="cli",
        )
        print(f"\nSubmitted report {report.report_id} to data/pending_reports.csv "
              "(pending maintainer review).")

    if args.output:
        with open(args.output, "w") as fh:
            json.dump(result.to_dict(), fh, indent=2)
        print(f"\nWrote plan to {args.output}")

    return 0 if result.objectives else 1


if __name__ == "__main__":
    sys.exit(main())
