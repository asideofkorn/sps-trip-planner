"""Tests for scripts/split_collections.py's duplicate-name tie-break.

scripts/ isn't a package, so the module is loaded by file path rather than
imported normally.

Run with:  python -m pytest tests/test_split_collections.py
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "split_collections", os.path.join(ROOT, "scripts", "split_collections.py")
)
split_collections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(split_collections)


def _staging_row(name, list_value, elevation_ft):
    return {
        "name": name, "latitude": 37.0, "longitude": -118.0,
        "elevation_ft": elevation_ft, "elev_estimated": False, "coord_source": "GNIS",
        "nearest_trailhead": "", "nearest_trailhead_side": "", "nearest_trailhead_mi": "",
        "nearest_trailhead_pass": "",
        "list": list_value, "section": "1.1", "class": "1", "emblem": False,
        "mountaineers": False, "mileage_rt": "", "gain_ft": "", "loss_ft": "",
        "trailhead": "", "quad": "", "benchmark": False, "benchmark_rating": "",
    }


def test_dedupe_keeps_sps_row_and_writes_a_note():
    df = pd.DataFrame([
        _staging_row("Mount Johnson", "SPS", 12871),
        _staging_row("Mount Johnson", "non-SPS", 12868),
        _staging_row("Some Other Peak", "SPS", 10000),
    ])
    result = split_collections._dedupe_by_name(df)

    assert len(result) == 2
    kept = result[result["name"] == "Mount Johnson"].iloc[0]
    assert kept["list"] == "SPS"
    assert kept["elevation_ft"] == 12871
    assert "unconfirmed" in kept["notes"].lower()
    assert "non-sps" in kept["notes"].lower()

    # An unaffected row must not get a spurious note.
    other = result[result["name"] == "Some Other Peak"].iloc[0]
    assert other["notes"] == "" or pd.isna(other["notes"])


def test_dedupe_no_duplicates_is_a_no_op():
    df = pd.DataFrame([_staging_row("Mount Whitney", "SPS", 14505)])
    result = split_collections._dedupe_by_name(df)
    assert len(result) == 1
    assert "notes" not in result.columns or result.iloc[0].get("notes", "") in ("", None)


def test_dedupe_rejects_unexpected_duplicate_shape():
    # Three rows for the same name, or two rows both list=SPS, aren't the
    # known SPS/non-SPS overlap this tie-break is designed for.
    df = pd.DataFrame([
        _staging_row("Weird Peak", "SPS", 1000),
        _staging_row("Weird Peak", "SPS", 1001),
    ])
    with pytest.raises(ValueError):
        split_collections._dedupe_by_name(df)


def test_dedupe_preserves_notes_column_through_split(tmp_path):
    staging = tmp_path / "staging.csv"
    pd.DataFrame([
        _staging_row("Mount Johnson", "SPS", 12871),
        _staging_row("Mount Johnson", "non-SPS", 12868),
    ]).to_csv(staging, index=False)

    core_out = tmp_path / "peaks.csv"
    collection_out = tmp_path / "sps.csv"
    split_collections.split(staging, core_out, collection_out)

    core = pd.read_csv(core_out)
    assert "notes" in core.columns
    assert "unconfirmed" in core.iloc[0]["notes"].lower()
