#!/usr/bin/env python3
"""Authoritatively fill pass coordinates in data/passes.csv from USGS GNIS.

Mountain passes, saddles, notches, and cols are all carried in GNIS under the
**feature class ``Gap``** (the same gazetteer ``merge_gnis.py`` uses for
``Summit`` features). This script reads a GNIS pipe-delimited extract, keeps the
``Gap`` rows inside the Sierra bounding box, and matches them into the curated
seed at ``data/passes.csv`` so the authoritative coordinates + USGS quad replace
the hand-entered ``coord_source=seed`` values.

GNIS elevation is unreliable (it was only a DEM sample at the point and has been
dropped from the primary national file), so this script does **not** touch the
``elevation_ft`` column -- run ``scripts/fill_pass_elevation.py`` to backfill
elevation from a DEM after coordinates are set.

Matching order for each seed pass (mirrors merge_gnis.py):
  1. ALIAS  - seed name -> (GNIS feature_name, GNIS quad) for wording variants.
  2. AUTO   - exact (normalized name, normalized quad); then unique name in box.

The committed ``data/source/gnis_sierra_summits.txt`` contains only ``Summit``
rows, so regenerate a Gap-bearing extract first (see data/source/README.md):

    # from the full GNIS California names file, keep Gap features
    python scripts/merge_passes.py --gnis data/source/gnis_sierra_gaps.txt

Usage:
    python scripts/merge_passes.py --gnis <file> [<file> ...]
    python scripts/merge_passes.py --gnis <file> --add-all   # also append
                                   #   every Sierra Gap not already listed
    python scripts/merge_passes.py --gnis <file> --report    # show unmatched
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sierra_peaks.passes import classify
DEFAULT_GNIS = ROOT / "data" / "source" / "gnis_sierra_gaps.txt"
PASSES = ROOT / "data" / "passes.csv"

# Generous Sierra Nevada bounding box (matches the summits extract extent).
# (lat_min, lat_max, lon_min, lon_max)
SIERRA_BBOX = (35.0, 41.5, -121.0, -117.0)

# Seed pass name -> (GNIS feature_name, GNIS quad/map_name) for wording variants.
ALIAS: dict[str, tuple[str, str]] = {
    "Echo Summit": ("Echo Summit", "Echo Lake"),
}


def norm(s: str) -> str:
    s = str(s).strip().lower()
    s = s.replace("mt.", "mount").replace("mtn.", "mountain").replace("mtn", "mountain")
    s = re.sub(r"\bmt\b", "mount", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def in_box(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = SIERRA_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def load_gaps(path: Path) -> tuple[dict, dict, dict, list]:
    """Index Gap features by (name, quad), by name, and by exact (name, quad)."""
    by_nq: dict[tuple[str, str], list] = defaultdict(list)
    by_n: dict[str, list] = defaultdict(list)
    exact: dict[tuple[str, str], tuple[float, float]] = {}
    all_gaps: list[tuple[str, str, float, float]] = []
    with path.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter="|")
        for row in reader:
            if (row.get("feature_class") or "").strip().lower() != "gap":
                continue
            try:
                lat = float(row["prim_lat_dec"]); lon = float(row["prim_long_dec"])
            except (KeyError, ValueError):
                continue
            if not in_box(lat, lon):
                continue
            name, quad = row["feature_name"], row.get("map_name", "")
            rec = (name, quad, lat, lon)
            by_nq[(norm(name), norm(quad))].append(rec)
            by_n[norm(name)].append(rec)
            exact[(name, quad)] = (lat, lon)
            all_gaps.append(rec)
    return by_nq, by_n, exact, all_gaps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gnis", nargs="*", default=[str(DEFAULT_GNIS)])
    ap.add_argument("--passes", default=str(PASSES))
    ap.add_argument("--out", default=str(PASSES))
    ap.add_argument("--add-all", action="store_true",
                    help="append every Sierra Gap not already in passes.csv")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    missing = [g for g in args.gnis if not Path(g).exists()]
    if missing:
        print("GNIS Gap extract not found:")
        for g in missing:
            print(f"  - {g}")
        print("\nRegenerate it from the full USGS GNIS California names file by "
              "keeping\nfeature_class == 'Gap' rows (see data/source/README.md).")
        return 1

    by_nq, by_n, exact, all_gaps = {}, {}, {}, []
    for g in args.gnis:
        a, b, c, d = load_gaps(Path(g))
        for k, v in a.items(): by_nq.setdefault(k, []).extend(v)
        for k, v in b.items(): by_n.setdefault(k, []).extend(v)
        exact.update(c)
        all_gaps.extend(d)

    passes = pd.read_csv(args.passes)
    passes["latitude"] = passes["latitude"].astype("float64")
    passes["longitude"] = passes["longitude"].astype("float64")
    passes["quad"] = passes["quad"].astype("object")
    passes["coord_source"] = passes["coord_source"].astype("object")

    matched = {"alias": 0, "name_quad": 0, "name_unique": 0}
    unmatched = []

    for i, p in passes.iterrows():
        name, quad = p["name"], str(p.get("quad", ""))
        rec = None

        if name in ALIAS:
            coord = exact.get(ALIAS[name])
            if coord:
                gname, gquad = ALIAS[name]
                rec = (gname, gquad, coord[0], coord[1]); matched["alias"] += 1
        if rec is None:
            cands = by_nq.get((norm(name), norm(quad)))
            if cands:
                rec = cands[0]; matched["name_quad"] += 1
            else:
                uniq = by_n.get(norm(name))
                if uniq and len({(r[2], r[3]) for r in uniq}) == 1:
                    rec = uniq[0]; matched["name_unique"] += 1

        if rec is None:
            unmatched.append((name, quad))
            continue
        passes.at[i, "latitude"] = round(rec[2], 6)
        passes.at[i, "longitude"] = round(rec[3], 6)
        passes.at[i, "quad"] = rec[1]
        passes.at[i, "coord_source"] = "GNIS"

    if args.add_all:
        have = {norm(n) for n in passes["name"]}
        added = 0
        new_rows = []
        for gname, gquad, lat, lon in all_gaps:
            if norm(gname) in have:
                continue
            have.add(norm(gname))
            tier, kind = classify(gname, "GNIS")
            new_rows.append({
                "name": gname, "latitude": round(lat, 6), "longitude": round(lon, 6),
                "elevation_ft": "", "quad": gquad, "coord_source": "GNIS",
                "tier": tier, "kind": kind, "notes": "",
            })
            added += 1
        if new_rows:
            passes = pd.concat([passes, pd.DataFrame(new_rows)], ignore_index=True)
        print(f"--add-all: appended {added} additional Sierra Gap features")

    passes.to_csv(args.out, index=False)

    have_gnis = (passes["coord_source"] == "GNIS").sum()
    print(f"GNIS sources: {args.gnis}")
    print(f"Sierra Gap features in box: {len(all_gaps)}")
    print(f"Match breakdown: {matched}")
    print(f"Passes with GNIS coordinates: {have_gnis}/{len(passes)} -> {args.out}")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) - kept seed coords (verify by hand):")
        for n, q in unmatched:
            print(f"  - {n!r}  (quad {q})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
