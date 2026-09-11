"""Load SPS peak data from CSV or JSON into :class:`Peak` objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pandas as pd

from .model import Peak, Trailhead

# Accepted column aliases -> canonical field name.
_COLUMN_ALIASES = {
    "name": "name",
    "peak": "name",
    "peak_name": "name",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lon": "longitude",
    "lng": "longitude",
    "long": "longitude",
    "elevation_ft": "elevation_ft",
    "elevation": "elevation_ft",
    "elev_ft": "elevation_ft",
    "elev": "elevation_ft",
    "region": "region",
    "area": "region",
}

_REQUIRED = {"name", "latitude", "longitude", "elevation_ft"}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in _COLUMN_ALIASES:
            rename[col] = _COLUMN_ALIASES[key]
    df = df.rename(columns=rename)
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            f"Input is missing required column(s): {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )
    if "region" not in df.columns:
        df["region"] = ""
    return df


# Extra (non-core) columns carried into Peak.meta when present.
_META_COLUMNS = [
    "list", "class", "section", "emblem", "mountaineers",
    "mileage_rt", "gain_ft", "loss_ft", "trailhead", "quad", "coord_source",
    "benchmark", "benchmark_rating",
    "nearest_trailhead", "nearest_trailhead_side", "nearest_trailhead_mi",
]


def load_peaks(
    path: str | Path,
    list_filter: str | None = None,
    require_coords: bool = True,
    collections_path: str | Path | None = None,
) -> List[Peak]:
    """Load peaks from a ``.csv`` or ``.json`` file.

    The loader is tolerant of common column-name variants (``lat``/``lon``,
    ``elevation`` vs ``elevation_ft``, etc.). JSON may be a top-level list of
    objects or an object with a ``"peaks"`` key.

    Parameters
    ----------
    list_filter : str, optional
        If given and the data has a ``list`` column, keep only rows whose list
        equals this value (e.g. ``"SPS"``). Case-insensitive.
    require_coords : bool
        Skip rows with missing/blank latitude or longitude (default True).
    collections_path : str or Path, optional
        A collection file (e.g. ``data/collections/sps.csv``) to left-join
        onto ``path`` by ``name``, adding fields like ``list``/``section``/
        ``mileage_rt`` that belong to a named collection rather than to the
        peak's core identity (see :mod:`wayproof.model`'s ``Peak.collection``
        and ``DATA_LICENSE.md``'s Source Policy section). Optional --
        ``path`` alone is a complete, collection-agnostic peak dataset;
        omitting this just means no collection metadata is attached.
        Silently skipped if the file doesn't exist, same as
        :func:`wayproof.access.load_approaches`'s optional-file pattern.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Peak data file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open() as fh:
            raw = json.load(fh)
        records = raw["peaks"] if isinstance(raw, dict) and "peaks" in raw else raw
        df = pd.DataFrame(records)
    elif suffix in {".csv", ".tsv", ".txt"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r} (use .csv or .json)")

    df = _normalize_columns(df)

    if collections_path is not None:
        collections_path = Path(collections_path)
        if collections_path.exists():
            cdf = pd.read_csv(collections_path)
            overlap = (set(df.columns) & set(cdf.columns)) - {"name"}
            if overlap:
                raise ValueError(
                    f"Collection file {collections_path} redefines core "
                    f"column(s) {sorted(overlap)}; a collection should only "
                    f"add new fields keyed by name."
                )
            df = df.merge(cdf, on="name", how="left")

    if list_filter is not None and "list" in df.columns:
        df = df[df["list"].astype(str).str.lower() == list_filter.lower()]

    meta_cols = [c for c in _META_COLUMNS if c in df.columns]

    peaks: List[Peak] = []
    seen = set()
    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        if not name or name.lower() == "nan":
            continue
        if require_coords and (pd.isna(row["latitude"]) or pd.isna(row["longitude"])):
            continue
        if name in seen:
            raise ValueError(f"Duplicate peak name in input: {name!r}")
        seen.add(name)

        meta = {}
        for c in meta_cols:
            val = row[c]
            if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                continue
            meta[c] = bool(val) if c in ("emblem", "mountaineers", "benchmark") else val
        meta = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                for k, v in meta.items()}

        peaks.append(
            Peak(
                name=name,
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                elevation_ft=float(row["elevation_ft"]),
                region=str(row.get("region", "") or ""),
                meta=meta,
            )
        )

    if not peaks:
        raise ValueError("No valid peaks found in input file.")
    return peaks


def load_trailheads(path: str | Path) -> List[Trailhead]:
    """Load road-accessible trailheads from a CSV (see ``data/trailheads.csv``).

    Expected columns: ``name``, ``latitude``, ``longitude``, and optionally
    ``elevation_ft``, ``side``, ``notes``, ``wilderness_area``, ``land_agency``,
    ``permit_group`` (the last three feed :mod:`wayproof.permits`).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Trailhead file not found: {path}")
    df = pd.read_csv(path)
    df = _normalize_columns(df)  # reuse lat/lon/elevation aliasing

    def _field(row, col: str) -> str:
        # NaN is truthy in Python, so `row.get(col, "") or ""` silently turns a
        # blank CSV cell into the literal string "nan" -- check pd.isna instead.
        val = row.get(col)
        if val is None or pd.isna(val):
            return ""
        return str(val).strip()

    trailheads: List[Trailhead] = []
    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        if not name or name.lower() == "nan":
            continue
        if pd.isna(row["latitude"]) or pd.isna(row["longitude"]):
            continue
        elev = row.get("elevation_ft")
        trailheads.append(
            Trailhead(
                name=name,
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                elevation_ft=float(elev) if elev is not None and not pd.isna(elev) else 0.0,
                side=_field(row, "side"),
                notes=_field(row, "notes"),
                wilderness_area=_field(row, "wilderness_area"),
                land_agency=_field(row, "land_agency"),
                permit_group=_field(row, "permit_group"),
            )
        )
    if not trailheads:
        raise ValueError("No valid trailheads found in input file.")
    return trailheads
