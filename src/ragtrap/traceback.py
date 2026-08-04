"""Poisoning traceback through RAGtrap's indexed content-hash lookup.

Given a set of *suspect* chunks (e.g. surfaced by a query-time filter or by an incident report's
retrieved contexts), traceback attributes each one to its source principal.

:func:`ragtrap_traceback` resolves each suspect by its content hash to the signed provenance
record in the datastore, in constant time per suspect, then verifies the signature. The
attribution is read directly from the signed record: no re-retrieval, no LLM judge. The published
baseline (RAGForensics' LLM-judge loop, one model call per context) is implemented separately in
:mod:`ragtrap.llm_judge` and run on identical suspects in the evaluation.

The result carries per-suspect attributions and an auditable unit-of-work count, so latency can
be reported jointly with attribution recall.
"""

from __future__ import annotations

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
