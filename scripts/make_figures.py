"""Generate the paper's results figures from results/*.json.

Reads the canonical experiment outputs and emits paper/figs/*.pdf. Every plotted
value comes from a JSON file; nothing is recomputed or hardcoded here beyond
selecting and formatting. Run after the experiments, before compiling the paper:

    python scripts/make_figures.py

Emits:
* paper/figs/drift_recall.pdf   -- E2 traceback recall vs post-ingestion drift (95% Wilson CIs)
* paper/figs/revoke_scaling.pdf -- E3 surgical-revocation MTTR advantage vs corpus scale
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGS = ROOT / "paper" / "figs"

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
        "savefig.pad_inches": 0.03,
        "pdf.fonttype": 42,
    }
)


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def fig_drift(real: dict) -> None:
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

    fig, ax = plt.subplots(figsize=FIGSIZE)
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
    # annotate each point, nudging the p=0 label below the ceiling and the
    # others above so no text overlaps the markers, error bars, or the frame.
    for x, y in zip(xs, ys):
        dy = -11 if y > 0.95 else 6
        ax.annotate(
            f"{y:.2f}",
            (x, y),
            textcoords="offset points",
            xytext=(7, dy),
            fontsize=8,
        )
    ax.set_xlabel("Post-ingestion drift fraction $p$")
    ax.set_ylabel("Traceback recall")
    ax.set_xlim(-0.04, 0.56)
    ax.set_ylim(0.40, 1.06)
    ax.set_xticks([0.0, 0.3, 0.5])
    ax.set_yticks([0.4, 0.6, 0.8, 1.0])
    ax.grid(True, linewidth=0.4, alpha=0.4)
    fig.savefig(FIGS / "drift_recall.pdf")
    plt.close(fig)


def fig_revoke(scaling: dict) -> None:
    """Surgical-revocation MTTR vs manual scan across corpus scale (log y)."""
    pts = scaling["scale_points"]
    sizes = [p["n_clean_passages"] for p in pts]
    revoke_ms = [p["revoke_mttr_s"] * 1e3 for p in pts]
    manual_ms = [p["manual_mttr_s"] * 1e3 for p in pts]

    fig, ax = plt.subplots(figsize=FIGSIZE)
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
        label="Surgical revoke",
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Clean corpus size (passages)")
    ax.set_ylabel("MTTR (ms)")
    # widen the y-range so the ratio labels above the top manual point are not
    # clipped by the frame
    ax.set_ylim(top=ax.get_ylim()[1] * 6)
    # annotate each x with the manual/revoke ratio; the leftmost label would
    # collide with the y-axis if right-aligned, so left-align that one
    for i, p in enumerate(pts):
        first = i == 0
        ax.annotate(
            f"{round(p['mttr_ratio']):,}$\\times$",
            (p["n_clean_passages"], p["manual_mttr_s"] * 1e3),
            textcoords="offset points",
            xytext=(5, 6) if first else (-3, 6),
            fontsize=7,
            ha="left" if first else "right",
        )
    ax.grid(True, which="both", linewidth=0.4, alpha=0.35)
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(FIGS / "revoke_scaling.pdf")
    plt.close(fig)


def main() -> int:
    FIGS.mkdir(parents=True, exist_ok=True)
    real = _load("real_results.json")
    scaling = _load("scaling_results.json")
    fig_drift(real)
    fig_revoke(scaling)
    print(f"wrote {FIGS/'drift_recall.pdf'}")
    print(f"wrote {FIGS/'revoke_scaling.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
