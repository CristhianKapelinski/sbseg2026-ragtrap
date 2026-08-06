#!/usr/bin/env python3
"""Print one claim's reproduced numbers next to the paper's, and gate on them.

Each claim of the README maps to one entry here. The point is that the evaluator
runs a single command and reads a block that states, side by side, what the paper
claims and what this machine produced, instead of assembling a query by hand.

Exit code is 0 only when every gated value matches; hardware-dependent quantities
(latencies) are reported but never gated, because they legitimately differ per host.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
BAR = "═" * 66
SEP = "─" * 66


def _load(_name: str = "") -> dict:
    """Read the results file the calling script pointed at.

    Claims 1 and 2 are pointed at a run recomputed on this machine, never at the
    committed reference, so that the reported value is measured here.
    """
    path = Path(os.environ.get("RAGTRAP_CLAIM_SRC", RESULTS / "main_results.json"))
    if not path.exists():
        sys.exit(f"missing {path}. Run ./scripts/claim1.sh, which recomputes it.")
    return json.loads(path.read_text())


def _fmt(v):
    return f"{v:.2f}" if isinstance(v, float) else v


def _row(label: str, got, paper, ok: bool | None) -> str:
    mark = "" if ok is None else ("  OK" if ok else "  FAIL")
    ref = "" if paper is None else f"(paper {_fmt(paper)})"
    return f"  {label:<30}: {str(_fmt(got)):<12} {ref:<16}{mark}"


def claim1() -> list[tuple[str, object, object, bool | None]]:
    h = _load()["headline"]
    return [
        ("recall at drift p=0.0", round(h["drift_recall_0.0"], 2), 0.99,
         round(h["drift_recall_0.0"], 2) == 0.99),
        ("recall at drift p=0.3", round(h["drift_recall_0.3"], 2), 0.69,
         round(h["drift_recall_0.3"], 2) == 0.69),
        ("recall at drift p=0.5", round(h["drift_recall_0.5"], 2), 0.50,
         round(h["drift_recall_0.5"], 2) == 0.50),
        ("work units (lookups)", h["ragtrap_work_units"], 1000,
         h["ragtrap_work_units"] == 1000),
        ("model calls", h["ragtrap_model_calls"], 0, h["ragtrap_model_calls"] == 0),
        ("per-suspect latency (us)", round(h["ragtrap_per_suspect_us"], 1), None, None),
    ]


def claim2() -> list[tuple[str, object, object, bool | None]]:
    h = _load()["headline"]
    ci = h["false_purge_per_document_ci"]
    lo, hi = round(ci["ci_low"], 2), round(ci["ci_high"], 2)
    return [
        ("false purge, per document", round(h["false_purge_per_document"], 2), 0.52,
         round(h["false_purge_per_document"], 2) == 0.52),
        ("  95% Wilson CI", f"[{lo}, {hi}]", "[0.49, 0.55]", (lo, hi) == (0.49, 0.55)),
        ("  N documents", ci["n"], 1290, ci["n"] == 1290),
        ("false purge, per chunk", round(h["false_purge_per_chunk"], 2), 0.00,
         round(h["false_purge_per_chunk"], 2) == 0.00),
    ]


def claim3() -> list[tuple[str, object, object, bool | None]]:
    d = _load()
    # results.json nests it under "aux"; a regenerated aux_results.json does not.
    a = (d["aux"]["exp3"] if "aux" in d else d["exp3"])["attack_success"]
    pct = round(100 * a["k"] / a["n"])
    return [
        ("attack-success rate (%)", pct, 98, pct == 98),
        ("  questions", a["n"], 100, a["n"] == 100),
        ("  successes", a["k"], 98, a["k"] == 98),
    ]


CLAIMS = {
    "1": ("Forensic-time attribution and drift sensitivity", claim1),
    "2": ("Source revocation and false purge  (MAIN CLAIM)", claim2),
    "3": ("Attack-success context", claim3),
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in CLAIMS:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(CLAIMS)}}}")
    key = sys.argv[1]
    title, fn = CLAIMS[key]
    rows = fn()
    print(BAR)
    print(f"  Claim #{key}  {title}")
    print(SEP)
    for label, got, paper, ok in rows:
        print(_row(label, got, paper, ok))
    print(SEP)
    src = Path(os.environ.get("RAGTRAP_CLAIM_SRC", ""))
    if src.parent.name == "claim_run":
        print(f"  {'source of these numbers':<30}: recomputed on this machine just now")
    else:
        print(f"  {'source of these numbers':<30}: read from the committed --full run")
        print(f"  {'':<30}  ({src}); regenerating it needs a CUDA GPU")
    # Cost measured on THIS machine by the calling script. Times and memory are
    # hardware-dependent, so they are reported and never gated.
    elapsed = os.environ.get("RAGTRAP_CLAIM_ELAPSED")
    peak_kb = os.environ.get("RAGTRAP_CLAIM_PEAK_KB")
    if elapsed:
        print(f"  {'wall clock on this machine':<30}: {elapsed} s")
    if peak_kb == "unavailable":
        print(f"  {'peak memory':<30}: not measured (/usr/bin/time absent)")
    elif peak_kb:
        print(f"  {'peak memory on this machine':<30}: {int(peak_kb) / 1024:.0f} MB")
    if elapsed or peak_kb:
        print(SEP)
    gated = [ok for *_, ok in rows if ok is not None]
    failed = gated.count(False)
    print(f"  RESULT: {'OK' if not failed else f'{failed} MISMATCH'}"
          f"   ({len(gated) - failed}/{len(gated)} gated values match the paper)")
    print(BAR)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
