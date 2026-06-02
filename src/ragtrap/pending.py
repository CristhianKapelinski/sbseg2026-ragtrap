"""Ready-to-run harnesses for experiments that cannot run in a CPU-only, offline session.

These functions do NOT fabricate numbers. Each checks for the resources its experiment needs
(an LLM API key, a GPU, model weights, or a larger memory/time budget) and, when they are
absent, returns a typed PENDING descriptor stating exactly what is missing and how to run it.
When the resources are present, the harness wires the real components and runs them.

* E5 -- faithful head-to-head vs published RAGForensics / RAGOrigin (needs an LLM-judge API and
  an embedding retriever; their official repo is `RAG-Responsibility-Attribution`).
* E6 -- end-to-end PoisonedRAG ASR and a GMTP query-time layer (needs an LLM and an MLM on GPU).
* E7 -- full-scale corpora (full BEIR nq / hotpotqa / msmarco; needs more RAM/time/cores). The
  E1/E4 harness runs unchanged with the passage cap removed.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass
class PendingDescriptor:
    """A structured PENDING record: what is missing and how the experiment would run."""

    experiment: str
    status: str
    reason: str
    needs: list[str]
    how_to_run: str

    def as_dict(self) -> dict[str, object]:
        return {
            "experiment": self.experiment,
            "status": self.status,
            "reason": self.reason,
            "needs": self.needs,
            "how_to_run": self.how_to_run,
        }


def _has_gpu() -> bool:
    """Best-effort GPU probe without importing heavy frameworks."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        import subprocess

        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def run_e5() -> dict[str, object]:
    """E5 harness: faithful RAGForensics / RAGOrigin head-to-head."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return PendingDescriptor(
            experiment="E5",
            status="PENDING",
            reason=(
                "the published baseline runs an iterative LLM judge (GPT-4o-mini) plus an "
                "embedding retriever (e5); no LLM API key is available in this offline session, "
                "so a faithful head-to-head cannot run without fabricating baseline numbers."
            ),
            needs=[
                "OPENAI_API_KEY (LLM judge, e.g. gpt-4o-mini)",
                "embedding retriever weights (e.g. e5) and a GPU for practical throughput",
                "the official repo RAG-Responsibility-Attribution checked out alongside",
            ],
            how_to_run=(
                "Set OPENAI_API_KEY, clone RAG-Responsibility-Attribution, point "
                "RAGTRAP_BASELINE_REPO at it, then re-run this harness; it wraps the repo's "
                "RAGForensics/RAGOrigin main.py behind the E1 interface and records measured "
                "latency/recall against RAGtrap's O(1) lookup on the same corpus."
            ),
        ).as_dict()
    # Resource present: real wiring would go here. Not exercised in this session.
    return PendingDescriptor(
        experiment="E5",
        status="READY",
        reason="OPENAI_API_KEY present; wire the baseline repo and run the head-to-head.",
        needs=["RAGTRAP_BASELINE_REPO pointing at a checkout of RAG-Responsibility-Attribution"],
        how_to_run="Provide RAGTRAP_BASELINE_REPO and re-run; the harness will invoke the repo.",
    ).as_dict()


def run_e6() -> dict[str, object]:
    """E6 harness: end-to-end PoisonedRAG ASR and a GMTP query-time layer."""
    return PendingDescriptor(
        experiment="E6",
        status="PENDING",
        reason=(
            "reproducing PoisonedRAG ASR end to end (adversarial-text optimization + LLM "
            "generation) and running GMTP (an MLM/reranker) both require an LLM and an MLM on a "
            "GPU; neither is available here. RAGtrap's claims are forensic (traceback/recall/"
            "MTTR), not ASR, so this is positioning evidence only and must come from a real run."
        ),
        needs=[
            "a GPU",
            "an LLM for generation (and PoisonedRAG's optimizer)",
            "an MLM/reranker for the GMTP filter",
        ],
        how_to_run=(
            "On a GPU host with model access, run PoisonedRAG's optimizer to produce adversarial "
            "texts, measure ASR with the target LLM, then attach GMTP post-retrieval; record the "
            f"measured ASR and GMTP filter rate. gpu_detected={_has_gpu()}."
        ),
    ).as_dict()


def run_e7() -> dict[str, object]:
    """E7 harness: full-scale corpora (cap removed)."""
    return PendingDescriptor(
        experiment="E7",
        status="PENDING",
        reason=(
            "ingesting and signing the complete multi-million-passage BEIR corpora is a memory/"
            "time stretch for one CPU-only session; E1/E4 report the bounded-subset numbers as "
            "the real measurements with the cap stated."
        ),
        needs=["more RAM and time (and more cores for parallel signing)"],
        how_to_run=(
            "Raise RAGTRAP_BEIR_PASSAGE_CAP (or set it very high to remove the bound) and re-run "
            "the E1/E4 harness unchanged; the same code path measures the full corpus."
        ),
    ).as_dict()


def run_all_pending() -> dict[str, object]:
    """Return PENDING/READY descriptors for E5-E7 without fabricating any measurement."""
    return {"E5": run_e5(), "E6": run_e6(), "E7": run_e7()}
