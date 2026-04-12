"""
Generate comparison graphs for ridesharing pipeline experiments.
Data sourced from experiments/comparison_table.py
"""

import sys
import os

# Allow importing comparison_table from the same directory
sys.path.insert(0, os.path.dirname(__file__))
from comparison_table import experiments

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import seaborn as sns

plt.style.use("dark_background")

OUT = os.path.join(os.path.dirname(__file__), "graphs")
os.makedirs(OUT, exist_ok=True)

# ── Shared data ────────────────────────────────────────────────────────────────
keys   = ["Scale1-Laptop", "Scale1-EC2", "Scale2-EC2", "Scale3-EMR"]
labels = ["Scale1-Laptop", "Scale1-EC2", "Scale2-EC2", "Scale3-EMR"]
colors = ["#4C9BE8", "#4CAF50", "#FF9800", "#E040FB"]   # blue, green, orange, purple

eps  = [experiments[k]["kafka_eps_avg"]    for k in keys]
lavg = [experiments[k]["latency_avg_ms"] / 1000 for k in keys]
lp95 = [experiments[k]["latency_p95_ms"] / 1000 for k in keys]
savg = [experiments[k]["surge_zones_avg"] for k in keys]
smax = [experiments[k]["surge_zones_max"] for k in keys]
cost = [experiments[k]["cost_per_hr"]     for k in keys]
wait = [experiments[k]["waiting_riders"]  for k in keys]

x = np.arange(len(keys))

# ── Helper ─────────────────────────────────────────────────────────────────────
def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved → {path}")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 1 — Throughput Comparison
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 5))

bars = ax.bar(x, eps, color=colors, width=0.55, edgecolor="white", linewidth=0.6, zorder=3)

ax.axhline(1000, color="red", linestyle="--", linewidth=1.5, label="SLA: 1000 EPS", zorder=4)

for bar, val in zip(bars, eps):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 30,
            f"{val:.0f}", ha="center", va="bottom", fontsize=11, fontweight="bold", color="white")

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=11)
ax.set_ylabel("Kafka EPS (events / second)", fontsize=11)
ax.set_title("Kafka Throughput Comparison Across Scales", fontsize=14, fontweight="bold", pad=14)
ax.set_ylim(0, max(eps) * 1.22)
ax.legend(fontsize=10)
ax.grid(axis="y", alpha=0.25, zorder=0)
sns.despine(ax=ax, left=False, bottom=False)

save(fig, "throughput_comparison.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 2 — Latency Comparison
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5))

w = 0.35
bars_avg = ax.bar(x - w / 2, lavg, width=w, color="#4C9BE8", label="Avg E2E",
                  edgecolor="white", linewidth=0.6, zorder=3)
bars_p95 = ax.bar(x + w / 2, lp95, width=w, color="#FF9800", label="P95",
                  edgecolor="white", linewidth=0.6, zorder=3)

ax.axhline(60, color="red", linestyle="--", linewidth=1.5, label="SLA: 60s", zorder=4)

for bar, val in zip(bars_avg, lavg):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
            f"{val:.1f}s", ha="center", va="bottom", fontsize=9, color="white")
for bar, val in zip(bars_p95, lp95):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
            f"{val:.1f}s", ha="center", va="bottom", fontsize=9, color="white")

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=11)
ax.set_ylabel("Latency (seconds)", fontsize=11)
ax.set_title("End-to-End Latency Comparison", fontsize=14, fontweight="bold", pad=14)
ax.set_ylim(0, max(max(lavg), max(lp95)) * 1.22)
ax.legend(fontsize=10)
ax.grid(axis="y", alpha=0.25, zorder=0)
sns.despine(ax=ax, left=False, bottom=False)

save(fig, "latency_comparison.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 3 — Surge Zones
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 5))

ax.plot(labels, savg, color="#4C9BE8", marker="o", markersize=8, linewidth=2,
        linestyle="-",  label="Avg surge zones", zorder=3)
ax.plot(labels, smax, color="#FF6B6B", marker="s", markersize=8, linewidth=2,
        linestyle="--", label="Max surge zones", zorder=3)

for i, (av, mx) in enumerate(zip(savg, smax)):
    ax.text(i, av + 1.5, f"{av:.0f}", ha="center", va="bottom", fontsize=10, color="#4C9BE8")
    ax.text(i, mx + 1.5, f"{mx:.0f}", ha="center", va="bottom", fontsize=10, color="#FF6B6B")

ax.set_ylabel("Active Surge Zones", fontsize=11)
ax.set_title("Active Surge Zones Across Scales", fontsize=14, fontweight="bold", pad=14)
ax.set_ylim(0, max(smax) * 1.25)
ax.legend(fontsize=10)
ax.grid(alpha=0.25, zorder=0)
sns.despine(ax=ax, left=False, bottom=False)

save(fig, "surge_zones.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 4 — Cost vs Latency
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 6))

point_colors = colors

offsets = [(-0.025, 4), (0.008, 4), (0.008, -12), (0.008, 8)]
for i, (lbl, c, h, la) in enumerate(zip(labels, cost, lavg, point_colors)):
    ax.scatter(c, h, s=220, color=la, edgecolors="white", linewidths=1.2, zorder=4)
    ox, oy = offsets[i]
    ax.annotate(lbl, (c, h), xytext=(c + ox, h + oy),
                fontsize=10, fontweight="bold", color="white",
                arrowprops=dict(arrowstyle="-", color="gray", lw=0.8))

ax.set_xlabel("Cost per Hour ($)", fontsize=11)
ax.set_ylabel("Avg E2E Latency (seconds)", fontsize=11)
ax.set_title("Cost vs Latency Trade-off", fontsize=14, fontweight="bold", pad=14)
ax.grid(alpha=0.25, zorder=0)
ax.set_xlim(-0.10, max(cost) * 1.15)
ax.set_ylim(-20, max(lavg) * 1.3)
sns.despine(ax=ax, left=False, bottom=False)

save(fig, "cost_vs_latency.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 6 — Infrastructure Scaling: Throughput vs Latency
# ══════════════════════════════════════════════════════════════════════════════
fig, ax1 = plt.subplots(figsize=(10, 6))

infra_labels = ["Scale1-Laptop", "Scale1-EC2", "Scale2-EC2", "Scale3-EMR"]
infra_eps    = [experiments[k]["kafka_eps_avg"]        for k in infra_labels]
infra_lavg   = [experiments[k]["latency_avg_ms"] / 1000 for k in infra_labels]
infra_colors = ["#4C9BE8", "#4CAF50", "#FF9800", "#E040FB"]
xi = np.arange(len(infra_labels))

# Bar chart — EPS (left y-axis)
bars = ax1.bar(xi, infra_eps, color=infra_colors, width=0.5,
               edgecolor="white", linewidth=0.6, alpha=0.85, zorder=3)
ax1.set_ylabel("Kafka EPS (events / second)", fontsize=11, color="#4C9BE8")
ax1.tick_params(axis="y", labelcolor="#4C9BE8")
ax1.set_xticks(xi)
ax1.set_xticklabels(infra_labels, fontsize=11)
ax1.set_ylim(0, max(infra_eps) * 1.35)
ax1.grid(axis="y", alpha=0.2, zorder=0)

for bar, val in zip(bars, infra_eps):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 40,
             f"{val:.0f}", ha="center", va="bottom", fontsize=10,
             fontweight="bold", color="white")

# Line chart — Avg Latency (right y-axis)
ax2 = ax1.twinx()
ax2.plot(xi, infra_lavg, color="#FF4444", marker="o", markersize=9,
         linewidth=2.5, linestyle="-", label="Avg Latency (s)", zorder=4)
ax2.set_ylabel("Avg E2E Latency (seconds)", fontsize=11, color="#FF4444")
ax2.tick_params(axis="y", labelcolor="#FF4444")
ax2.set_ylim(0, max(infra_lavg) * 1.35)

for i, val in enumerate(infra_lavg):
    ax2.text(xi[i] + 0.18, val + 4, f"{val:.1f}s",
             ha="left", va="bottom", fontsize=9, color="#FF4444")

# Annotation: 4.5× latency improvement EC2 vs Laptop
laptop_lat = experiments["Scale1-Laptop"]["latency_avg_ms"] / 1000
ec2_lat    = experiments["Scale1-EC2"]["latency_avg_ms"] / 1000
improvement = round(laptop_lat / ec2_lat, 1)
ax2.annotate(
    f"{improvement}× latency improvement\nEC2 vs Laptop",
    xy=(1, ec2_lat), xytext=(1.25, ec2_lat + 50),
    fontsize=9, color="white",
    arrowprops=dict(arrowstyle="->", color="white", lw=1.2),
    bbox=dict(boxstyle="round,pad=0.3", facecolor="#333333", edgecolor="white", alpha=0.8),
)

ax1.set_title("Infrastructure Scaling: Throughput vs Latency",
              fontsize=14, fontweight="bold", pad=14)

# Combined legend
bar_patch = mpatches.Patch(color="#4C9BE8", label="Kafka EPS (bars)")
line_patch = mpatches.Patch(color="#FF4444", label="Avg Latency (line)")
ax1.legend(handles=[bar_patch, line_patch], fontsize=10, loc="upper left")

sns.despine(ax=ax1, left=False, bottom=False)
fig.tight_layout()
save(fig, "infrastructure_scaling.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 5 — Dashboard (2×2)
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.suptitle("Ridesharing Pipeline — Scale Comparison Dashboard",
             fontsize=16, fontweight="bold", y=1.01)

# ── Subplot 1: Throughput ──────────────────────────────────────────
ax1 = axes[0, 0]
b1 = ax1.bar(x, eps, color=colors, width=0.55, edgecolor="white", linewidth=0.5, zorder=3)
ax1.axhline(1000, color="red", linestyle="--", linewidth=1.3, label="SLA 1000 EPS")
for bar, val in zip(b1, eps):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
             f"{val:.0f}", ha="center", va="bottom", fontsize=9, color="white")
ax1.set_xticks(x); ax1.set_xticklabels(labels, fontsize=9)
ax1.set_ylabel("EPS"); ax1.set_title("Throughput (Kafka EPS)", fontweight="bold")
ax1.set_ylim(0, max(eps) * 1.25); ax1.legend(fontsize=8); ax1.grid(axis="y", alpha=0.2)

# ── Subplot 2: Latency ─────────────────────────────────────────────
ax2 = axes[0, 1]
b2a = ax2.bar(x - 0.2, lavg, width=0.38, color="#4C9BE8", label="Avg", edgecolor="white", linewidth=0.5, zorder=3)
b2p = ax2.bar(x + 0.2, lp95, width=0.38, color="#FF9800", label="P95", edgecolor="white", linewidth=0.5, zorder=3)
ax2.axhline(60, color="red", linestyle="--", linewidth=1.3, label="SLA 60s")
for bar, val in zip(b2a, lavg):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             f"{val:.0f}s", ha="center", va="bottom", fontsize=8, color="white")
for bar, val in zip(b2p, lp95):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             f"{val:.0f}s", ha="center", va="bottom", fontsize=8, color="white")
ax2.set_xticks(x); ax2.set_xticklabels(labels, fontsize=9)
ax2.set_ylabel("Seconds"); ax2.set_title("End-to-End Latency", fontweight="bold")
ax2.set_ylim(0, max(max(lavg), max(lp95)) * 1.28); ax2.legend(fontsize=8); ax2.grid(axis="y", alpha=0.2)

# ── Subplot 3: Surge Zones ─────────────────────────────────────────
ax3 = axes[1, 0]
ax3.plot(labels, savg, color="#4C9BE8", marker="o", markersize=7, linewidth=2,
         linestyle="-",  label="Avg", zorder=3)
ax3.plot(labels, smax, color="#FF6B6B", marker="s", markersize=7, linewidth=2,
         linestyle="--", label="Max", zorder=3)
for i, (av, mx) in enumerate(zip(savg, smax)):
    ax3.text(i, av + 1, f"{av:.0f}", ha="center", va="bottom", fontsize=9, color="#4C9BE8")
    ax3.text(i, mx + 1, f"{mx:.0f}", ha="center", va="bottom", fontsize=9, color="#FF6B6B")
ax3.set_ylabel("Active Surge Zones"); ax3.set_title("Surge Zone Detection", fontweight="bold")
ax3.set_ylim(0, max(smax) * 1.3); ax3.legend(fontsize=8); ax3.grid(alpha=0.2)

# ── Subplot 4: Waiting Riders ──────────────────────────────────────
ax4 = axes[1, 1]
b4 = ax4.bar(x, wait, color=colors, width=0.55, edgecolor="white", linewidth=0.5, zorder=3)
for bar, val in zip(b4, wait):
    ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 30,
             f"{val:,.0f}", ha="center", va="bottom", fontsize=9, color="white")
ax4.set_xticks(x); ax4.set_xticklabels(labels, fontsize=9)
ax4.set_ylabel("Waiting Riders"); ax4.set_title("Waiting Riders per Batch", fontweight="bold")
ax4.set_ylim(0, max(wait) * 1.25); ax4.grid(axis="y", alpha=0.2)

for ax in axes.flat:
    sns.despine(ax=ax, left=False, bottom=False)

plt.tight_layout()
save(fig, "dashboard.png")

print("\nAll 6 graphs generated successfully.")
