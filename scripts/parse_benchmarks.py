"""Parse benchmark_routes.pdf into a normalized route table.

The SPS "Benchmark Routes" sheet anchors each Scrambler Rating category
(S-1.0 ... S-4.2) with one or more reference climbs. A single peak can appear
under multiple ratings (e.g. Mount Whitney via the trail at S-1.0 and via the
Mountaineer's Route at S-3.1), so the natural model is **one row per route**,
with the peak as a foreign key.

Outputs ``data/benchmark_routes.csv`` with one row per benchmark route, joined
to ``data/sps_peaks.csv`` for coordinates / section where the peak matches.

Usage:
    python scripts/parse_benchmarks.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "source" / "benchmark_routes.pdf"
PEAKS_CSV = ROOT / "data" / "sps_peaks.csv"
OUT_CSV = ROOT / "data" / "benchmark_routes.csv"

CLASS_RE = re.compile(r"^Class\s+(\d)\b")
RATING_RE = re.compile(r"^S-(\d\.\d):")
# A route line: optional leading flag chars (* / #), a Title-Case peak name,
# " - ", then the route description.
ROUTE_RE = re.compile(r"^([*#]+\s*)?([A-Z][A-Za-z.'’]*(?:\s+[A-Z0-9][A-Za-z.'’&]*)*)\s+-\s+(.+)$")
# Lines from the legend / footer that must never be treated as routes.
SKIP = ("= Emblem", "= Mountaineering", "= Vagmarken",
        "benchmark routes are on SPS", "refinements to rating",
        "Benchmark Routes for")


def extract_lines() -> list[str]:
    if not PDF.exists():
        raise SystemExit(
            f"Source document not found: {PDF.relative_to(ROOT)}\n"
            "The Sierra Club source PDFs are not redistributed in this repo "
            "(see DATA_LICENSE.md). Download the SPS 'Benchmark Routes' sheet "
            "from https://angeles.sierraclub.org/sierra_peaks and place it at "
            f"{PDF.relative_to(ROOT)} to regenerate. The committed "
            "data/benchmark_routes.csv already contains the parsed result."
        )
    reader = PdfReader(str(PDF))
    lines: list[str] = []
    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            s = raw.strip()
            if s:
                lines.append(s)
    return lines


def parse() -> pd.DataFrame:
    rows = []
    cur_class = cur_rating = None
    for line in extract_lines():
        if any(tok in line for tok in SKIP):
            continue
        m = CLASS_RE.match(line)
        if m:
            cur_class = int(m.group(1))
            continue
        m = RATING_RE.match(line)
        if m:
            cur_rating = f"S-{m.group(1)}"
            continue
        m = ROUTE_RE.match(line)
        if m and cur_rating:
            flags = (m.group(1) or "").replace(" ", "")
            peak = m.group(2).strip()
            route = m.group(3).strip()
            rows.append({
                "scrambler_rating": cur_rating,
                "ydc_class": cur_class,
                "peak": peak,
                "route": route,
                "emblem": flags.count("*") == 2,
                "mountaineering": flags.count("*") == 1,
                "vagmarken": "#" in flags,
            })
    return pd.DataFrame(rows)


def join_coords(df: pd.DataFrame) -> pd.DataFrame:
    peaks = pd.read_csv(PEAKS_CSV)
    lookup = {n.lower(): n for n in peaks["name"]}
    cols = ["name", "latitude", "longitude", "elevation_ft", "section", "list"]
    by_name = peaks.set_index("name")[cols[1:]]

    matched, lat, lon, elev, sec = [], [], [], [], []
    for peak in df["peak"]:
        canon = lookup.get(peak.lower())
        matched.append(canon or "")
        if canon is not None:
            r = by_name.loc[canon]
            lat.append(r["latitude"]); lon.append(r["longitude"])
            elev.append(r["elevation_ft"]); sec.append(r["section"])
        else:
            lat.append(None); lon.append(None); elev.append(None); sec.append(None)
    df = df.copy()
    df["sps_name"] = matched
    df["latitude"] = lat
    df["longitude"] = lon
    df["elevation_ft"] = elev
    df["section"] = sec
    return df


def main() -> None:
    df = parse()
    df = join_coords(df)
    # Stable ordering: by rating then peak, easiest first.
    df = df.sort_values(["scrambler_rating", "peak"]).reset_index(drop=True)
    df.insert(0, "route_id", range(1, len(df) + 1))
    df.to_csv(OUT_CSV, index=False)

    unmatched = df[df["sps_name"] == ""]["peak"].tolist()
    print(f"Parsed {len(df)} benchmark routes across "
          f"{df['peak'].nunique()} peaks -> {OUT_CSV.relative_to(ROOT)}")
    if unmatched:
        print("WARNING unmatched peaks:", unmatched)
    else:
        print("All peaks matched to data/sps_peaks.csv")


if __name__ == "__main__":
    main()
