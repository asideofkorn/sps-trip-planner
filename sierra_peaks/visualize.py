"""Optional matplotlib visualization of clustered peaks and TSP routes.

Import is lazy so the rest of the toolkit works without matplotlib installed.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .model import Cluster


def plot_clusters(
    clusters: Sequence[Cluster],
    output_path: Optional[str] = None,
    show: bool = False,
    label_peaks: Optional[bool] = None,
):
    """Scatter peaks colored by cluster and draw each TSP route.

    ``label_peaks`` controls per-peak name labels; when ``None`` they are shown
    only for small plots (<= 40 peaks) to avoid clutter on statewide maps.
    Returns the matplotlib Figure. Raises ImportError if matplotlib is missing.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "matplotlib is required for visualization. Install with "
            "`pip install matplotlib`."
        ) from exc

    total_peaks = sum(c.num_peaks for c in clusters)
    if label_peaks is None:
        label_peaks = total_peaks <= 40

    fig, ax = plt.subplots(figsize=(11, 13))
    cmap = plt.get_cmap("tab20")

    for c in clusters:
        color = cmap(c.cluster_id % 20)
        lons = [p.longitude for p in c.peaks]
        lats = [p.latitude for p in c.peaks]
        # Route line follows the TSP order (peaks are already stored in order).
        if len(c.peaks) > 1:
            ax.plot(lons, lats, "-", color=color, linewidth=1.5, alpha=0.7, zorder=1)
        ax.scatter(lons, lats, color=color, s=60, edgecolors="k", zorder=2)
        if label_peaks:
            for p in c.peaks:
                ax.annotate(
                    p.name,
                    (p.longitude, p.latitude),
                    fontsize=6,
                    xytext=(3, 3),
                    textcoords="offset points",
                )
        # Label the cluster near its centroid.
        ax.annotate(
            f"#{c.cluster_id} ({c.num_peaks}pk / {c.estimated_days}d)",
            (sum(lons) / len(lons), sum(lats) / len(lats)),
            fontsize=8,
            fontweight="bold",
            color=color,
        )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Sierra Peaks clusters & recommended TSP routes")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150)
    if show:  # pragma: no cover
        plt.show()
    return fig
