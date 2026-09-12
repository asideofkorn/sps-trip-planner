#!/usr/bin/env python3
"""Submit, list, and resolve data reports -- the write side of the
scavenger-hunt loop (see wayproof.reports and README's "The Scavenger Hunt").

Deliberately separate from plan.py: planning resolves/reads trip logistics
for named objectives on a date; reporting submits a claim about the dataset
itself. A report isn't tied to any trip date, and its target doesn't need to
already exist (e.g. reporting a peak that's missing entirely) -- coupling
the two forced every report through plan.py's objective-resolution flow and
a required --date that had nothing to do with the claim being made.

Examples
--------
Submit a report about something already in the dataset::

    python report.py submit data/water_sources.csv "Boyd Camp" \\
        "Confirmed running, saw it flowing" --confidence firsthand

Report a peak missing from the dataset entirely -- target_key is the name
you'd expect to find, target_file is where it would eventually go::

    python report.py submit data/peaks.csv "Mount Carillon" \\
        "Believed to be a real SPS peak near Mount Russell, not in the dataset" \\
        --confidence secondhand

List reports awaiting review::

    python report.py list

Resolve one after review (this only updates the report's own status --
transcribing an accepted claim into the actual domain CSV, citing the
report ID, is still a separate, deliberate step)::

    python report.py resolve R0001 accepted --notes "Added to data/peaks.csv, see PR #20"
"""

from __future__ import annotations

import argparse
import sys

from wayproof.reports import (
    format_pending_reports,
    pending_reports,
    resolve_report,
    submit_report,
)

_VALID_CONFIDENCE = ["firsthand", "official_source", "told_by_staff", "secondhand"]
_VALID_STATUS = ["pending", "accepted", "rejected", "needs-more-evidence"]


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--pending-reports-file", default="data/pending_reports.csv",
                    help="Report intake queue (default data/pending_reports.csv)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("submit", help="Submit a new report")
    s.add_argument("target_file", help="Dataset this claim is about, e.g. "
                                        "data/water_sources.csv, data/approaches.csv, "
                                        "data/campgrounds.csv, data/park_access.csv -- "
                                        "use data/peaks.csv to propose a peak that's "
                                        "missing from the dataset entirely")
    s.add_argument("target_key", help="The specific row/item this is about, e.g. a "
                                       "peak, water source, or campground name")
    s.add_argument("claim", help="What you're reporting")
    s.add_argument("--evidence", default="",
                    help="A link, photo description, who told you, a GPS track, etc.")
    s.add_argument("--confidence", default="firsthand", choices=_VALID_CONFIDENCE,
                    help="How solid the claim is (default firsthand)")
    s.add_argument("--channel", default="cli",
                    help="Where this came from, e.g. cli, github_issue (default cli)")

    sub.add_parser("list", help="List reports awaiting review")

    r = sub.add_parser("resolve", help="Mark a report resolved after review")
    r.add_argument("report_id")
    r.add_argument("status", choices=_VALID_STATUS)
    r.add_argument("--notes", default="",
                    help="Resolution notes, e.g. what CSV row or PR this became")

    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.command == "submit":
        report = submit_report(
            target_file=args.target_file, target_key=args.target_key, claim=args.claim,
            evidence=args.evidence, confidence=args.confidence, channel=args.channel,
            path=args.pending_reports_file,
        )
        print(f"Submitted report {report.report_id} to {args.pending_reports_file} "
              "(pending maintainer review).")
        return 0

    if args.command == "list":
        print(format_pending_reports(pending_reports(args.pending_reports_file)))
        return 0

    if args.command == "resolve":
        report = resolve_report(args.report_id, args.status, args.notes,
                                 path=args.pending_reports_file)
        print(f"{report.report_id} marked {report.status}.")
        return 0

    return 1  # pragma: no cover -- argparse's `required=True` prevents this


if __name__ == "__main__":
    sys.exit(main())
