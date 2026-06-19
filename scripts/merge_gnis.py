#!/usr/bin/env python3
"""Fill latitude/longitude in data/sps_peaks.csv from USGS GNIS data.

GNIS (the federal gazetteer the SPS list is itself built from) provides the
authoritative decimal coordinates plus the USGS quad name, so peaks are matched
on **name + quad**, which disambiguates same-named summits precisely.

Matching order for each peak:
  1. MANUAL   - explicit coordinates for peaks GNIS does not name (unofficial
                names like "Taylor Dome", "Clyde Minaret").
  2. ALIAS    - SPS name -> (GNIS feature_name, GNIS quad) for spelling/wording
                variants ("Mount MacClure" -> "Mount Maclure", etc.).
  3. AUTO     - exact (normalized name, normalized quad); then unique name.

Reads the trimmed Sierra subset committed at data/source/gnis_sierra_summits.txt
(regenerate from the full state files with --gnis <path> [...]).

Usage:
    python scripts/merge_gnis.py            # uses committed Sierra subset
    python scripts/merge_gnis.py --report   # show unmatched detail
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GNIS = ROOT / "data" / "source" / "gnis_sierra_summits.txt"
PEAKS = ROOT / "data" / "sps_peaks.csv"

# SPS list name  ->  (GNIS feature_name, GNIS quad/map_name)
ALIAS: dict[str, tuple[str, str]] = {
    "Mount Carillion": ("Mount Carillon", "Mount Whitney"),
    "Mount MacClure": ("Mount Maclure", "Mount Lyell"),
    "Mount LeConte": ("Mount Le Conte", "Mount Whitney"),
    "Mount Julius Ceasar": ("Mount Julius Caesar", "Mount Hilgard"),
    "Mount Lippincott": ("Lippincott Mountain", "Triple Divide Peak"),
    "Mount Muah": ("Muah Mountain", "Cirque Peak"),
    "Devils Crag #1": ("Devils Crags", "North Palisade"),
    "Round Top": ("Round Top", "Caples Lake"),
    "Sawtooth Peak (S)": ("Sawtooth Peak", "Ninemile Canyon"),
    "Castle Peak": ("Castle Peak", "Norden"),
    "Whaleback": ("Whaleback", "Sphinx Lakes"),
    "Glacier Ridge": ("Glacier Ridge", "Triple Divide Peak"),
    "Florence Peak": ("Mount Florence", "Mineral King"),
    "Forester Peak": ("Foerster Peak", "Mount Lyell"),  # SPS misspells "Foerster"
}

# Peaks GNIS does not name (unofficial summits). Coordinates sourced from
# peakbagger.com and rounded to 5 dp. source noted per-peak.
MANUAL: dict[str, tuple[float, float]] = {
    # name: (lat, lon)  -- sourced from peakbagger.com (WGS84 decimal degrees)
    "Spanish Needle": (35.77155, -118.0012),
    "Rockhouse Peak": (35.90099, -118.22839),
    "Taylor Dome": (35.85635, -118.30342),
    "North Maggie Mountain": (36.276772, -118.637698),
    "Cartago Peak": (36.32457, -118.10213),
    "Clyde Minaret": (37.66028, -119.1739),
}


def norm(s: str) -> str:
    s = str(s).strip().lower()
    s = s.replace("mt.", "mount").replace("mtn.", "mountain").replace("mtn", "mountain")
    s = re.sub(r"\bmt\b", "mount", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def load_gnis(path: Path) -> tuple[dict, dict, dict]:
    by_nq: dict[tuple[str, str], list] = defaultdict(list)
    by_n: dict[str, list] = defaultdict(list)
    exact: dict[tuple[str, str], tuple[float, float]] = {}
    with path.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter="|")
        for row in reader:
            try:
                lat = float(row["prim_lat_dec"]); lon = float(row["prim_long_dec"])
            except (KeyError, ValueError):
                continue
            name, quad = row["feature_name"], row["map_name"]
            rec = (name, quad, lat, lon)
            by_nq[(norm(name), norm(quad))].append(rec)
            by_n[norm(name)].append(rec)
            exact[(name, quad)] = (lat, lon)
    return by_nq, by_n, exact


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gnis", nargs="*", default=[str(DEFAULT_GNIS)])
    ap.add_argument("--peaks", default=str(PEAKS))
    ap.add_argument("--out", default=str(PEAKS))
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    by_nq, by_n, exact = {}, {}, {}
    for g in args.gnis:
        a, b, c = load_gnis(Path(g))
        for k, v in a.items(): by_nq.setdefault(k, []).extend(v)
        for k, v in b.items(): by_n.setdefault(k, []).extend(v)
        exact.update(c)

    peaks = pd.read_csv(args.peaks)
    # Ensure assignable dtypes (empty columns load as all-NaN float64).
    peaks["latitude"] = peaks["latitude"].astype("float64")
    peaks["longitude"] = peaks["longitude"].astype("float64")
    peaks["coord_source"] = peaks["coord_source"].astype("object")
    matched = {"manual": 0, "alias": 0, "name_quad": 0, "name_unique": 0}
    unmatched_sps, unmatched_non = [], []

    for i, p in peaks.iterrows():
        name, quad = p["name"], str(p.get("quad", ""))
        coord = src = None

        if name in MANUAL:
            coord, src = MANUAL[name], "peakbagger"; matched["manual"] += 1
        elif name in ALIAS:
            coord = exact.get(ALIAS[name]); src = "GNIS"
            if coord:
                matched["alias"] += 1
        if coord is None:
            cands = by_nq.get((norm(name), norm(quad)))
            if cands:
                coord = (cands[0][2], cands[0][3]); src = "GNIS"; matched["name_quad"] += 1
            else:
                uniq = by_n.get(norm(name))
                if uniq and len({(r[2], r[3]) for r in uniq}) == 1:
                    coord = (uniq[0][2], uniq[0][3]); src = "GNIS"; matched["name_unique"] += 1

        if coord is None:
            (unmatched_sps if p["list"] == "SPS" else unmatched_non).append((name, quad))
            continue
        peaks.at[i, "latitude"] = round(coord[0], 6)
        peaks.at[i, "longitude"] = round(coord[1], 6)
        peaks.at[i, "coord_source"] = src

    peaks.to_csv(args.out, index=False)

    sps = peaks[peaks.list == "SPS"]
    have = sps["latitude"].notna().sum()
    print(f"GNIS sources: {args.gnis}")
    print(f"Match breakdown: {matched}")
    print(f"SPS peaks with coordinates: {have}/{len(sps)}")
    print(f"non-SPS with coordinates:   {peaks[peaks.list=='non-SPS']['latitude'].notna().sum()}/"
          f"{(peaks.list=='non-SPS').sum()}")
    if unmatched_sps:
        print(f"\nUNMATCHED SPS ({len(unmatched_sps)}) - need MANUAL coords:")
        for n, q in unmatched_sps:
            print(f"  - {n!r}  (quad {q})")
    if args.report and unmatched_non:
        print(f"\nUNMATCHED non-SPS: {len(unmatched_non)} (out of scope)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
