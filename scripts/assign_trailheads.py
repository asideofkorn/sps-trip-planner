"""Assign each peak its nearest trailhead from data/trailheads.csv.

Adds three columns to ``data/sps_peaks.csv``:
  * ``nearest_trailhead``      — name of the closest curated trailhead
  * ``nearest_trailhead_side`` — east / west / crest
  * ``nearest_trailhead_mi``   — miles to that trailhead

By default the distance is straight-line (great-circle). With ``--use-passes``
the approach is **crest-aware**: a trailhead on the far side of the Sierra crest
from the peak is reached by routing over the cheapest pass (so a peak is not
matched to a closer-as-the-crow-flies trailhead it can't actually reach without
crossing the crest). That mode also writes a fourth column,
``nearest_trailhead_pass`` — the pass the approach crosses, or blank if none.

These give a clean, geographically-grounded access point per peak (unlike the
raw ``trailhead`` text, which mixes point trailheads with long trail names).
Group on it with: ``cli.py --by-trailhead --trailhead-field nearest_trailhead``.

NOTE: trailhead coordinates in data/trailheads.csv are curated to ~0.001 deg and
spot-checked against public sources; distances are straight-line (or straight
line via a pass), not trail mileage, so treat them as a relative signal.

Usage:
    python scripts/assign_trailheads.py                 # straight-line
    python scripts/assign_trailheads.py --use-passes    # crest-aware via passes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sierra_peaks.distances import haversine_miles
PEAKS = ROOT / "data" / "sps_peaks.csv"
TRAILHEADS = ROOT / "data" / "trailheads.csv"
PASSES = ROOT / "data" / "passes.csv"


class _Pt:
    """Minimal lat/lon/elevation holder for PassRouter.leg()."""
    __slots__ = ("latitude", "longitude", "elevation_ft")

    def __init__(self, lat, lon, elev):
        self.latitude = float(lat)
        self.longitude = float(lon)
        self.elevation_ft = float(elev) if pd.notna(elev) else 0.0


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--use-passes", action="store_true",
                    help="crest-aware approach: route over the cheapest pass when "
                         "the trailhead is across the crest from the peak")
    ap.add_argument("--pass-tier", type=int, default=1, choices=[1, 2],
                    help="passes usable as crossings (1 = named only, 2 = all gaps)")
    args = ap.parse_args(argv)

    peaks = pd.read_csv(PEAKS)
    th = pd.read_csv(TRAILHEADS)

    router = None
    if args.use_passes:
        from sierra_peaks.passes import build_router
        router = build_router(PASSES, candidate_tier=args.pass_tier)

    names, sides, dists, passes_crossed = [], [], [], []
    for _, p in peaks.iterrows():
        if pd.isna(p["latitude"]) or pd.isna(p["longitude"]):
            names.append(None); sides.append(None); dists.append(None)
            passes_crossed.append(None)
            continue
        peak_pt = _Pt(p["latitude"], p["longitude"], p.get("elevation_ft"))
        best_i, best_d, best_pass = -1, float("inf"), None
        for i, t in th.iterrows():
            if router is not None:
                leg = router.leg(_Pt(t["latitude"], t["longitude"],
                                     t.get("elevation_ft")), peak_pt, by="effective")
                d, via = leg.effective_mi, leg.via_pass
            else:
                d = haversine_miles(p["latitude"], p["longitude"],
                                    t["latitude"], t["longitude"])
                via = None
            if d < best_d:
                best_d, best_i, best_pass = d, i, via
        names.append(th.at[best_i, "name"])
        sides.append(th.at[best_i, "side"])
        dists.append(round(best_d, 1))
        passes_crossed.append(best_pass)

    peaks["nearest_trailhead"] = names
    peaks["nearest_trailhead_side"] = sides
    peaks["nearest_trailhead_mi"] = dists
    if args.use_passes:
        peaks["nearest_trailhead_pass"] = passes_crossed
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
