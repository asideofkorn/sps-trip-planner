"""Plot the SPS benchmark routes as a difficulty progression.

Produces two charts under ``charts/``:
  * a difficulty ladder (S-1.0 -> S-4.2), one marker per benchmark route, so a
    peak with multiple routes (e.g. Mount Whitney) shows up at each rating;
  * a geographic map of the benchmark peaks, coloured by YDS class.

Usage:
    python scripts/plot_benchmarks.py [YYYY-MM-DD]
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "data" / "benchmark_routes.csv"
CHARTS = ROOT / "charts"

# YDS class -> colour (green easy ... red hard).
CLASS_COLOR = {1: "#2ca02c", 2: "#1f77b4", 3: "#ff7f0e", 4: "#d62728"}


def class_num(val) -> int:
    """'3s4' / '3' / 3 -> leading integer for colour binning."""
    return int(str(val)[0])


def flag_tag(row) -> str:
    tags = []
    if row["emblem"]:
        tags.append("E")
    if row["mountaineering"]:
        tags.append("M")
    return f" [{'/'.join(tags)}]" if tags else ""


def plot_ladder(df: pd.DataFrame, stamp: str) -> Path:
    ratings = sorted(df["scrambler_rating"].unique())
    x_of = {r: i for i, r in enumerate(ratings)}

    fig, ax = plt.subplots(figsize=(16, 7))
    for rating, grp in df.groupby("scrambler_rating"):
        grp = grp.reset_index(drop=True)
        for j, row in grp.iterrows():
            x = x_of[rating]
            y = j
            c = CLASS_COLOR[class_num(row["ydc_class"])]
            ax.scatter(x, y, s=90, color=c, zorder=3, edgecolor="k", linewidth=0.4)
            ax.annotate(f"{row['peak']}{flag_tag(row)}", (x, y),
                        xytext=(0, 11), textcoords="offset points",
                        ha="center", fontsize=7, rotation=12)

    ax.set_xticks(range(len(ratings)))
    ax.set_xticklabels(ratings)
    ax.set_yticks([])
    ax.set_ylim(-0.6, df.groupby("scrambler_rating").size().max() - 0.2)
    ax.set_xlabel("Scrambler rating  (easier  ->  harder)")
    ax.set_title("SPS Benchmark Routes — difficulty progression ladder")
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", markersize=9,
                          markerfacecolor=CLASS_COLOR[k], markeredgecolor="k",
                          label=f"Class {k}") for k in sorted(CLASS_COLOR)]
    handles.append(plt.Line2D([0], [0], linestyle="", label="E=Emblem  M=Mountaineering"))
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    out = CHARTS / f"benchmark_progression_ladder_{stamp}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_map(df: pd.DataFrame, stamp: str) -> Path:
    # One point per peak; use the easiest rating for the label.
    per_peak = (df.sort_values("scrambler_rating")
                  .groupby("sps_name", as_index=False).first())
    fig, ax = plt.subplots(figsize=(9, 11))
    for _, row in per_peak.iterrows():
        c = CLASS_COLOR[class_num(row["ydc_class"])]
        ax.scatter(row["longitude"], row["latitude"], s=80, color=c,
                   edgecolor="k", linewidth=0.4, zorder=3)
        ax.annotate(f"{row['peak']} ({row['scrambler_rating']})",
                    (row["longitude"], row["latitude"]),
                    xytext=(4, 3), textcoords="offset points", fontsize=7)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("SPS Benchmark Peaks — location & easiest benchmark rating")
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", markersize=9,
                          markerfacecolor=CLASS_COLOR[k], markeredgecolor="k",
                          label=f"Class {k}") for k in sorted(CLASS_COLOR)]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    ax.grid(linestyle=":", alpha=0.5)
    fig.tight_layout()
    out = CHARTS / f"benchmark_peaks_map_{stamp}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main() -> None:
    stamp = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    CHARTS.mkdir(exist_ok=True)
    df = pd.read_csv(ROUTES)
    p1 = plot_ladder(df, stamp)
    p2 = plot_map(df, stamp)
    print("Wrote", p1.relative_to(ROOT))
    print("Wrote", p2.relative_to(ROOT))


if __name__ == "__main__":
    main()
