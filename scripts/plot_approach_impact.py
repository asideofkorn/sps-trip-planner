import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sierra_peaks import load_peaks, load_trailheads, ClusterConfig, plan_trips
from sierra_peaks.approach import choose_trailhead

peaks = load_peaks("data/sps_peaks.csv", list_filter="SPS")
ths = load_trailheads("data/trailheads.csv")
cfg = ClusterConfig(max_days=2, include_approach=True)
clusters = plan_trips(peaks, cfg, trailheads=ths)

# ---- Panel A: inter-peak vs approach effective miles, top 15 trips by peaks ----
top = sorted(clusters, key=lambda c: c.num_peaks, reverse=True)[:15]
top = sorted(top, key=lambda c: c.total_effective_mi)
labels = [f"{c.num_peaks}pk  {c.trailhead[:18]}" for c in top]
interpeak = [c.total_effective_mi - c.approach_effective_mi for c in top]
approach = [c.approach_effective_mi for c in top]

fig, (axA, axB) = plt.subplots(1, 2, figsize=(17, 8))

y = range(len(top))
axA.barh(y, interpeak, color="#3b7dd8", label="inter-peak (traverse)")
axA.barh(y, approach, left=interpeak, color="#e8743b", label="trailhead approach")
axA.set_yticks(list(y)); axA.set_yticks(list(y), labels)
axA.set_xlabel("effective miles (Naismith)")
axA.set_title("Where the effort goes: traverse vs. approach\n(top 15 trips by peak count, --include-approach)")
axA.legend(loc="lower right")
for i, c in enumerate(top):
    pct = 100 * c.approach_effective_mi / c.total_effective_mi
    axA.text(c.total_effective_mi + 0.3, i, f"{pct:.0f}% approach", va="center", fontsize=8, color="#555")
axA.margins(x=0.12)

# ---- Panel B: map of the Palisades cluster with trailhead + in/out legs ----
pal = max(clusters, key=lambda c: sum(1 for p in c.peaks if "Palisade" in p.name or p.name in
          {"Mount Sill","Norman Clyde Peak","Mount Gayley","Temple Crag"}))
th = choose_trailhead(pal.peaks, ths)
ordered = pal.peaks  # already in route order
xs = [p.longitude for p in ordered]; ys = [p.latitude for p in ordered]
axB.plot(xs, ys, "-o", color="#3b7dd8", zorder=3)
for p in ordered:
    axB.annotate(p.name, (p.longitude, p.latitude), fontsize=7,
                 xytext=(3,3), textcoords="offset points")
# trailhead + approach legs (dashed) to entry & exit
axB.plot(th.longitude, th.latitude, "*", color="#e8743b", markersize=22, zorder=4)
axB.annotate(f"TH: {th.name}", (th.longitude, th.latitude), fontsize=9, color="#b8460f",
             fontweight="bold", xytext=(5,-12), textcoords="offset points")
for end in (ordered[0], ordered[-1]):
    axB.plot([th.longitude, end.longitude], [th.latitude, end.latitude],
             "--", color="#e8743b", zorder=2)
axB.set_title(f"Palisades trip re-anchored to its trailhead\n"
              f"{pal.num_peaks} peaks | {pal.total_effective_mi:.1f} eff mi "
              f"({pal.approach_effective_mi:.1f} approach) | {pal.estimated_days} days")
axB.set_xlabel("longitude"); axB.set_ylabel("latitude")
axB.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("examples/approach_impact.png", dpi=300)
print("entry:", ordered[0].name, "| exit:", ordered[-1].name, "| TH:", th.name)
print("saved examples/approach_impact.png")
