"""Tests for sierra_peaks.trails (OSM-derived trail-network routing).

Entirely network-free: every test builds a small synthetic networkx.Graph by
hand rather than depending on the real committed data/trails.graphml, which is
fetched offline by scripts/fetch_osm_trails.py and is not required to run
these tests (see that script's docstring).

Run with:  python -m pytest tests/  (or)  python tests/test_trails.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx

from sierra_peaks.model import Peak, Trailhead
from sierra_peaks.distances import haversine_miles, naismith_effective_miles
from sierra_peaks.tsp import route_metrics
from sierra_peaks.approach import approach_leg
from sierra_peaks.clustering import ClusterConfig
from sierra_peaks.pipeline import plan_trips
from sierra_peaks.data_loader import load_peaks

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "sps_sample.csv")


def _synthetic_trail_graph():
    """A small "Y"-shaped trail: n0 (trailhead end) -- n1 (fork) -- {n2, n3}
    (two branch ends), plus a disconnected pair {n4, n5} to exercise the
    no-path fallback.
    """
    from sierra_peaks.trails import TrailRouter

    coords = {
        "n0": (37.000, -118.500),
        "n1": (37.010, -118.480),
        "n2": (37.020, -118.460),
        "n3": (37.005, -118.460),
        "n4": (38.500, -119.500),
        "n5": (38.505, -119.505),
    }
    g = nx.Graph()
    for node, (lat, lon) in coords.items():
        g.add_node(node, y=lat, x=lon)

    def add_edge(a, b):
        lat_a, lon_a = coords[a]
        lat_b, lon_b = coords[b]
        g.add_edge(a, b, length_mi=haversine_miles(lat_a, lon_a, lat_b, lon_b))

    add_edge("n0", "n1")
    add_edge("n1", "n2")
    add_edge("n1", "n3")
    add_edge("n4", "n5")
    return g, coords


def _router():
    from sierra_peaks.trails import TrailRouter

    graph, _ = _synthetic_trail_graph()
    return TrailRouter(graph, max_snap_mi=1.5)


def test_nearest_node_snaps_to_closest():
    router = _router()
    node, snap_mi = router.nearest_node(37.0201, -118.4601)  # just off n2
    assert node == "n2"
    assert snap_mi < 0.1


def test_router_leg_uses_trail_path_when_both_endpoints_near_trail():
    router = _router()
    peak_a = Peak("A", 37.0205, -118.4605, 13000)  # near n2
    peak_b = Peak("B", 37.0055, -118.4605, 12500)  # near n3

    node_a, snap_a = router.nearest_node(peak_a.latitude, peak_a.longitude)
    node_b, snap_b = router.nearest_node(peak_b.latitude, peak_b.longitude)
    assert node_a == "n2" and node_b == "n3"
    on_trail_mi = nx.shortest_path_length(router.graph, node_a, node_b,
                                          weight="length_mi")
    expected = snap_a + on_trail_mi + snap_b

    leg = router.leg(peak_a, peak_b)
    assert leg.on_trail
    assert math.isclose(leg.horizontal_mi, expected, rel_tol=1e-9)
    asc = max(0.0, peak_b.elevation_ft - peak_a.elevation_ft)
    assert math.isclose(leg.effective_mi,
                        naismith_effective_miles(leg.horizontal_mi, asc), rel_tol=1e-9)


def test_router_leg_falls_back_when_peak_far_from_trail():
    router = _router()
    near = Peak("near", 37.0205, -118.4605, 13000)   # near n2
    far = Peak("far", 40.0, -120.0, 12000)            # nowhere near the graph

    leg = router.leg(near, far)
    assert not leg.on_trail
    h = haversine_miles(near.latitude, near.longitude, far.latitude, far.longitude)
    asc = max(0.0, far.elevation_ft - near.elevation_ft)
    assert math.isclose(leg.horizontal_mi, h, rel_tol=1e-9)
    assert math.isclose(leg.effective_mi, naismith_effective_miles(h, asc), rel_tol=1e-9)


def test_router_leg_falls_back_when_no_path_exists():
    router = _router()
    a = Peak("a", 37.0205, -118.4605, 13000)   # snaps to n2 (main component)
    b = Peak("b", 38.5005, -119.5005, 12000)   # snaps to n4 (disconnected component)

    node_a, snap_a = router.nearest_node(a.latitude, a.longitude)
    node_b, snap_b = router.nearest_node(b.latitude, b.longitude)
    assert node_a == "n2" and node_b == "n4"
    assert snap_a <= router.max_snap_mi and snap_b <= router.max_snap_mi

    leg = router.leg(a, b)
    assert not leg.on_trail
    h = haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude)
    assert math.isclose(leg.horizontal_mi, h, rel_tol=1e-9)


def test_route_metrics_tolerates_router_without_via_pass():
    router = _router()
    peaks = [
        Peak("A", 37.0205, -118.4605, 13000),
        Peak("B", 37.0055, -118.4605, 12500),
    ]
    metrics = route_metrics(peaks, router=router)  # must not raise AttributeError
    assert metrics["passes"] == []
    assert metrics["horizontal_mi"] > 0


def test_approach_leg_uses_router_when_no_official_mileage():
    router = _router()
    trailhead = Trailhead("TH", 37.000, -118.500, 8000.0)  # at n0
    peak = Peak("A", 37.0205, -118.4605, 13000)             # no meta at all

    dist, ascent = approach_leg(trailhead, peak, router=router)
    expected = router.leg(trailhead, peak, by="effective")
    assert math.isclose(dist, expected.horizontal_mi, rel_tol=1e-9)
    assert math.isclose(ascent, expected.ascent_ft, rel_tol=1e-9)


def test_load_trail_graph_graphml_roundtrip(tmp_path):
    from sierra_peaks.trails import load_trail_graph

    graph, _ = _synthetic_trail_graph()
    out = tmp_path / "trails.graphml"
    nx.write_graphml(graph, out)

    loaded = load_trail_graph(out)
    assert loaded.number_of_nodes() == graph.number_of_nodes()
    assert loaded.number_of_edges() == graph.number_of_edges()
    # GraphML round-trips attributes as strings unless explicitly cast back;
    # load_trail_graph must hand back real floats.
    assert isinstance(loaded.nodes["n0"]["y"], float)
    n0n1 = loaded["n0"]["n1"]
    assert isinstance(n0n1["length_mi"], float)
    assert math.isclose(n0n1["length_mi"], graph["n0"]["n1"]["length_mi"], rel_tol=1e-6)


def test_load_trail_graph_missing_file_raises(tmp_path):
    from sierra_peaks.trails import load_trail_graph

    try:
        load_trail_graph(tmp_path / "does_not_exist.graphml")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_pipeline_with_trail_router_partitions_and_budgets():
    from sierra_peaks.trails import TrailRouter

    peaks = load_peaks(DATA)
    graph, _ = _synthetic_trail_graph()
    router = TrailRouter(graph, max_snap_mi=1.5)
    config = ClusterConfig(eps_mi=6.0, miles_per_day=15.0, max_days=3, router=router)
    clusters = plan_trips(peaks, config)
    names = [n for c in clusters for n in c.peak_names]
    assert sorted(names) == sorted(p.name for p in peaks)
    for c in clusters:
        assert c.total_effective_mi <= config.max_effective_mi + 1e-6
        # None of the sample peaks are near the tiny synthetic graph, so every
        # leg should fall back -- this must behave identically to no router.
        assert c.route_source in ("", "trails")


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
