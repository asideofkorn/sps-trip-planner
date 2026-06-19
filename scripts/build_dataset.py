#!/usr/bin/env python3
"""Build the authoritative peak dataset from the official Sierra Club sources.

Inputs (place under ``data/source/`` yourself — these copyrighted Sierra Club
documents are NOT redistributed in this repo; see DATA_LICENSE.md):
  * sps_list_with_mileage.xls          - SPS list + per-peak mileage/gain/TH
  * scrambler_ratings_non_sps_2025.pdf - non-SPS High Sierra peaks

Download them from https://angeles.sierraclub.org/sierra_peaks. The committed
data/sps_peaks.csv already contains the built result, so you only need these to
rebuild from scratch.

Output:
  * data/sps_peaks.csv  - one row per peak with rich attributes. Latitude and
    longitude are left blank here; they are joined in afterward by
    ``scripts/merge_coords.py`` from a peakbagger GPX/CSV export, because none
    of the Sierra Club source documents contain full lat/long coordinates.

The numeric/text fields below are factual data (names, elevations, ratings)
extracted from the published list; they are not creative content.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source"
OUT = ROOT / "data" / "sps_peaks.csv"

FIELDS = [
    "name", "latitude", "longitude", "elevation_ft", "list", "section",
    "class", "emblem", "mountaineers", "mileage_rt", "gain_ft", "loss_ft",
    "trailhead", "quad", "elev_estimated", "coord_source",
]


def _norm(name: str) -> str:
    """Normalize a peak name for cross-sheet matching."""
    s = str(name).strip().lower()
    s = s.replace("mt.", "mount").replace("mt ", "mount ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _parse_elev(value) -> tuple[int | None, bool]:
    """Parse an elevation cell like '14,042+' -> (14042, True)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, False
    s = str(value).strip().replace(",", "")
    estimated = s.endswith("+")
    s = s.rstrip("+").strip()
    try:
        return int(round(float(s))), estimated
    except ValueError:
        return None, estimated


def _badge_names(xls_path: Path, sheet: str) -> set[str]:
    df = pd.read_excel(xls_path, sheet_name=sheet, header=0)
    col = df.columns[0]
    return {_norm(n) for n in df[col].dropna() if str(n).strip().lower() != "peak name"}


def parse_sps(xls_path: Path) -> list[dict]:
    df = pd.read_excel(
        xls_path, sheet_name="SPS LIST", header=0,
        converters={"Section": lambda v: str(v).strip()},
    )
    emblem = _badge_names(xls_path, "Emblem")
    mountaineers = _badge_names(xls_path, "Mountaineers")

    rows: list[dict] = []
    for _, r in df.iterrows():
        name = r["Peak Name"]
        # Real peak rows have a numeric "Section" like "1.10"; footnotes don't.
        section = str(r.get("Section", "")).strip()
        if not re.match(r"^\d+\.\d+$", section):
            continue
        elev, est = _parse_elev(r["Summit"])
        nkey = _norm(name)
        rows.append({
            "name": str(name).strip(),
            "latitude": "", "longitude": "",
            "elevation_ft": elev if elev is not None else "",
            "list": "SPS",
            "section": section,
            "class": str(r.get("Class", "")).strip(),
            "emblem": nkey in emblem,
            "mountaineers": nkey in mountaineers,
            "mileage_rt": "" if pd.isna(r.get("Mileage")) else r.get("Mileage"),
            "gain_ft": "" if pd.isna(r.get("Gain")) else int(r.get("Gain")),
            "loss_ft": "" if pd.isna(r.get("Loss")) else int(r.get("Loss")),
            "trailhead": "" if pd.isna(r.get("Trail Head")) else str(r.get("Trail Head")).strip(),
            "quad": "" if pd.isna(r.get("Quad. Map")) else str(r.get("Quad. Map")).strip(),
            "elev_estimated": est,
            "coord_source": "",
        })
    return rows


# Lines beginning "<sec>.<n> <name> <elev> <route...>" ; a leading region
# header looks like "3. Olancha to Langley and West".
_NONSPS_RE = re.compile(r'^(\d+\.\d+)\s+(.+?)\s+(\d{4,5}\+?)\s+(.*)$')
_YDS_RE = re.compile(r'\b(\d(?:s\d|sr\d)?(?:-\d)?)\b')


def parse_non_sps(pdf_path: Path) -> list[dict]:
    reader = PdfReader(str(pdf_path))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)

    rows: list[dict] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        m = _NONSPS_RE.match(line.strip())
        if not m:
            continue
        section, name, elev_s, rest = m.groups()
        name = name.strip().strip('"“”')
        if name in seen:
            continue
        seen.add(name)
        elev, est = _parse_elev(elev_s)
        yds = _YDS_RE.search(rest)
        quad = rest.split()[-1] if rest.split() else ""
        rows.append({
            "name": name,
            "latitude": "", "longitude": "",
            "elevation_ft": elev if elev is not None else "",
            "list": "non-SPS",
            "section": section,
            "class": yds.group(1) if yds else "",
            "emblem": False, "mountaineers": False,
            "mileage_rt": "", "gain_ft": "", "loss_ft": "",
            "trailhead": "", "quad": quad,
            "elev_estimated": est, "coord_source": "",
        })
    return rows


def main() -> None:
    for f in ("sps_list_with_mileage.xls", "scrambler_ratings_non_sps_2025.pdf"):
        if not (SRC / f).exists():
            raise SystemExit(
                f"Source document not found: data/source/{f}\n"
                "The Sierra Club source documents are not redistributed in this "
                "repo (see DATA_LICENSE.md). Download them from "
                "https://angeles.sierraclub.org/sierra_peaks and place them under "
                "data/source/. The committed data/sps_peaks.csv already contains "
                "the built result."
            )
    sps = parse_sps(SRC / "sps_list_with_mileage.xls")
    non_sps = parse_non_sps(SRC / "scrambler_ratings_non_sps_2025.pdf")
    rows = sps + non_sps

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    n_emblem = sum(1 for r in sps if r["emblem"])
    n_mtn = sum(1 for r in sps if r["mountaineers"])
    print(f"SPS peaks:      {len(sps)}  (emblem={n_emblem}, mountaineers={n_mtn})")
    print(f"non-SPS peaks:  {len(non_sps)}")
    print(f"Wrote {len(rows)} rows -> {OUT.relative_to(ROOT)}")
    print("NOTE: latitude/longitude are blank; run scripts/merge_coords.py to fill them.")


if __name__ == "__main__":
    main()
