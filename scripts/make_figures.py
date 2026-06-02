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

# Shared style: single-column width, consistent fonts across both figures.
COLW_IN = 3.3  # ~\columnwidth in the SBC two-column-ish single-column body
plt.rcParams.update(
    {
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "figure.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
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

    fig, ax = plt.subplots(figsize=(COLW_IN, 2.1))
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
    for x, y in zip(xs, ys):
        ax.annotate(
            f"{y:.2f}",
            (x, y),
            textcoords="offset points",
            xytext=(6, 5),
            fontsize=7,
        )
    ax.set_xlabel("Post-ingestion drift fraction $p$")
    ax.set_ylabel("Traceback recall")
    ax.set_xlim(-0.04, 0.54)
    ax.set_ylim(0.40, 1.04)
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

    fig, ax = plt.subplots(figsize=(COLW_IN, 2.1))
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
    # annotate each x with the manual/revoke ratio
    for p in pts:
        ax.annotate(
            f"{round(p['mttr_ratio']):,}$\\times$",
            (p["n_clean_passages"], p["manual_mttr_s"] * 1e3),
            textcoords="offset points",
            xytext=(-2, 5),
            fontsize=6.5,
            ha="right",
        )
    ax.grid(True, which="both", linewidth=0.4, alpha=0.35)
    ax.legend(loc="lower right", frameon=False)
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
