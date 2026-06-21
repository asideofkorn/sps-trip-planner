"""Tests for the Sierra Peaks clustering toolkit.

Run with:  python -m pytest tests/  (or)  python tests/test_pipeline.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sierra_peaks.model import Peak, Trailhead
from sierra_peaks.data_loader import load_peaks, load_trailheads
from sierra_peaks.distances import (
    haversine_miles,
    naismith_effective_miles,
    leg_metrics,
    build_distance_matrix,
)
from sierra_peaks.tsp import solve_tsp, solve_tsp_cycle, route_metrics
from sierra_peaks.clustering import ClusterConfig, cluster_peaks
from sierra_peaks.pipeline import build_itineraries, rank_clusters, plan_trips
from sierra_peaks.approach import choose_trailhead, approach_metrics
from sierra_peaks.diagnostics import approach_amortization, format_approach_report
from sierra_peaks import manual

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "sps_sample.csv")
TRAILHEADS = os.path.join(os.path.dirname(__file__), "..", "data", "trailheads.csv")


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


def test_solve_tsp_cycle_orders_collinear_peaks():
    # Anchor (index 0) at the west end; cheapest closed tour runs out and back.
    peaks = [Peak(f"p{i}", 37.0, -118.0 + 0.1 * i, 12000) for i in range(5)]
    cost = build_distance_matrix(peaks, metric="haversine")
    tour = solve_tsp_cycle(cost, start=0)
    assert sorted(tour) == [0, 1, 2, 3, 4]
    assert tour[0] == 0


def test_load_trailheads():
    ths = load_trailheads(TRAILHEADS)
    assert len(ths) > 30
    assert all(th.name and th.side for th in ths)
    assert any(th.name.startswith("Whitney Portal") for th in ths)


def test_choose_trailhead_modal():
    ths = [
        Trailhead("A", 37.0, -118.0, 8000),
        Trailhead("B", 37.5, -118.5, 9000),
    ]
    peaks = [
        Peak("p1", 37.0, -118.0, 13000, meta={"nearest_trailhead": "A"}),
        Peak("p2", 37.0, -118.0, 13000, meta={"nearest_trailhead": "A"}),
        Peak("p3", 37.5, -118.5, 13000, meta={"nearest_trailhead": "B"}),
    ]
    assert choose_trailhead(peaks, ths).name == "A"


def test_choose_trailhead_centroid_fallback():
    # No usable nearest_trailhead names -> nearest trailhead to the centroid.
    ths = [Trailhead("Far", 40.0, -120.0, 7000), Trailhead("Near", 37.0, -118.0, 8000)]
    peaks = [Peak("p", 37.01, -118.01, 13000)]
    assert choose_trailhead(peaks, ths).name == "Near"


def test_approach_single_peak_equals_round_trip():
    # In + out for one peak reduces to the official round trip plus one-way gain.
    th = Trailhead("TH", 37.0, -118.0, 8000)
    p = Peak("P", 37.05, -118.05, 13000,
             meta={"mileage_rt": 10.0, "gain_ft": 5000, "nearest_trailhead": "TH"})
    m = approach_metrics(th, p, p)
    assert math.isclose(m["horizontal_mi"], 10.0)
    assert math.isclose(m["effective_mi"], 10.0 + naismith_effective_miles(0, 5000))
    assert m["elevation_gain_ft"] == 5000


def test_include_approach_increases_effort_and_sets_trailhead():
    peaks = load_peaks(DATA)
    trailheads = load_trailheads(TRAILHEADS)
    base = plan_trips(peaks, ClusterConfig(max_days=3))
    withth = plan_trips(peaks, ClusterConfig(max_days=3, include_approach=True),
                        trailheads=trailheads)
    base_eff = sum(c.total_effective_mi for c in base)
    appr_eff = sum(c.total_effective_mi for c in withth)
    assert appr_eff > base_eff  # approach only adds effort
    for c in withth:
        assert c.trailhead  # every trip gets an anchor
        assert c.approach_effective_mi > 0
        d = c.to_dict()
        assert "trailhead" in d and "approach_effective_mi" in d


def test_approach_off_by_default_leaves_output_unchanged():
    peaks = load_peaks(DATA)
    clusters = plan_trips(peaks)  # no trailheads, default config
    for c in clusters:
        assert c.trailhead == ""
        assert c.approach_effective_mi == 0.0
        assert "trailhead" not in c.to_dict()


def test_approach_amortization_flags_shared_trailheads():
    peaks = load_peaks(DATA)
    trailheads = load_trailheads(TRAILHEADS)
    config = ClusterConfig(max_days=2, include_approach=True)
    clusters = plan_trips(peaks, config, trailheads=trailheads)
    rows = approach_amortization(clusters, config)
    # Only trailheads serving >1 trip are reported.
    for r in rows:
        assert r.num_trips >= 2
        assert r.recoverable_mi >= 0
        assert r.min_trips_by_budget <= r.num_trips
    # Sorted by recoverable effort (then approach paid), descending.
    keys = [(r.recoverable_mi, r.approach_paid_mi) for r in rows]
    assert keys == sorted(keys, reverse=True)
    assert isinstance(format_approach_report(rows), str)


def test_approach_amortization_empty_when_no_shared_trailhead():
    # Two peaks at distinct trailheads -> no trailhead serves multiple trips.
    a = Peak("A", 36.50, -118.30, 13000,
             meta={"nearest_trailhead": "Whitney Portal", "mileage_rt": 6, "gain_ft": 3000})
    b = Peak("B", 39.30, -120.30, 9000,
             meta={"nearest_trailhead": "Castle Peak (Donner)", "mileage_rt": 5, "gain_ft": 2000})
    trailheads = load_trailheads(TRAILHEADS)
    config = ClusterConfig(include_approach=True)
    clusters = plan_trips([a, b], config, trailheads=trailheads)
    assert approach_amortization(clusters, config) == []
    assert "No trailhead" in format_approach_report([])


def test_approach_aware_split_adds_trips_when_over_budget():
    # Six peaks spread along a line, sharing a trailhead whose approach is
    # significant. The bare traverse fits in two trips, but once the walk-in is
    # counted each trip is over budget, so approach-aware splitting must use more.
    ths = [Trailhead("TH", 37.0, -118.30, 8000)]
    peaks = [Peak(f"s{i}", 37.0, -118.0 - 0.06 * i, 13000,
                  meta={"nearest_trailhead": "TH", "mileage_rt": 6.0, "gain_ft": 2000})
             for i in range(6)]
    common = dict(eps_mi=50, miles_per_day=12, max_days=1)
    off = plan_trips(peaks, ClusterConfig(include_approach=False, **common))
    on = plan_trips(peaks, ClusterConfig(include_approach=True, **common), trailheads=ths)
    assert len(on) > len(off)


def test_approach_aware_split_does_not_oversplit_when_approach_dominates():
    # Four peaks within a fraction of a mile of each other (near-zero traverse),
    # but a long approach that alone exceeds the budget. Splitting can't make any
    # trip fit -- it would only pay the approach more times -- so the planner must
    # keep the single inter-peak group rather than fragmenting.
    farth = [Trailhead("FarTH", 36.6, -118.0, 6000)]
    peaks = [Peak(f"t{i}", 37.0 + 0.003 * i, -118.0, 13000,
                  meta={"nearest_trailhead": "FarTH", "mileage_rt": 40.0, "gain_ft": 6000})
             for i in range(4)]
    common = dict(eps_mi=50, miles_per_day=15, max_days=2)
    off = plan_trips(peaks, ClusterConfig(include_approach=False, **common))
    on = plan_trips(peaks, ClusterConfig(include_approach=True, **common), trailheads=farth)
    assert len(on) == len(off) == 1
    # Sanity: the approach alone really does exceed the trip budget here.
    assert on[0].approach_effective_mi > common["miles_per_day"] * common["max_days"]


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
