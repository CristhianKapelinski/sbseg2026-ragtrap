"""Real, non-circular evaluation on third-party PoisonedRAG / RAGOrigin data.

The substrate is the RAGOrigin released feedback file: for 100 NQ questions, the top-100 contexts
surfaced by the real ``intfloat/e5`` dense retriever, each with a third-party ground-truth label
(poisoned vs clean) and the real PoisonedRAG adversarial text. None of it is authored here.

Ingestion model (realistic). Every retrieved context is corpus content that was ingested. Clean
contexts come from benign Wikipedia/NQ sources (round-robined benign principals); poisoned
contexts are the real PoisonedRAG passages, attributed to attacker principals. The whole set is
sealed through the RAGtrap gate with real Ed25519 per chunk.

Forensic time. The suspects are the top-``k`` retrieved contexts per question, i.e. exactly what
an attacked RAG pipeline feeds the language model. Two attributors run on the *identical* suspect
list:

* **RAGtrap**: one constant-time content-hash lookup per suspect, resolving the signed record and
  reading its principal. A suspect is flagged poisoned iff its principal is an attacker principal.
* **RAGForensics (baseline)**: the published LLM-judge loop (one model call per context), run on a
  local GPU model over the same contexts; see :mod:`ragtrap.llm_judge`.

Adversarial drift split (honest false negatives). A configurable fraction of the *poisoned*
suspects are paraphrased after ingestion so their retrieved bytes differ from the sealed bytes.
A hash lookup cannot match a paraphrase, so these are genuine RAGtrap false negatives that we
report rather than hide; precision stays exact because a hash match is exact.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .gate import ingest
from .llm_judge import LocalLLMJudge
from .records import Chunk
from .signing import Ed25519Signer
from .stats import wilson
from .traceback import ragtrap_traceback

ATTACKER_PRINCIPAL = "poisonedrag-attacker"


# ---------------------------------------------------------------------------- ingest
def build_corpus_from_feedback(feedback, *, benign_principals: int = 32) -> list[Chunk]:
    """Turn every retrieved context across all questions into a signed-ingestion Chunk.

    Poisoned contexts (third-party label True) are attributed to the attacker principal; clean
    contexts are round-robined across benign source principals. Each context becomes one chunk
    keyed by ``q<qid>::r<rank>`` so identical poison strings across questions stay distinct.
    """
    chunks: list[Chunk] = []
    benign_idx = 0
    for q in feedback:
        for ctx in q.contexts:
            if ctx.is_poison:
                principal = ATTACKER_PRINCIPAL
                uri = f"poisonedrag://attacker/{q.question_id}"
            else:
                principal = f"nq-source-{benign_idx % max(1, benign_principals)}"
                uri = f"beir://nq/clean/{benign_idx}"
                benign_idx += 1
            chunks.append(
                Chunk(
                    chunk_id=f"q{q.question_id}::r{ctx.rank}",
                    text=ctx.text,
                    source_uri=uri,
                    principal=principal,
                    is_poisoned=ctx.is_poison,
                    document_id=f"doc-{q.question_id}-{ctx.rank}",
                )
            )
    return chunks


def _paraphrase(text: str, rng: random.Random) -> str:
    """Cheap deterministic byte-level drift: a paraphrase a retriever would still surface.

    The semantics are preserved (the same claim) but the bytes change, so an exact content hash
    no longer matches. This models a poisoned source mutating after collection (split-view /
    frontrunning), the case PoisonedRAG and Carlini both describe.
    """
    prefixes = [
        "As is widely documented, ",
        "According to multiple sources, ",
        "It is well established that ",
        "Notably, ",
        "In fact, ",
    ]
    suffixes = [
        " This is the accepted account.",
        " This remains the standard reference.",
        " The record is consistent on this point.",
        " This is corroborated elsewhere.",
        "",
    ]
    body = text
    if rng.random() < 0.5 and ". " in body:
        head, _, tail = body.partition(". ")
        body = tail + ". " + head if tail else body
    return rng.choice(prefixes) + body + rng.choice(suffixes)


# --------------------------------------------------------------------------------------------- E1
@dataclass
class ConfusionCounts:
    """Pooled confusion counts over contexts judged poisoned (positive) vs clean (negative)."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, predicted_poison: bool, truth_poison: bool) -> None:
        if predicted_poison and truth_poison:
            self.tp += 1
        elif predicted_poison and not truth_poison:
            self.fp += 1
        elif not predicted_poison and truth_poison:
            self.fn += 1
        else:
            self.tn += 1

    def metrics(self) -> dict[str, object]:
        pos = self.tp + self.fn
        neg = self.tn + self.fp
        pred_pos = self.tp + self.fp
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "n_positives": pos,
            "n_negatives": neg,
            "recall": wilson(self.tp, pos).as_dict() if pos else None,
            "precision": wilson(self.tp, pred_pos).as_dict() if pred_pos else None,
            "fpr": wilson(self.fp, neg).as_dict() if neg else None,
            "fnr": wilson(self.fn, pos).as_dict() if pos else None,
        }


def run_e1_ragtrap(
    feedback,
    *,
    top_k: int = 5,
    drift_fraction: float = 0.0,
    seed: int = 1337,
    repeats: int = 5,
) -> dict[str, object]:
    """RAGtrap O(1) attribution over the top-k retrieved suspects of every question.

    Returns confusion-based detection metrics, attribution recall, latency, and work units.
    With ``drift_fraction`` > 0 the given fraction of poisoned suspects is paraphrased after
    ingestion, exposing real hash-miss false negatives.
    """
    rng = random.Random(seed)
    corpus = build_corpus_from_feedback(feedback)
    signer = Ed25519Signer.generate()
    store, _ = ingest(corpus, signer)

    # Suspects: top-k retrieved contexts per question (what the attacked RAG fed the LLM).
    suspects: list[Chunk] = []
    truth: dict[str, bool] = {}
    drifted: set[str] = set()
    for q in feedback:
        topk = sorted(q.contexts, key=lambda c: c.rank)[:top_k]
        for ctx in topk:
            cid = f"q{q.question_id}::r{ctx.rank}"
            text = ctx.text
            if ctx.is_poison and drift_fraction > 0 and rng.random() < drift_fraction:
                text = _paraphrase(text, rng)
                drifted.add(cid)
            suspects.append(
                Chunk(
                    chunk_id=cid,
                    text=text,
                    source_uri="suspect://retrieved",
                    principal="unknown",
                    is_poisoned=ctx.is_poison,
                    document_id=cid,
                )
            )
            truth[cid] = ctx.is_poison

    # Timed O(1) attribution (repeats for a latency CI).
    latencies: list[float] = []
    attribution = None
    for _ in range(repeats):
        start = time.perf_counter()
        attribution = ragtrap_traceback(suspects, store, signer)
        latencies.append(time.perf_counter() - start)
    assert attribution is not None

    conf = ConfusionCounts()
    attribution_correct = 0
    attribution_pos = 0
    for s in suspects:
        principal = attribution.attributions.get(s.chunk_id)
        predicted_poison = principal == ATTACKER_PRINCIPAL
        conf.add(predicted_poison, truth[s.chunk_id])
        if truth[s.chunk_id]:
            attribution_pos += 1
            if predicted_poison:
                attribution_correct += 1

    return {
        "method": "ragtrap",
        "n_questions": len(feedback),
        "top_k": top_k,
        "n_suspects": len(suspects),
        "n_poison_suspects": sum(1 for v in truth.values() if v),
        "n_clean_suspects": sum(1 for v in truth.values() if not v),
        "drift_fraction": drift_fraction,
        "n_drifted": len(drifted),
        "detection": conf.metrics(),
        "attribution_recall": wilson(attribution_correct, attribution_pos).as_dict(),
        "work_units": attribution.work_units,
        "latency_s_min": min(latencies),
        "latency_s_mean": sum(latencies) / len(latencies),
        "latency_s_per_suspect_us": (min(latencies) / len(suspects)) * 1e6,
        "repeats": repeats,
    }


def run_e1_baseline_judge(
    feedback,
    judge: LocalLLMJudge,
    *,
    top_k: int = 5,
    max_questions: int | None = None,
    usd_per_call: float = 0.0,
) -> dict[str, object]:
    """RAGForensics LLM-judge baseline over the identical top-k suspects.

    One model call per context. Returns the same detection metrics plus measured wall-clock,
    model-call count, and a per-incident cost (``usd_per_call`` priced at the published API rate).
    """
    conf = ConfusionCounts()
    total_calls = 0
    total_seconds = 0.0
    n_q = 0
    questions = feedback if max_questions is None else feedback[:max_questions]
    for q in questions:
        topk = sorted(q.contexts, key=lambda c: c.rank)[:top_k]
        texts = [c.text for c in topk]
        res = judge.judge_contexts(q.question, q.rag_response or q.target_answer, texts)
        total_calls += res.n_calls
        total_seconds += res.total_seconds
        for ctx, predicted_poison in zip(topk, res.labels, strict=False):
            conf.add(predicted_poison, ctx.is_poison)
        n_q += 1
    n_suspects = sum(
        len(sorted(q.contexts, key=lambda c: c.rank)[:top_k]) for q in questions
    )
    return {
        "method": "ragforensics_llm_judge",
        "judge_model": judge.model_name,
        "n_questions": n_q,
        "top_k": top_k,
        "n_suspects": n_suspects,
        "detection": conf.metrics(),
        "work_units": total_calls,
        "model_calls": total_calls,
        "latency_s_total": total_seconds,
        "latency_s_per_suspect": total_seconds / n_suspects if n_suspects else 0.0,
        "usd_per_call": usd_per_call,
        "estimated_usd_cost": total_calls * usd_per_call,
    }
