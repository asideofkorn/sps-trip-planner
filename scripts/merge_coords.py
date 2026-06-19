#!/usr/bin/env python3
"""Join coordinates into data/sps_peaks.csv from a peakbagger-style export.

Accepts a GPX, KML, CSV, or JSON file containing peak names + lat/lon and
matches them, by normalized name (with an elevation tie-breaker when names are
ambiguous), into the peaks dataset. Any peak that cannot be matched is reported
so it can be fixed by hand.

Usage:
    python scripts/merge_coords.py <coords_file> [--peaks data/sps_peaks.csv]
                                   [--out data/sps_peaks.csv] [--source peakbagger]

Supported coordinate inputs:
    GPX   <wpt lat=".." lon=".."><name>..</name><ele>..</ele></wpt>
    KML   <Placemark><name>..</name><Point><coordinates>lon,lat,ele</...>
    CSV   columns: name, lat/latitude, lon/longitude, (optional) elevation/ele
    JSON  list of {name, lat/latitude, lon/longitude, ...}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd


def norm(name: str) -> str:
    s = str(name).strip().lower()
    s = s.replace("mt.", "mount").replace("mt ", "mount ")
    s = re.sub(r"\(.*?\)", " ", s)          # drop "(S)", "(North)", etc.
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_gpx(path: Path) -> list[dict]:
    tree = ET.parse(path)
    out = []
    for el in tree.iter():
        if _strip_ns(el.tag) != "wpt":
            continue
        rec = {"lat": float(el.get("lat")), "lon": float(el.get("lon"))}
        for child in el:
            t = _strip_ns(child.tag)
            if t == "name":
                rec["name"] = (child.text or "").strip()
            elif t == "ele" and child.text:
                rec["elev"] = float(child.text)
        if "name" in rec:
            out.append(rec)
    return out


def parse_kml(path: Path) -> list[dict]:
    tree = ET.parse(path)
    out = []
    for pm in tree.iter():
        if _strip_ns(pm.tag) != "Placemark":
            continue
        name, coords = None, None
        for el in pm.iter():
            t = _strip_ns(el.tag)
            if t == "name":
                name = (el.text or "").strip()
            elif t == "coordinates" and el.text:
                coords = el.text.strip().split()[0]
        if name and coords:
            parts = coords.split(",")
            rec = {"name": name, "lon": float(parts[0]), "lat": float(parts[1])}
            if len(parts) > 2:
                rec["elev"] = float(parts[2])
            out.append(rec)
    return out


def parse_tabular(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        records = data["peaks"] if isinstance(data, dict) and "peaks" in data else data
        df = pd.DataFrame(records)
    else:
        df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    name_c = next((cols[k] for k in ("name", "peak", "peak_name") if k in cols), None)
    lat_c = next((cols[k] for k in ("lat", "latitude") if k in cols), None)
    lon_c = next((cols[k] for k in ("lon", "lng", "long", "longitude") if k in cols), None)
    elev_c = next((cols[k] for k in ("elevation", "elevation_ft", "ele", "elev") if k in cols), None)
    if not (name_c and lat_c and lon_c):
        raise ValueError(f"Could not find name/lat/lon columns in {list(df.columns)}")
    out = []
    for _, r in df.iterrows():
        rec = {"name": str(r[name_c]).strip(), "lat": float(r[lat_c]), "lon": float(r[lon_c])}
        if elev_c and pd.notna(r[elev_c]):
            rec["elev"] = float(r[elev_c])
        out.append(rec)
    return out


def load_coords(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".gpx":
        return parse_gpx(path)
    if suffix == ".kml":
        return parse_kml(path)
    if suffix in (".csv", ".json"):
        return parse_tabular(path)
    raise ValueError(f"Unsupported coordinate file type: {suffix}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("coords_file")
    ap.add_argument("--peaks", default="data/sps_peaks.csv")
    ap.add_argument("--out", default="data/sps_peaks.csv")
    ap.add_argument("--source", default="peakbagger")
    args = ap.parse_args(argv)

    peaks = pd.read_csv(args.peaks)
    coords = load_coords(Path(args.coords_file))

    # Index coordinate records by normalized name (keep list for ambiguity).
    by_name: dict[str, list[dict]] = {}
    for rec in coords:
        by_name.setdefault(norm(rec["name"]), []).append(rec)

    matched, unmatched = 0, []
    for i, row in peaks.iterrows():
        key = norm(row["name"])
        cands = by_name.get(key)
        if not cands:
            unmatched.append(row["name"])
            continue
        rec = cands[0]
        if len(cands) > 1 and pd.notna(row.get("elevation_ft")):
            # disambiguate by closest elevation
            rec = min(cands, key=lambda c: abs(c.get("elev", 1e9) - row["elevation_ft"]))
        peaks.at[i, "latitude"] = round(rec["lat"], 6)
        peaks.at[i, "longitude"] = round(rec["lon"], 6)
        peaks.at[i, "coord_source"] = args.source
        matched += 1

    peaks.to_csv(args.out, index=False)
    print(f"Loaded {len(coords)} coordinate records from {args.coords_file}")
    print(f"Matched {matched}/{len(peaks)} peaks -> {args.out}")
    if unmatched:
        print(f"\n{len(unmatched)} peaks UNMATCHED (need manual coords or name fix):")
        for n in unmatched:
            print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
