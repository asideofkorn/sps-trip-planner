"""Assign each peak its nearest trailhead (straight-line) from data/trailheads.csv.

Adds three columns to ``data/sps_peaks.csv``:
  * ``nearest_trailhead``      — name of the closest curated trailhead
  * ``nearest_trailhead_side`` — east / west / crest
  * ``nearest_trailhead_mi``   — great-circle miles to that trailhead

These give a clean, geographically-grounded access point per peak (unlike the
raw ``trailhead`` text, which mixes point trailheads with long trail names).
Group on it with: ``cli.py --by-trailhead --trailhead-field nearest_trailhead``.

NOTE: trailhead coordinates in data/trailheads.csv are curated to ~0.001 deg and
spot-checked against public sources; the distance is straight-line, not trail
mileage, so treat it as a relative "which trailhead is closest" signal.

Usage:
    python scripts/assign_trailheads.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sierra_peaks.distances import haversine_miles
PEAKS = ROOT / "data" / "sps_peaks.csv"
TRAILHEADS = ROOT / "data" / "trailheads.csv"


def main() -> None:
    peaks = pd.read_csv(PEAKS)
    th = pd.read_csv(TRAILHEADS)

    names, sides, dists = [], [], []
    for _, p in peaks.iterrows():
        if pd.isna(p["latitude"]) or pd.isna(p["longitude"]):
            names.append(None); sides.append(None); dists.append(None)
            continue
        best_i, best_d = -1, float("inf")
        for i, t in th.iterrows():
            d = haversine_miles(p["latitude"], p["longitude"],
                                t["latitude"], t["longitude"])
            if d < best_d:
                best_d, best_i = d, i
        names.append(th.at[best_i, "name"])
        sides.append(th.at[best_i, "side"])
        dists.append(round(best_d, 1))

    peaks["nearest_trailhead"] = names
    peaks["nearest_trailhead_side"] = sides
    peaks["nearest_trailhead_mi"] = dists
    peaks.to_csv(PEAKS, index=False)

    sps = peaks[peaks["list"] == "SPS"]
    print(f"Assigned nearest trailhead to {peaks['nearest_trailhead'].notna().sum()} peaks")
    print(f"SPS peaks: {len(sps)} | distinct trailheads used (SPS): "
          f"{sps['nearest_trailhead'].nunique()}")
    print(f"SPS median distance to trailhead: "
          f"{sps['nearest_trailhead_mi'].median():.1f} mi  "
          f"(max {sps['nearest_trailhead_mi'].max():.1f} mi)")
    print("\nSide split (SPS):")
    print(sps["nearest_trailhead_side"].value_counts().to_string())


if __name__ == "__main__":
    main()
