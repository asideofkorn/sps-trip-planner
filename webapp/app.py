#!/usr/bin/env python3
"""Flask web app for the Sierra Peaks trip planner.

Wraps the clustering pipeline behind a small JSON API and serves an
interactive Leaflet map (``webapp/static/index.html``). Users adjust the trip
budget and grouping parameters in the browser; each change re-runs the planner
server-side and redraws the routes, peaks, and trailheads on a topo map.

Endpoints
---------
``GET /``                    the single-page map UI
``GET /api/plan``            run the planner with the given parameters -> JSON
``GET /api/weather``         NWS point forecast for a lat/lon (proxied)
``GET /api/meta``            dataset bounds + parameter ranges for the UI

Run::

    pip install flask           # plus the core deps in requirements.txt
    python webapp/app.py        # then open http://127.0.0.1:5000

The weather endpoint proxies the US National Weather Service API
(api.weather.gov, no key required) server-side so the browser avoids CORS and
we can set the required User-Agent. It degrades gracefully when offline.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sierra_peaks.data_loader import load_peaks, load_trailheads  # noqa: E402
from sierra_peaks.clustering import ClusterConfig  # noqa: E402
from sierra_peaks.pipeline import plan_trips  # noqa: E402
from sierra_peaks.export import clusters_to_payload  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PEAKS = ROOT / "data" / "sps_peaks.csv"
DEFAULT_TRAILHEADS = ROOT / "data" / "trailheads.csv"
DEFAULT_PASSES = ROOT / "data" / "passes.csv"

app = Flask(__name__, static_folder=None)

# ---------------------------------------------------------------------------
# Data is loaded once at startup and cached in module globals. The peak list is
# static; only the clustering parameters change per request.
# ---------------------------------------------------------------------------
_PEAKS = None
_TRAILHEADS = None


def _peaks():
    global _PEAKS
    if _PEAKS is None:
        _PEAKS = load_peaks(str(DEFAULT_PEAKS), list_filter="SPS")
    return _PEAKS


def _trailheads():
    global _TRAILHEADS
    if _TRAILHEADS is None:
        try:
            _TRAILHEADS = load_trailheads(str(DEFAULT_TRAILHEADS))
        except Exception:
            _TRAILHEADS = []
    return _TRAILHEADS


def _arg_float(name, default):
    try:
        return float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _arg_int(name, default):
    try:
        return int(float(request.args.get(name, default)))
    except (TypeError, ValueError):
        return default


def _arg_bool(name, default=False):
    val = request.args.get(name)
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/meta")
def api_meta():
    """Dataset bounds + the set of trailheads, for initializing the UI."""
    peaks = _peaks()
    lats = [p.latitude for p in peaks]
    lons = [p.longitude for p in peaks]
    ths = _trailheads()
    return jsonify({
        "num_peaks": len(peaks),
        "bounds": {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        },
        "elevation": {
            "min_ft": min(p.elevation_ft for p in peaks),
            "max_ft": max(p.elevation_ft for p in peaks),
        },
        "trailheads": [
            {
                "name": t.name, "latitude": t.latitude, "longitude": t.longitude,
                "elevation_ft": t.elevation_ft, "side": t.side, "notes": t.notes,
            }
            for t in ths
        ],
    })


@app.route("/api/plan")
def api_plan():
    """Run the planner with query parameters and return clusters as JSON."""
    include_approach = _arg_bool("include_approach", False)
    use_passes = _arg_bool("use_passes", False)
    exclude = [s.strip() for s in request.args.get("exclude", "").split(",") if s.strip()]

    config = ClusterConfig(
        eps_mi=_arg_float("eps_mi", 6.0),
        min_samples=_arg_int("min_samples", 1),
        miles_per_day=_arg_float("miles_per_day", 15.0),
        max_days=_arg_int("max_days", 3),
        method=request.args.get("method", "dbscan"),
        exclude=exclude,
        by_trailhead=_arg_bool("by_trailhead", False),
        trailhead_field=request.args.get("trailhead_field", "nearest_trailhead"),
        trailhead_max_mi=(_arg_float("trailhead_max_mi", 0) or None)
        if request.args.get("trailhead_max_mi") else None,
        include_approach=include_approach,
    )

    if use_passes:
        try:
            from sierra_peaks.passes import build_router
            config.router = build_router(
                str(DEFAULT_PASSES), candidate_tier=_arg_int("pass_tier", 1)
            )
        except Exception as exc:  # pragma: no cover - data/optional dep issues
            app.logger.warning("pass routing unavailable: %s", exc)

    trailheads = _trailheads() if include_approach else None
    clusters = plan_trips(_peaks(), config, trailheads)

    payload = clusters_to_payload(clusters, config)
    # Attach the full ordered peak geometry (lat/lon/elev/meta) per cluster so
    # the browser can draw routes and markers without a second request.
    for c, cd in zip(clusters, payload["clusters"]):
        cd["peaks_ordered"] = [
            {
                "name": p.name,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "elevation_ft": p.elevation_ft,
                "class": p.meta.get("class", ""),
                "section": p.meta.get("section", ""),
                "emblem": bool(p.meta.get("emblem")),
                "mountaineers": bool(p.meta.get("mountaineers")),
                "mileage_rt": p.meta.get("mileage_rt"),
                "gain_ft": p.meta.get("gain_ft"),
                "nearest_trailhead": p.meta.get("nearest_trailhead"),
            }
            for p in c.peaks
        ]
    return jsonify(payload)


# Cache point->forecast-url lookups so we hit /points only once per location.
_WX_CACHE: dict = {}
_NWS_HEADERS = {
    "User-Agent": "sps-trip-planner (https://github.com/asideofkorn/sps-trip-planner)",
    "Accept": "application/geo+json",
}


def _nws_get(url):
    req = urllib.request.Request(url, headers=_NWS_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


@app.route("/api/weather")
def api_weather():
    """Proxy a National Weather Service point forecast for lat/lon (US only)."""
    lat = _arg_float("lat", None)
    lon = _arg_float("lon", None)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required"}), 400

    key = f"{lat:.4f},{lon:.4f}"
    try:
        forecast_url = _WX_CACHE.get(key)
        if forecast_url is None:
            point = _nws_get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
            forecast_url = point["properties"]["forecast"]
            _WX_CACHE[key] = forecast_url
        data = _nws_get(forecast_url)
        periods = data["properties"]["periods"][:8]
        return jsonify({
            "source": "NWS api.weather.gov",
            "periods": [
                {
                    "name": p.get("name"),
                    "temperature": p.get("temperature"),
                    "temperatureUnit": p.get("temperatureUnit"),
                    "windSpeed": p.get("windSpeed"),
                    "windDirection": p.get("windDirection"),
                    "shortForecast": p.get("shortForecast"),
                    "detailedForecast": p.get("detailedForecast"),
                    "isDaytime": p.get("isDaytime"),
                    "icon": p.get("icon"),
                }
                for p in periods
            ],
        })
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
        return jsonify({
            "error": "forecast unavailable",
            "detail": str(exc),
        }), 502


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Sierra Peaks trip planner web app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
