#!/usr/bin/env python3
"""Build data/source/gnis_sierra_gaps.txt from a USGS GNIS names download.

This is the network-dependent companion to ``merge_passes.py``. It takes a raw
USGS GNIS names file (national or California), keeps the ``Gap`` features inside
the Sierra bounding box, and writes them in the trimmed pipe-delimited schema
the rest of the pipeline expects:

    feature_name|feature_class|state_name|map_name|prim_lat_dec|prim_long_dec

Input can be a local file (``--src``) or fetched over the network (``--url``).
``.zip`` and ``.gz`` inputs are handled transparently. Column names are matched
case-insensitively, so both the legacy GNIS schema (``FEATURE_NAME``,
``STATE_ALPHA``, ``MAP_NAME`` ...) and the current ``DomesticNames_*`` schema
work; ``map_name`` (the USGS quad) is captured when present, else left blank.

Download the source from the USGS GNIS data page (pick the National file or the
California state file, "Text/pipe" format):
    https://www.usgs.gov/us-board-on-geographic-names/download-gnis-data
NOTE: USGS has changed these URLs over time, so this script does not hardcode
one -- pass the current link to ``--url``, or download manually and use ``--src``.

Usage:
    python scripts/build_gnis_gaps.py --src ~/Downloads/DomesticNames_CA.txt
    python scripts/build_gnis_gaps.py --url https://.../DomesticNames_CA.zip
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "source" / "gnis_sierra_gaps.txt"

# (lat_min, lat_max, lon_min, lon_max) -- matches merge_passes.SIERRA_BBOX.
SIERRA_BBOX = (35.0, 41.5, -121.0, -117.0)

OUT_HEADER = ["feature_name", "feature_class", "state_name",
              "map_name", "prim_lat_dec", "prim_long_dec"]

# Logical field -> accepted source header names (lower-cased).
FIELD_ALIASES = {
    "feature_name": ["feature_name"],
    "feature_class": ["feature_class"],
    "state_name": ["state_name", "state_alpha"],
    "map_name": ["map_name"],
    "prim_lat_dec": ["prim_lat_dec", "primary_lat_dec", "prim_lat_dec_deg"],
    "prim_long_dec": ["prim_long_dec", "primary_long_dec", "prim_long_dec_deg"],
}


def read_text(src: Path | None, url: str | None) -> io.TextIOBase:
    """Return a text stream for a local or remote GNIS file (.txt/.zip/.gz)."""
    if url:
        print(f"Fetching {url}")
        raw = urllib.request.urlopen(url, timeout=120).read()
        name = url
    else:
        raw = src.read_bytes()
        name = str(src)

    if name.lower().endswith(".zip"):
        zf = zipfile.ZipFile(io.BytesIO(raw))
        member = next((n for n in zf.namelist() if n.lower().endswith(".txt")), None)
        if not member:
            raise ValueError(f"No .txt member found in zip: {zf.namelist()}")
        print(f"  reading {member} from zip")
        return io.TextIOWrapper(zf.open(member), encoding="utf-8-sig")
    if name.lower().endswith(".gz"):
        return io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding="utf-8-sig")
    return io.StringIO(raw.decode("utf-8-sig"))


def resolve_columns(header: list[str]) -> dict[str, str]:
    lower = {h.strip().lower(): h for h in header}
    cols: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        match = next((lower[a] for a in aliases if a in lower), None)
        if match:
            cols[field] = match
    required = {"feature_name", "feature_class", "prim_lat_dec", "prim_long_dec"}
    missing = required - cols.keys()
    if missing:
        raise ValueError(
            f"GNIS file missing required column(s): {sorted(missing)}. "
            f"Header was: {header}"
        )
    return cols


def in_box(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = SIERRA_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--src", type=Path, help="local GNIS names file (.txt/.zip/.gz)")
    grp.add_argument("--url", help="URL to a GNIS names file (.txt/.zip/.gz)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    stream = read_text(args.src, args.url)
    reader = csv.reader(stream, delimiter="|")
    try:
        header = next(reader)
    except StopIteration:
        print("Empty GNIS file.")
        return 1
    cols = resolve_columns(header)
    idx = {f: header.index(h) for f, h in cols.items()}

    kept, scanned = [], 0
    for row in reader:
        scanned += 1
        if len(row) <= max(idx.values()):
            continue
        if row[idx["feature_class"]].strip().lower() != "gap":
            continue
        try:
            lat = float(row[idx["prim_lat_dec"]]); lon = float(row[idx["prim_long_dec"]])
        except ValueError:
            continue
        if not in_box(lat, lon):
            continue
        kept.append({
            "feature_name": row[idx["feature_name"]].strip(),
            "feature_class": "Gap",
            "state_name": row[idx["state_name"]].strip() if "state_name" in idx else "",
            "map_name": row[idx["map_name"]].strip() if "map_name" in idx else "",
            "prim_lat_dec": f"{lat:.7f}",
            "prim_long_dec": f"{lon:.7f}",
        })

    kept.sort(key=lambda r: r["feature_name"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_HEADER, delimiter="|")
        w.writeheader()
        w.writerows(kept)

    print(f"Scanned {scanned} rows; kept {len(kept)} Sierra Gap features -> {args.out}")
    if not kept:
        print("WARNING: no Gap features matched. Check the file/box.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
