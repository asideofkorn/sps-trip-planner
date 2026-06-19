"""Tests for the Sierra Peaks clustering toolkit.

Run with:  python -m pytest tests/  (or)  python tests/test_pipeline.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sierra_peaks.model import Peak
from sierra_peaks.data_loader import load_peaks
from sierra_peaks.distances import (
    haversine_miles,
    naismith_effective_miles,
    leg_metrics,
    build_distance_matrix,
)
from sierra_peaks.tsp import solve_tsp, route_metrics
from sierra_peaks.clustering import ClusterConfig, cluster_peaks
from sierra_peaks.pipeline import build_itineraries, rank_clusters, plan_trips
from sierra_peaks import manual

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "sps_sample.csv")


def test_haversine_known_distance():
    # Whitney to North Palisade is roughly 36 miles great-circle.
    d = haversine_miles(36.5785, -118.2923, 37.0945, -118.5147)
    assert 34 < d < 38, d


def test_haversine_zero():
    assert haversine_miles(37.0, -118.0, 37.0, -118.0) == 0.0


def test_naismith_adds_ascent():
    # 2000 ft ascent == 3 equivalent flat miles.
    assert math.isclose(naismith_effective_miles(0.0, 2000.0), 3.0, rel_tol=1e-6)
    # Descent adds nothing.
    assert naismith_effective_miles(5.0, 0.0) == 5.0


def test_leg_metrics_directional_ascent():
    low = Peak("low", 37.0, -118.0, 10000)
    high = Peak("high", 37.0, -118.0, 12000)
    _, asc_up, _ = leg_metrics(low, high)
    _, asc_down, _ = leg_metrics(high, low)
    assert asc_up == 2000
    assert asc_down == 0


def test_distance_matrix_symmetric():
    peaks = load_peaks(DATA)[:6]
    mat = build_distance_matrix(peaks, metric="effective")
    assert mat.shape == (6, 6)
    assert (mat == mat.T).all()
    assert (mat.diagonal() == 0).all()


def test_solve_tsp_orders_collinear_peaks():
    # Five peaks strung out west-to-east; optimal open path is in order.
    peaks = [Peak(f"p{i}", 37.0, -118.0 + 0.1 * i, 12000) for i in range(5)]
    cost = build_distance_matrix(peaks, metric="haversine")
    order = solve_tsp(cost)
    assert order in ([0, 1, 2, 3, 4], [4, 3, 2, 1, 0])


def test_solve_tsp_heuristic_large():
    # Force the heuristic branch (> BRUTE_FORCE_MAX peaks).
    peaks = [Peak(f"p{i}", 37.0, -118.0 + 0.05 * i, 12000) for i in range(12)]
    cost = build_distance_matrix(peaks, metric="haversine")
    order = solve_tsp(cost)
    assert sorted(order) == list(range(12))
    # Monotonic line should be recovered exactly.
    assert order in ([list(range(12))][0], list(range(11, -1, -1)))


def test_clusters_respect_budget():
    peaks = load_peaks(DATA)
    config = ClusterConfig(eps_mi=6.0, miles_per_day=15.0, max_days=3)
    clusters = plan_trips(peaks, config)
    # Every peak appears exactly once across all clusters.
    names = [n for c in clusters for n in c.peak_names]
    assert sorted(names) == sorted(p.name for p in peaks)
    # No trip exceeds the effort budget.
    for c in clusters:
        assert c.total_effective_mi <= config.max_effective_mi + 1e-6
        assert 1 <= c.estimated_days <= config.max_days


def test_ranking_is_descending():
    peaks = load_peaks(DATA)
    clusters = plan_trips(peaks)
    scores = [c.score for c in clusters]
    assert scores == sorted(scores, reverse=True)
    assert [c.cluster_id for c in clusters] == list(range(len(clusters)))


def test_exclude_drops_peak():
    peaks = load_peaks(DATA)
    config = ClusterConfig(exclude=["Mount Whitney"])
    clusters = plan_trips(peaks, config)
    names = {n for c in clusters for n in c.peak_names}
    assert "Mount Whitney" not in names


def test_force_together_keeps_peaks_in_one_cluster():
    peaks = load_peaks(DATA)
    # Two peaks that DBSCAN would normally separate.
    config = ClusterConfig(force_together=[["Mount Dana", "Matterhorn Peak"]])
    clusters = plan_trips(peaks, config)
    for c in clusters:
        if "Mount Dana" in c.peak_names:
            assert "Matterhorn Peak" in c.peak_names
            break
    else:
        raise AssertionError("Mount Dana not found in any cluster")


def test_by_trailhead_keeps_shared_trailhead_together():
    # Two peaks ~40 mi apart (DBSCAN would separate them) that share a trailhead.
    far_a = Peak("A", 36.50, -118.30, 13000, meta={"trailhead": "Shared TH"})
    far_b = Peak("B", 37.10, -118.55, 13000, meta={"trailhead": "Shared TH"})
    other = Peak("C", 40.30, -120.30, 9000, meta={"trailhead": "Other TH"})
    peaks = [far_a, far_b, other]

    # Without the flag the two distant peaks land in separate trips.
    base = plan_trips(peaks, ClusterConfig(eps_mi=6.0, max_days=10))
    a_trip = next(c for c in base if "A" in c.peak_names)
    assert "B" not in a_trip.peak_names

    # With the flag they share a trip despite the distance.
    by_th = plan_trips(peaks, ClusterConfig(eps_mi=6.0, max_days=10, by_trailhead=True))
    a_trip = next(c for c in by_th if "A" in c.peak_names)
    assert "B" in a_trip.peak_names
    assert "C" not in a_trip.peak_names


def test_trailhead_max_mi_splits_distant_shared_trailhead():
    # Three peaks share a trailhead name but A,B are close and C is far away.
    a = Peak("A", 37.00, -118.50, 13000, meta={"trailhead": "Long Trail"})
    b = Peak("B", 37.03, -118.52, 13000, meta={"trailhead": "Long Trail"})
    c = Peak("C", 37.60, -118.90, 13000, meta={"trailhead": "Long Trail"})
    peaks = [a, b, c]

    # No cap: all three are forced into one trip.
    uncapped = plan_trips(peaks, ClusterConfig(by_trailhead=True, max_days=10))
    a_trip = next(t for t in uncapped if "A" in t.peak_names)
    assert {"A", "B", "C"} <= set(a_trip.peak_names)

    # 10-mile cap: A+B stay together, distant C breaks off.
    capped = plan_trips(
        peaks, ClusterConfig(by_trailhead=True, trailhead_max_mi=10.0,
                             eps_mi=2.0, max_days=10)
    )
    a_trip = next(t for t in capped if "A" in t.peak_names)
    assert "B" in a_trip.peak_names
    assert "C" not in a_trip.peak_names


def test_trailhead_field_selects_metadata_column():
    # Group on a custom field rather than the default "trailhead".
    a = Peak("A", 36.50, -118.30, 13000, meta={"nearest_trailhead": "TH1"})
    b = Peak("B", 37.10, -118.55, 13000, meta={"nearest_trailhead": "TH1"})
    peaks = [a, b]
    grouped = plan_trips(
        peaks, ClusterConfig(by_trailhead=True, trailhead_field="nearest_trailhead",
                             eps_mi=6.0, max_days=10)
    )
    a_trip = next(t for t in grouped if "A" in t.peak_names)
    assert "B" in a_trip.peak_names


def test_manual_merge_and_split_roundtrip():
    peaks = load_peaks(DATA)
    config = ClusterConfig()
    clusters = plan_trips(peaks, config)
    n_before = len(clusters)

    groups = manual.merge_clusters(clusters, [0, 1])
    merged = rank_clusters(build_itineraries(groups, config))
    assert len(merged) == n_before - 1

    # Splitting the largest cluster increases the count.
    biggest = max(merged, key=lambda c: c.num_peaks)
    if biggest.num_peaks >= 2:
        groups = manual.split_cluster(merged, biggest.cluster_id, 2)
        split = rank_clusters(build_itineraries(groups, config))
        assert len(split) == len(merged) + 1


def test_load_peaks_json(tmp_path):
    import json
    peaks = load_peaks(DATA)[:3]
    payload = {"peaks": [p.to_dict() for p in peaks]}
    fp = tmp_path / "p.json"
    fp.write_text(json.dumps(payload))
    loaded = load_peaks(str(fp))
    assert [p.name for p in loaded] == [p.name for p in peaks]


def _run_all():
    import tempfile, types
    g = dict(globals())
    tests = [v for k, v in g.items() if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for t in tests:
        import inspect
        params = inspect.signature(t).parameters
        if "tmp_path" in params:
            with tempfile.TemporaryDirectory() as d:
                import pathlib
                t(pathlib.Path(d))
        else:
            t()
        passed += 1
        print(f"  PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run_all()
