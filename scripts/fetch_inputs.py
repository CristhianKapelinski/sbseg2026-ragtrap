#!/usr/bin/env python3
"""Auto-fetch and checksum-pin the third-party inputs the reproduction needs.

Fast path (default) fetches only the two *small* third-party files, each verified against a
pinned SHA-256 (a mismatch is a hard error, so a result never flows from the wrong bytes):

1. RAGOrigin / RAGForensics released attack-feedback (the labelled suspect set + the published
   baseline substrate) -- ``attack_feedback/PRAGB/k5_m5_e5_gpt-4o-mini.json`` from
   github.com/zhangbl6618/RAG-Responsibility-Attribution (shallow clone, ~6 MB).
2. PoisonedRAG released adversarial passages (the attack) -- ``results/adv_targeted_results/
   nq.json`` from github.com/sleeepeer/PoisonedRAG (sparse blobless clone, ~120 KB).

The clean BEIR/nq substrate for the fast Exp. 2 false-purge contrast is the frozen sample shipped in
the repo (``data/beir_nq_sample.parquet``), so the fast path needs no large download.

``--full`` additionally downloads the complete 2,681,468-passage BEIR/nq corpus parquet (~764 MB)
from the Hugging Face mirror, which the full-corpus scaling sweep (Exp. 1) consumes.

All paths default under ``$RAGTRAP_DATA_ROOT`` so heavy data lives off the repository tree.
Outputs (for the caller / reproduce.sh) are printed as ``KEY=path`` lines at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

# Import the pinned digests from the package so there is one source of truth.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ragtrap.realdata import (  # noqa: E402
    POISONEDRAG_SHA256,
    RAGORIGIN_FEEDBACK_SHA256,
)

RAGORIGIN_REPO = "https://github.com/zhangbl6618/RAG-Responsibility-Attribution.git"
POISONEDRAG_REPO = "https://github.com/sleeepeer/PoisonedRAG.git"
RAGORIGIN_FEEDBACK_REL = "attack_feedback/PRAGB/k5_m5_e5_gpt-4o-mini.json"
POISONEDRAG_NQ_REL = "results/adv_targeted_results/nq.json"
BEIR_NQ_REVISION = "b7253e6c379163d024ddb1d6948152a91a2e3b46"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _verify(path: Path, pinned: str, label: str) -> None:
    got = _sha256(path)
    if got != pinned:
        raise SystemExit(
            f"[FAIL] {label} digest {got} != pinned {pinned} for {path}"
        )
    print(f"   {label} sha256 OK ({got[:16]}...)", flush=True)


def _shallow_clone(url: str, dst: Path) -> None:
    if dst.exists():
        print(f"   already present: {dst}", flush=True)
        return
    subprocess.run(["git", "clone", "--depth", "1", url, str(dst)], check=True)


def _sparse_clone(url: str, dst: Path, sparse_dir: str) -> None:
    if dst.exists():
        print(f"   already present: {dst}", flush=True)
        return
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(dst)],
        check=True,
    )
    subprocess.run(["git", "-C", str(dst), "sparse-checkout", "set", sparse_dir], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        default=os.environ.get("RAGTRAP_DATA_ROOT", os.path.expanduser("~/.cache/ragtrap")),
    )
    ap.add_argument("--full", action="store_true",
                    help="also download the full 2.68M-passage BEIR/nq corpus (~764 MB)")
    args = ap.parse_args()

    root = Path(args.root)
    repos = root / "repos"
    repos.mkdir(parents=True, exist_ok=True)

    print("[1/2] RAGOrigin attack-feedback (labelled suspects + baseline substrate)", flush=True)
    ragorigin = repos / "RAG-Responsibility-Attribution"
    _shallow_clone(RAGORIGIN_REPO, ragorigin)
    feedback = ragorigin / RAGORIGIN_FEEDBACK_REL
    _verify(feedback, RAGORIGIN_FEEDBACK_SHA256, "feedback")

    print("[2/2] PoisonedRAG adversarial passages (the attack)", flush=True)
    prag = repos / "PoisonedRAG"
    _sparse_clone(POISONEDRAG_REPO, prag, "results/adv_targeted_results")
    poisonedrag_nq = prag / POISONEDRAG_NQ_REL
    _verify(poisonedrag_nq, POISONEDRAG_SHA256["nq"], "poisonedrag-nq")

    parquet = ""
    if args.full:
        print("[full] BEIR/nq corpus (2,681,468 passages, ~764 MB)", flush=True)
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from huggingface_hub import snapshot_download

        snap = snapshot_download(
            "BeIR/nq",
            repo_type="dataset",
            revision=BEIR_NQ_REVISION,
            allow_patterns=["corpus/*", "README*"],
        )
        import glob
        hits = glob.glob(os.path.join(snap, "**", "corpus-*.parquet"), recursive=True)
        parquet = hits[0] if hits else ""
        print(f"   corpus parquet: {parquet}", flush=True)

    # Machine-readable output for reproduce.sh.
    print("--- INPUTS ---")
    print(f"FEEDBACK={feedback}")
    print(f"POISONEDRAG={poisonedrag_nq}")
    if parquet:
        print(f"PARQUET={parquet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
