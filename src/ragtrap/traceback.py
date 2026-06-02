"""Poisoning traceback: RAGtrap's O(1) signature lookup and an iterative baseline.

Given a set of *suspect* chunks (e.g. surfaced by a query-time filter or an incident report),
traceback attributes each one to its source principal.

* :func:`ragtrap_traceback` resolves each suspect by its content hash to the signed provenance
  record in the datastore, in constant time per suspect, then verifies the signature. The
  attribution is read directly from the signed record: no re-retrieval, no LLM judge.

* :func:`iterative_baseline_traceback` reproduces the *algorithmic shape* of response-triggered
  attribution (RAGForensics / RAGOrigin) WITHOUT the LLM judge: for each suspect it re-retrieves
  candidate chunks from the corpus by similarity and scans them to decide attribution. This is a
  deliberately conservative, CPU-only, deterministic *structural lower bound* on the real
  baseline's cost; the published LLM-judge version is strictly slower (an LLM call per candidate).
  The number of corpus comparisons is counted explicitly so the work is auditable.

Both return an :class:`AttributionResult` carrying per-suspect attributions and a unit of work
count, so latency can be reported jointly with attribution recall and a latency win is never
bought at the cost of correctness.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .datastore import ProvenanceDatastore
from .gate import verify_record
from .hashing import sha256_text
from .records import Chunk
from .signing import Signer


@dataclass
class AttributionResult:
    """Per-suspect attribution plus an auditable unit-of-work count."""

    #: suspect chunk_id -> attributed principal (or None if unattributed)
    attributions: dict[str, str | None] = field(default_factory=dict)
    #: total units of work (datastore lookups for RAGtrap; corpus comparisons for the baseline)
    work_units: int = 0
    #: suspects whose signature failed verification (tamper evidence)
    verification_failures: list[str] = field(default_factory=list)

    def recall(self, ground_truth: dict[str, str]) -> float:
        """Fraction of suspects attributed to their true principal.

        ``ground_truth`` maps suspect chunk_id -> true principal. Recall is computed over the
        suspects present in ``ground_truth``.
        """
        if not ground_truth:
            return 0.0
        correct = sum(
            1
            for cid, true_principal in ground_truth.items()
            if self.attributions.get(cid) == true_principal
        )
        return correct / len(ground_truth)


def ragtrap_traceback(
    suspects: list[Chunk],
    datastore: ProvenanceDatastore,
    signer: Signer,
) -> AttributionResult:
    """O(1)-per-suspect signature-keyed traceback (the RAGtrap mechanism)."""
    result = AttributionResult()
    for suspect in suspects:
        content_hash = sha256_text(suspect.text)
        record = datastore.lookup_by_content_hash(content_hash)  # O(1)
        result.work_units += 1
        if record is None:
            result.attributions[suspect.chunk_id] = None
            continue
        if not verify_record(record, signer):
            result.verification_failures.append(suspect.chunk_id)
            result.attributions[suspect.chunk_id] = None
            continue
        result.attributions[suspect.chunk_id] = record.principal
    return result


def _token_set(text: str) -> set[str]:
    return set(text.lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def iterative_baseline_traceback(
    suspects: list[Chunk],
    corpus_chunks: list[Chunk],
    *,
    top_k: int = 5,
) -> AttributionResult:
    """Structural cost model of iterative re-retrieval attribution (no LLM judge).

    For each suspect, every corpus chunk is scored by lexical similarity (one comparison each),
    the top-``k`` candidates are taken, and the suspect is attributed to the majority principal
    among them. Each similarity comparison is one unit of work, mirroring the per-candidate cost
    the real baseline pays (and then multiplies by an LLM call). This is a lower bound on the
    published baseline's cost and is labelled as such throughout the artifact.
    """
    result = AttributionResult()
    corpus_tokens = [(c, _token_set(c.text)) for c in corpus_chunks]
    for suspect in suspects:
        s_tokens = _token_set(suspect.text)
        scored: list[tuple[float, Chunk]] = []
        for chunk, c_tokens in corpus_tokens:
            scored.append((_jaccard(s_tokens, c_tokens), chunk))
            result.work_units += 1  # one re-retrieval/scan comparison
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = [chunk for score, chunk in scored[:top_k] if score > 0.0]
        if not top:
            result.attributions[suspect.chunk_id] = None
            continue
        majority = Counter(chunk.principal for chunk in top).most_common(1)[0][0]
        result.attributions[suspect.chunk_id] = majority
    return result
