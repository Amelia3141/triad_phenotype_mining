"""
Plot accuracy over the 50-disease experiment, showing how generalisable fixes
improved config-generation accuracy over time.

Reads version_traj.json (from compare_versions.py) and writes:
  accuracy_over_iterations.png
  accuracy_over_iterations.csv

Usage:
    python -m nlp_pipeline_v2.experiments.make_plot version_traj.json out_dir
"""

import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Iteration at which each generalisable fix was introduced during the run.
FIX_POINTS = [
    (15, "Robust candidate\nselection", "V1"),
    (25, "Pattern-quality\nfixes", "V2"),
    (42, "Null-safe\nAPI parsing", None),
]


def active_version(i):
    if i < 15:
        return "V0"
    if i < 25:
        return "V1"
    return "V2"


def main():
    traj_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/version_traj.json"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(__file__)
    rows = json.load(open(traj_path))
    rows.sort(key=lambda r: r["index"])

    x = [r["index"] + 1 for r in rows]
    v0 = [r["V0"] for r in rows]
    v2 = [r["V2"] for r in rows]
    # As-fixed-over-time trajectory: each disease scored under the code version
    # live when the run reached it.
    traj = [r[active_version(r["index"])] for r in rows]
    run_mean = [sum(traj[: i + 1]) / (i + 1) for i in range(len(traj))]

    v0_mean = sum(v0) / len(v0)
    v2_mean = sum(v2) / len(v2)

    # ── Write CSV ──
    csv_path = os.path.join(out_dir, "accuracy_over_iterations.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["iteration", "disease", "baseline_V0", "as_fixed_trajectory",
                    "final_V2", "running_mean_trajectory", "active_version"])
        for i, r in enumerate(rows):
            w.writerow([r["index"] + 1, r["name"], f"{v0[i]:.2f}", f"{traj[i]:.2f}",
                        f"{v2[i]:.2f}", f"{run_mean[i]:.2f}", active_version(r["index"])])

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(13, 6.5))

    ax.plot(x, v0, color="#c0392b", lw=1, alpha=0.5, marker="o", ms=3,
            label="Original code (baseline)")
    ax.plot(x, traj, color="#27ae60", lw=1.4, alpha=0.85, marker="o", ms=3.5,
            label="Pipeline as fixes were applied")
    ax.plot(x, run_mean, color="#16a085", lw=3, label="Running mean (as-fixed)")

    ax.axhline(v0_mean, ls=":", color="#c0392b", alpha=0.7,
               label=f"Baseline mean = {v0_mean:.1f}%")
    ax.axhline(v2_mean, ls=":", color="#27ae60", alpha=0.7,
               label=f"Final mean = {v2_mean:.1f}%")

    for it, label, _ in FIX_POINTS:
        ax.axvline(it + 0.5, ls="--", color="#34495e", alpha=0.55, lw=1.2)
        ax.annotate(label, xy=(it + 0.5, 12), xytext=(it + 0.8, 12),
                    fontsize=8.5, color="#34495e", rotation=0, va="bottom")

    ax.set_xlabel("Iteration (disease #)")
    ax.set_ylabel("Config-generation accuracy (%)")
    ax.set_title("Disease config-generator accuracy over 50 diseases\n"
                 "(self-match recall + intra-config specificity + control specificity)")
    ax.set_ylim(0, 104)
    ax.set_xlim(0.5, len(x) + 0.5)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower right", fontsize=8.5, ncol=2)

    fig.tight_layout()
    png_path = os.path.join(out_dir, "accuracy_over_iterations.png")
    fig.savefig(png_path, dpi=150)
    print(f"saved -> {png_path}")
    print(f"saved -> {csv_path}")
    print(f"baseline mean={v0_mean:.2f}%  final mean={v2_mean:.2f}%  "
          f"final running-mean={run_mean[-1]:.2f}%")


if __name__ == "__main__":
    main()
