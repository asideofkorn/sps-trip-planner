#!/usr/bin/env python3
"""Backfill elevation_ft in data/passes.csv by sampling a DEM at each point.

GNIS does not carry reliable elevation for passes, so once coordinates are set
(seed values, or authoritative ones from ``scripts/merge_passes.py``), sample a
digital elevation model at each lat/lon to get a consistent elevation.

Two point-query DEM services are supported (no key required):
  * usgs  - USGS 3DEP Elevation Point Query Service (epqs.nationalmap.gov),
            returns feet directly. US-only, highest resolution. (default)
  * opentopodata - api.opentopodata.org ``ned10m`` dataset, returns metres.

By default only rows whose elevation is blank are filled. Use ``--all`` to
re-sample every row, or ``--only-seed`` to refresh just the hand-entered seed
elevations once coordinates have been upgraded to GNIS.

Network is required. If the host has no outbound access the script reports the
failure and leaves data/passes.csv untouched.

Usage:
    python scripts/fill_pass_elevation.py
    python scripts/fill_pass_elevation.py --provider opentopodata --all
"""

from __future__ import annotations

import argparse
import time
import urllib.request
import urllib.error
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PASSES = ROOT / "data" / "passes.csv"

M_TO_FT = 3.280839895


def query_usgs(lat: float, lon: float) -> float | None:
    url = (f"https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}"
           f"&units=Feet&wkid=4326&includeDate=false")
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.load(resp)
    val = data.get("value")
    if val in (None, "", "-1000000"):
        return None
    return float(val)


def query_opentopodata(lat: float, lon: float) -> float | None:
    url = f"https://api.opentopodata.org/v1/ned10m?locations={lat},{lon}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.load(resp)
    results = data.get("results") or []
    if not results or results[0].get("elevation") is None:
        return None
    return float(results[0]["elevation"]) * M_TO_FT


PROVIDERS = {"usgs": query_usgs, "opentopodata": query_opentopodata}


def sample(fn, lat: float, lon: float, retries: int = 4) -> float | None:
    """Query with exponential backoff on transient network errors."""
    delay = 2.0
    for attempt in range(retries):
        try:
            return fn(lat, lon)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == retries - 1:
                raise
            print(f"    network error ({exc}); retrying in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--passes", default=str(PASSES))
    ap.add_argument("--out", default=str(PASSES))
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default="usgs")
    ap.add_argument("--all", action="store_true", help="re-sample every row")
    ap.add_argument("--only-seed", action="store_true",
                    help="only re-sample rows still marked coord_source=seed")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between requests (be polite to the API)")
    args = ap.parse_args(argv)

    passes = pd.read_csv(args.passes)
    passes["elevation_ft"] = passes["elevation_ft"].astype("float64")
    fn = PROVIDERS[args.provider]

    filled = failed = skipped = 0
    try:
        for i, row in passes.iterrows():
            name = row["name"]
            needs = pd.isna(row["elevation_ft"])
            if args.all:
                needs = True
            elif args.only_seed:
                needs = str(row.get("coord_source", "")).lower() == "seed"
            if not needs:
                skipped += 1
                continue
            lat, lon = float(row["latitude"]), float(row["longitude"])
            elev = sample(fn, lat, lon)
            if elev is None:
                print(f"  {name}: no DEM value at ({lat}, {lon})")
                failed += 1
            else:
                passes.at[i, "elevation_ft"] = round(elev)
                print(f"  {name}: {round(elev)} ft")
                filled += 1
            time.sleep(args.sleep)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(f"\nNetwork unavailable ({exc}). data/passes.csv left unchanged.")
        print("Run this script from a host with outbound internet access.")
        return 1

    passes["elevation_ft"] = passes["elevation_ft"].astype("Int64")
    passes.to_csv(args.out, index=False)
    print(f"\nProvider {args.provider}: filled {filled}, "
          f"failed {failed}, skipped {skipped} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
