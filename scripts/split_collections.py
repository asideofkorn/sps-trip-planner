#!/usr/bin/env python3
"""Split the combined peak-build staging file into a public-domain core
dataset plus an SPS collection layer.

This is the final step of the rebuild pipeline. ``build_dataset.py`` ->
``merge_gnis.py`` -> ``merge_coords.py`` -> ``assign_trailheads.py`` all
progressively enrich a single staging file (``data/sps_peaks.csv`` by
default) exactly as before -- none of that logic changed. This script then
splits that staging file's columns into:

- ``data/peaks.csv`` (the **core** dataset): name, coordinates, elevation,
  and the project-computed nearest-trailhead access signal. Collection-
  agnostic -- a peak's presence here never depends on Sierra Club data,
  only on having a name and a location (from GNIS, or a documented
  third-party fallback; see ``coord_source``).
- ``data/collections/sps.csv`` (the **SPS collection**): the fields that
  come specifically from the Sierra Club SPS program's own two source
  documents (the SPS list and the non-SPS scrambler ratings) -- list
  membership, section, class, emblem/mountaineers flags, official
  round-trip mileage/gain, named trail, quad, and benchmark rating.

See DATA_LICENSE.md's Source Policy section for why this split exists: it
keeps the project's core geography independent of a private compilation, so
a future non-Sierra-Club collection (a different range, a different list)
layers onto the same core dataset instead of requiring its own copy of
USGS-sourced facts.

Usage
-----
    python scripts/split_collections.py
    python scripts/split_collections.py --staging data/sps_peaks.csv \\
        --core-out data/peaks.csv --collection-out data/collections/sps.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# Collection-agnostic facts: a peak's location and identity.
_CORE_COLUMNS = [
    "name", "latitude", "longitude", "elevation_ft", "elev_estimated",
    "coord_source", "nearest_trailhead", "nearest_trailhead_side",
    "nearest_trailhead_mi", "nearest_trailhead_pass", "notes",
]

# Facts specific to the Sierra Club SPS program's own compilation (the SPS
# list and the non-SPS scrambler ratings share these columns).
_COLLECTION_COLUMNS = [
    "name", "list", "section", "class", "emblem", "mountaineers",
    "mileage_rt", "gain_ft", "loss_ft", "trailhead", "quad",
    "benchmark", "benchmark_rating",
]


def _dedupe_by_name(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse a peak name that appears under both `list=SPS` and
    `list=non-SPS` to its SPS row (see DATA_LICENSE.md's "Known follow-ups").

    This is a known, tracked data-quality issue (two names -- "Mount
    Johnson", "Thunder Mountain" -- appear once per list with conflicting
    elevation), not something this split invents. But the core dataset must
    have a unique `name` key for the core/collection join to be meaningful,
    so this makes an explicit, documented, conservative choice (prefer the
    primary SPS-list entry) rather than silently letting a duplicate name
    propagate into the split files. Independently resolving *which value is
    actually correct* (not just which list to prefer) stays a separate,
    tracked follow-up -- this does not assert the dropped row was wrong,
    only that a peak needs exactly one core identity to be joinable.

    The kept row's ``notes`` column records the conflict itself (rather than
    leaving it only in this docstring and DATA_LICENSE.md), so
    :func:`wayproof.reports.open_questions` can surface it live as an
    unconfirmed fact instead of it living solely as static prose.
    """
    dupes = df[df.duplicated("name", keep=False)]
    if dupes.empty:
        return df
    if "notes" not in df.columns:
        df["notes"] = ""
    for name in sorted(dupes["name"].unique()):
        rows = dupes[dupes["name"] == name]
        lists = set(rows.get("list", pd.Series(dtype=str)).str.upper())
        if lists != {"SPS", "NON-SPS"} or len(rows) != 2:
            raise ValueError(
                f"Unexpected duplicate-name shape for {name!r} ({len(rows)} "
                f"rows, list values {sorted(lists)}) -- the SPS-preferred "
                f"tie-break only handles the known SPS/non-SPS overlap; "
                f"update _dedupe_by_name if this is a new case."
            )
        print(f"NOTE: {name!r} appears under both SPS and non-SPS with "
              f"conflicting data -- keeping the SPS row for the split "
              f"output (see DATA_LICENSE.md's Known follow-ups).")
        kept_idx = rows[rows["list"].str.upper() == "SPS"].index
        df.loc[kept_idx, "notes"] = (
            "Also appears under list=non-SPS with conflicting data; this "
            "SPS-list entry was kept via a documented tie-break. Which "
            "value is actually correct remains unconfirmed -- see "
            "DATA_LICENSE.md's Known follow-ups."
        )
    keep_mask = ~df.index.isin(dupes.index) | (df.get("list", "").str.upper() == "SPS")
    return df[keep_mask]


def split(staging_path: Path, core_out: Path, collection_out: Path) -> None:
    df = pd.read_csv(staging_path)

    # "name" is always present; "notes" is an optional, project-added
    # annotation (written by _dedupe_by_name when it fires) rather than a
    # raw source field, so its absence from the staging file isn't an error.
    missing = set(_CORE_COLUMNS + _COLLECTION_COLUMNS) - set(df.columns) - {"name", "notes"}
    if missing:
        raise ValueError(
            f"Staging file {staging_path} is missing expected column(s): "
            f"{sorted(missing)}"
        )

    df = _dedupe_by_name(df)
    if "notes" not in df.columns:
        df["notes"] = ""

    core = df[[c for c in _CORE_COLUMNS if c in df.columns]].copy()
    collection = df[[c for c in _COLLECTION_COLUMNS if c in df.columns]].copy()

    core_out.parent.mkdir(parents=True, exist_ok=True)
    collection_out.parent.mkdir(parents=True, exist_ok=True)
    core.to_csv(core_out, index=False)
    collection.to_csv(collection_out, index=False)

    print(f"Wrote {len(core)} rows to {core_out}")
    print(f"Wrote {len(collection)} rows to {collection_out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staging", default=str(ROOT / "data" / "sps_peaks.csv"),
                     help="Combined build-staging file (default data/sps_peaks.csv)")
    ap.add_argument("--core-out", default=str(ROOT / "data" / "peaks.csv"),
                     help="Core dataset output path (default data/peaks.csv)")
    ap.add_argument("--collection-out", default=str(ROOT / "data" / "collections" / "sps.csv"),
                     help="SPS collection output path (default data/collections/sps.csv)")
    args = ap.parse_args(argv)

    split(Path(args.staging), Path(args.core_out), Path(args.collection_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
