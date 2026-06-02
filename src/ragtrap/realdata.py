"""Loaders for the real, third-party attack and retrieval data, pinned by checksum.

Two artifacts, both released by groups other than this work, are used so the evaluation is
non-circular (the detector under test authored neither the attack nor the labels):

* **PoisonedRAG** (Zou et al., USENIX Security 2025) released adversarial passages:
  ``results/adv_targeted_results/{nq,hotpotqa,msmarco}.json``. Each file holds 100 target
  questions; each carries the ``correct answer``, the attacker ``incorrect answer``, and 5
  adversarial passages. These are real attacker output, not a template authored here.

* **RAGOrigin / RAGForensics** (Zhang et al., S&P 2026 / WWW 2025) released attack-feedback:
  ``attack_feedback/PRAGB/k5_m5_e5_gpt-4o-mini.json``. Each of 100 NQ questions carries the
  top-100 contexts surfaced by the real ``intfloat/e5`` dense retriever, with the third-party
  ground-truth ``context_labels`` (True == poisoned) and ``retrieval_scores``. This is the exact
  format and substrate the published baseline consumes, so RAGForensics can be run on it
  verbatim and RAGtrap attribution can be measured on identical inputs.

Each loader verifies the SHA-256 of the file it reads against a pinned digest and raises
:class:`DataIntegrityError` on mismatch, so a result never silently flows from the wrong bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# Pinned SHA-256 digests of the third-party files (verified on the cloned upstream repos).
POISONEDRAG_SHA256 = {
    "nq": "44df711454a9bada08e72e9e4a003a2cc845c43707ac93a3493e5168ec415cf2",
    "hotpotqa": "5119d6f9fd53cb0ecb3f33de939bd940d77cbaf80284b7ccd3d256f63a430537",
    "msmarco": "d6bf508ebb0e31e09095995061bd483678e2ae8634f6ba5de1611e4adf9b1987",
}
# RAGOrigin released feedback (e5 retriever, gpt-4o-mini attack LLM, k=5, m=5).
RAGORIGIN_FEEDBACK_SHA256 = (
    "658419c9411ee68571c15174e6ceaed3ea24f9912bef8ed5a805a44638fde3b6"
)


class DataIntegrityError(RuntimeError):
    """Raised when a third-party data file's digest does not match the pinned value."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class FeedbackContext:
    """One retrieved context for a question, with its third-party ground-truth label."""

    text: str
    is_poison: bool
    retrieval_score: float
    rank: int


@dataclass(frozen=True)
class FeedbackQuestion:
    """One attacked question: its retrieved contexts and the RAG response under attack."""

    question_id: str
    question: str
    correct_answer: str
    target_answer: str
    rag_response: str
    contexts: list[FeedbackContext]


def load_ragorigin_feedback(
    path: str | Path, *, expected_sha256: str | None = None
) -> list[FeedbackQuestion]:
    """Load the RAGOrigin released feedback file (e5 retrieval over NQ, k5_m5).

    Verifies the file digest when ``expected_sha256`` is given (the pinned value is recorded in
    the run manifest, not hard-failed here, because the upstream file may be re-released; the
    measured digest always flows into the manifest).
    """
    path = Path(path)
    digest = _sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise DataIntegrityError(
            f"feedback digest {digest} != pinned {expected_sha256} for {path}"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[FeedbackQuestion] = []
    for item in raw:
        labels = item["context_labels"]
        texts = item["context_texts"]
        scores = item.get("retrieval_scores", [0.0] * len(texts))

        def _is_poison(label) -> bool:
            return label == "True" if isinstance(label, str) else bool(label)

        contexts = [
            FeedbackContext(
                text=str(texts[i]),
                is_poison=_is_poison(labels[i]),
                retrieval_score=float(scores[i]) if i < len(scores) else 0.0,
                rank=i,
            )
            for i in range(len(texts))
        ]
        out.append(
            FeedbackQuestion(
                question_id=str(item.get("question_id", item.get("id", len(out)))),
                question=str(item.get("question", "")),
                correct_answer=str(item.get("correct_answer", item.get("correct answer", ""))),
                target_answer=str(item.get("target_answer", item.get("incorrect answer", ""))),
                rag_response=str(item.get("RAG_response", "")),
                contexts=contexts,
            )
        )
    return out


def feedback_file_digest(path: str | Path) -> str:
    """Public helper to record a third-party file's measured digest in the manifest."""
    return _sha256_file(Path(path))


@dataclass(frozen=True)
class PoisonedRagEntry:
    """One PoisonedRAG target question with its released adversarial passages."""

    qid: str
    question: str
    correct_answer: str
    incorrect_answer: str
    adv_texts: list[str]


def load_poisonedrag(
    path: str | Path, *, dataset: str = "nq"
) -> list[PoisonedRagEntry]:
    """Load PoisonedRAG released adversarial passages, verifying the pinned digest."""
    path = Path(path)
    digest = _sha256_file(path)
    pinned = POISONEDRAG_SHA256.get(dataset)
    if pinned is not None and digest != pinned:
        raise DataIntegrityError(
            f"PoisonedRAG {dataset} digest {digest} != pinned {pinned} for {path}"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[PoisonedRagEntry] = []
    for _, v in raw.items():
        out.append(
            PoisonedRagEntry(
                qid=str(v.get("id", len(out))),
                question=str(v.get("question", "")),
                correct_answer=str(v.get("correct answer", "")),
                incorrect_answer=str(v.get("incorrect answer", "")),
                adv_texts=[str(t) for t in v.get("adv_texts", [])],
            )
        )
    return out
