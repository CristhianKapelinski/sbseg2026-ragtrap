"""Generate the paper's results figures from results/*.json.

Reads the canonical experiment outputs and emits a publication-ready PDF. Every plotted
value comes from a JSON file; nothing is recomputed or hardcoded here beyond
selecting and formatting. Run after the experiments, before compiling the paper:

    python scripts/make_figures.py [--out PATH]

The default output is ``results/results_panels.pdf``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

# Shared style: each panel renders at ~half \columnwidth, so use a compact
# short aspect ratio that reads well when scaled to 0.49\columnwidth.
FIGSIZE = (3.3, 2.4)
plt.rcParams.update(
    {
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.3,
        "lines.markersize": 4,
        "figure.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,
    }
)


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def fig_drift(real: dict, ax) -> None:
    """Traceback recall vs post-ingestion provenance-loss/drift fraction p."""
    rt = real["ragtrap"]
    order = [("drift_0", 0.0), ("drift_0.3", 0.3), ("drift_0.5", 0.5)]
    xs, ys, lo, hi = [], [], [], []
    for key, p in order:
        rec = rt[key]["detection"]["recall"]
        xs.append(p)
        ys.append(rec["point"])
        # asymmetric Wilson half-widths; clamp tiny float noise at the p=0 ceiling
        lo.append(max(0.0, rec["point"] - rec["ci_low"]))
        hi.append(max(0.0, rec["ci_high"] - rec["point"]))

    ax.errorbar(
        xs,
        ys,
        yerr=[lo, hi],
        marker="o",
        color="#1f3b73",
        ecolor="#1f3b73",
        elinewidth=0.9,
        capsize=2.5,
        capthick=0.9,
    )
    # annotate each point so every label stays fully inside the axes: the
    # rightmost point's label goes to its LEFT (right-aligned) and above so it
    # cannot spill past the right frame; the p=0 ceiling label sits below-right;
    # interior labels go above-right.
    last = len(xs) - 1
    for i, (x, y) in enumerate(zip(xs, ys, strict=False)):
        if i == last:
            xoff, yoff, ha = -7, 8, "right"
        elif y > 0.95:
            xoff, yoff, ha = 7, -12, "left"
        else:
            xoff, yoff, ha = 7, 7, "left"
        ax.annotate(
            f"{y:.2f}",
            (x, y),
            textcoords="offset points",
            xytext=(xoff, yoff),
            ha=ha,
            fontsize=8,
        )
    ax.set_xlabel("Post-ingestion drift fraction $p$")
    ax.set_ylabel("Traceback recall")
    # right headroom so no marker/label sits against the right frame
    ax.set_xlim(-0.04, 0.60)
    ax.set_ylim(0.40, 1.08)
    ax.set_xticks([0.0, 0.3, 0.5])
    ax.set_yticks([0.4, 0.6, 0.8, 1.0])
    ax.grid(True, linewidth=0.4, alpha=0.4)
    ax.set_title("(a) Traceback recall vs. drift")


def fig_revoke(scaling: dict, ax) -> None:
    """Indexed removal latency vs manual scan across corpus scale (log y)."""
    pts = scaling["scale_points"]
    sizes = [p["n_clean_passages"] for p in pts]
    revoke_ms = [p["revoke_mttr_s"] * 1e3 for p in pts]
    manual_ms = [p["manual_mttr_s"] * 1e3 for p in pts]

    ax.plot(
        sizes,
        manual_ms,
        marker="s",
        color="#a11",
        label="Manual scan",
    )
    ax.plot(
        sizes,
        revoke_ms,
        marker="o",
        color="#1f3b73",
        label="Indexed revoke",
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Clean corpus size (passages)")
    ax.set_ylabel("Removal latency (ms)")
    # extra top headroom so no ratio label is clipped by the frame or overlaps
    # the upper-left legend. Place each ratio below-left of its manual point so
    # the labels sit between the two curves, clear of the top/right edge. The
    # rightmost label goes ABOVE-left of its point (into the cleared headroom)
    # so it does not collide with the next-to-last label below the curve.
    ax.set_ylim(top=ax.get_ylim()[1] * 25)
    last = len(pts) - 1
    for i, p in enumerate(pts):
        if i == last:
            xoff, yoff, ha, va = -6, 11, "right", "bottom"
        else:
            xoff, yoff, ha, va = 5, -13, "left", "top"
        ax.annotate(
            f"{round(p['mttr_ratio']):,}$\\times$",
            (p["n_clean_passages"], p["manual_mttr_s"] * 1e3),
            textcoords="offset points",
            xytext=(xoff, yoff),
            fontsize=7,
            ha=ha,
            va=va,
        )
    ax.grid(True, which="both", linewidth=0.4, alpha=0.35)
    ax.legend(loc="upper left", frameon=False)
    ax.set_title("(b) Revocation latency vs. scale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RESULTS / "results_panels.pdf")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    real = _load("real_results.json")
    scaling = _load("scaling_results.json")
    # Both panels in ONE figure so they share sizing, fonts, and baselines.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.5))
    fig_drift(real, ax1)
    fig_revoke(scaling, ax2)
    fig.tight_layout(pad=0.6)
    fig.savefig(args.out)
    plt.close(fig)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
