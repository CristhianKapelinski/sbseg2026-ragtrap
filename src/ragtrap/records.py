"""Provenance record schema and its canonical signed-message encoding.

A :class:`ProvenanceRecord` is the per-chunk artifact RAGtrap seals into the vector store. It
carries the chunk's own content hash and the detector verdicts that admitted it, in contrast to
document-level schemes that hash a whole document and propagate trust to fragments.

The signed message is a deterministic, canonical byte string over the provenance tuple, so a
single signature commits to (source URI, principal, chunk hash, detector verdicts, timestamp,
granularity) together. Canonicalisation uses JSON with sorted keys and no whitespace, which is
stable across processes and Python versions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Chunk:
    """A unit of corpus content to be ingested and signed."""

    chunk_id: str
    text: str
    source_uri: str
    principal: str
    #: ground-truth label used only for evaluation/recall; never trusted at ingestion.
    is_poisoned: bool = False
    #: identifier of the parent document (enables the per-document granularity contrast, E3).
    document_id: str = ""


@dataclass(frozen=True)
class ProvenanceRecord:
    """A signed per-chunk provenance record stored alongside the chunk in the vector store."""

    chunk_id: str
    source_uri: str
    principal: str
    content_hash: str
    detector_verdicts: dict[str, str]
    timestamp: str
    signer_name: str
    signer_identity: str
    signature_hex: str
    #: "chunk" (RAGtrap default) or "document" (the per-document contrast configuration, E3).
    granularity: str = "chunk"

    def signed_payload(self) -> dict[str, object]:
        """The fields covered by the signature (everything except the signature itself)."""
        return {
            "chunk_id": self.chunk_id,
            "source_uri": self.source_uri,
            "principal": self.principal,
            "content_hash": self.content_hash,
            "detector_verdicts": self.detector_verdicts,
            "timestamp": self.timestamp,
            "signer_name": self.signer_name,
            "signer_identity": self.signer_identity,
            "granularity": self.granularity,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def canonical_message(payload: dict[str, object]) -> bytes:
    """Deterministic byte encoding of a signed payload (sorted keys, compact separators)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


@dataclass
class StorageStats:
    """Accounting for signed-record storage cost (used by E4)."""

    n_records: int = 0
    total_record_bytes: int = 0
    total_signature_bytes: int = 0
    per_record_bytes: list[int] = field(default_factory=list)

    def add(self, record: ProvenanceRecord) -> None:
        encoded = canonical_message(record.to_dict())
        size = len(encoded)
        self.n_records += 1
        self.total_record_bytes += size
        self.total_signature_bytes += len(bytes.fromhex(record.signature_hex))
        self.per_record_bytes.append(size)

    def mean_record_bytes(self) -> float:
        return self.total_record_bytes / self.n_records if self.n_records else 0.0

    def mean_signature_bytes(self) -> float:
        return self.total_signature_bytes / self.n_records if self.n_records else 0.0
