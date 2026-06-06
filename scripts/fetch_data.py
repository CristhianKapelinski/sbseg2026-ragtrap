#!/usr/bin/env python3
"""Fetch and pin the third-party datasets the evaluation depends on.

Three artifacts, none authored here:

1. PoisonedRAG released adversarial passages (the attack) -- github.com/sleeepeer/PoisonedRAG,
   ``results/adv_targeted_results/{nq,hotpotqa,msmarco}.json``.
2. RAGForensics/RAGOrigin code and released feedback (the baseline + the labelled suspect set) --
   github.com/zhangbl6618/RAG-Responsibility-Attribution.
3. BEIR ``nq`` passage corpus (the clean substrate, 2,681,468 passages) -- HF ``BeIR/nq``.

The script clones the two small repos, verifies the pinned SHA-256 of each data file, and (unless
``--no-corpus``) downloads the BEIR corpus parquet. Paths default under ``$RAGTRAP_DATA_ROOT`` so
heavy data lives off the repo. Nothing is fabricated: a digest mismatch is a hard error.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ragtrap.realdata import POISONEDRAG_SHA256, RAGORIGIN_FEEDBACK_SHA256, feedback_file_digest

POISONEDRAG_REPO = "https://github.com/sleeepeer/PoisonedRAG.git"
BASELINE_REPO = "https://github.com/zhangbl6618/RAG-Responsibility-Attribution.git"


def _clone(url: str, dst: Path) -> None:
    if dst.exists():
        print(f"  already present: {dst}")
        return
    subprocess.run(["git", "clone", "--depth", "50", url, str(dst)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        default=os.environ.get("RAGTRAP_DATA_ROOT", os.path.expanduser("~/.cache/ragtrap")),
    )
    ap.add_argument("--no-corpus", action="store_true", help="skip the 764MB BEIR corpus download")
    args = ap.parse_args()

    root = Path(args.root)
    repos = root / "repos"
    repos.mkdir(parents=True, exist_ok=True)

    print("[1/3] PoisonedRAG (attack)")
    _clone(POISONEDRAG_REPO, repos / "PoisonedRAG")
    import hashlib

    for ds, pin in POISONEDRAG_SHA256.items():
        p = repos / "PoisonedRAG" / "results" / "adv_targeted_results" / f"{ds}.json"
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        ok = got == pin
        print(f"    {ds}.json sha256 {'OK' if ok else 'MISMATCH'}: {got[:16]}...")
        if not ok:
            print("    digest mismatch -- aborting", file=sys.stderr)
            return 1

    print("[2/3] RAG-Responsibility-Attribution (baseline + feedback)")
    _clone(BASELINE_REPO, repos / "RAG-Responsibility-Attribution")
    fb = (
        repos
        / "RAG-Responsibility-Attribution"
        / "attack_feedback"
        / "PRAGB"
        / "k5_m5_e5_gpt-4o-mini.json"
    )
    got = feedback_file_digest(fb)
    print(f"    feedback sha256 {'OK' if got == RAGORIGIN_FEEDBACK_SHA256 else 'MISMATCH'}: "
          f"{got[:16]}...")

    if not args.no_corpus:
        print("[3/3] BEIR/nq corpus (clean substrate, 2,681,468 passages)")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from huggingface_hub import snapshot_download

        p = snapshot_download(
            "BeIR/nq", repo_type="dataset", allow_patterns=["corpus/*", "README*"]
        )
        print(f"    downloaded to {p}")
    else:
        print("[3/3] skipped BEIR corpus (--no-corpus)")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
