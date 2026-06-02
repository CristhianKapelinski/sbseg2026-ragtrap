"""Ingestion gate: chunk -> detect -> hash -> sign -> store.

For each chunk the gate computes the content hash, runs the best-effort detector suite, builds
the canonical signed message over the provenance tuple, signs it with the configured backend,
and writes the signed :class:`ProvenanceRecord` into the datastore. The gate never drops a chunk
on a detector verdict: detectors are best-effort and recorded as verdicts, so even an
undetected poisoned chunk remains attributable and revocable.

A per-document configuration is provided for the granularity contrast (E3): one signed record is
produced per parent document and trust propagates to that document's chunks.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from .datastore import ProvenanceDatastore
from .detectors import Detector, default_detectors, run_detectors
from .hashing import sha256_text
from .records import Chunk, ProvenanceRecord, StorageStats, canonical_message
from .signing import Signer


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunk_text(
    text: str,
    *,
    chunk_chars: int,
    overlap: int,
    source_uri: str,
    principal: str,
    document_id: str,
    is_poisoned: bool = False,
) -> list[Chunk]:
    """Split ``text`` into overlapping character windows, each a :class:`Chunk`.

    Character-window chunking keeps the gate dependency-free and deterministic; a production
    deployment would reuse the host framework's splitter. ``overlap`` is clamped so the window
    always advances, preventing an infinite loop on a pathological config.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    step = max(1, chunk_chars - max(0, overlap))
    chunks: list[Chunk] = []
    idx = 0
    pos = 0
    text = text or ""
    if not text:
        return chunks
    while pos < len(text):
        window = text[pos : pos + chunk_chars]
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}::c{idx}",
                text=window,
                source_uri=source_uri,
                principal=principal,
                is_poisoned=is_poisoned,
                document_id=document_id,
            )
        )
        idx += 1
        pos += step
    return chunks


def sign_chunk(
    chunk: Chunk,
    signer: Signer,
    detectors: dict[str, Detector],
    *,
    granularity: str = "chunk",
    timestamp: str | None = None,
) -> ProvenanceRecord:
    """Hash, detect, and sign a single chunk, returning its provenance record."""
    content_hash = sha256_text(chunk.text)
    verdicts = run_detectors(chunk.text, detectors)
    payload = {
        "chunk_id": chunk.chunk_id,
        "source_uri": chunk.source_uri,
        "principal": chunk.principal,
        "content_hash": content_hash,
        "detector_verdicts": verdicts,
        "timestamp": timestamp or _now_iso(),
        "signer_name": signer.name,
        "signer_identity": signer.public_identity(),
        "granularity": granularity,
    }
    signature = signer.sign(canonical_message(payload))
    return ProvenanceRecord(
        chunk_id=payload["chunk_id"],
        source_uri=payload["source_uri"],
        principal=payload["principal"],
        content_hash=content_hash,
        detector_verdicts=verdicts,
        timestamp=payload["timestamp"],
        signer_name=signer.name,
        signer_identity=payload["signer_identity"],
        signature_hex=signature.hex(),
        granularity=granularity,
    )


def verify_record(record: ProvenanceRecord, signer: Signer) -> bool:
    """Recompute the canonical message and verify the record's signature."""
    message = canonical_message(record.signed_payload())
    return signer.verify(message, bytes.fromhex(record.signature_hex))


def ingest(
    chunks: Iterable[Chunk],
    signer: Signer,
    *,
    datastore: ProvenanceDatastore | None = None,
    detectors: dict[str, Detector] | None = None,
    stats: StorageStats | None = None,
) -> tuple[ProvenanceDatastore, StorageStats]:
    """Ingest chunks through the per-chunk gate, returning the populated datastore and stats."""
    store = datastore if datastore is not None else ProvenanceDatastore()
    detset = detectors if detectors is not None else default_detectors()
    acc = stats if stats is not None else StorageStats()
    for chunk in chunks:
        record = sign_chunk(chunk, signer, detset, granularity="chunk")
        store.put(chunk, record)
        acc.add(record)
    return store, acc


def ingest_per_document(
    chunks: Iterable[Chunk],
    signer: Signer,
    *,
    datastore: ProvenanceDatastore | None = None,
    detectors: dict[str, Detector] | None = None,
) -> ProvenanceDatastore:
    """Per-document contrast (E3): one signed record per parent document, trust propagated.

    The document hash is computed over the concatenation of its chunk texts; every chunk of the
    document inherits the same document-level content hash and signature. This reproduces the
    document-granularity model so attribution recall and false-purge rate can be measured against
    RAGtrap's per-chunk configuration, without fabricating external numbers.
    """
    store = datastore if datastore is not None else ProvenanceDatastore()
    detset = detectors if detectors is not None else default_detectors()

    by_doc: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk.document_id, []).append(chunk)

    for doc_id, doc_chunks in by_doc.items():
        concat = "".join(c.text for c in doc_chunks)
        doc_hash = sha256_text(concat)
        head = doc_chunks[0]
        verdicts = run_detectors(concat, detset)
        payload = {
            "chunk_id": doc_id,
            "source_uri": head.source_uri,
            "principal": head.principal,
            "content_hash": doc_hash,
            "detector_verdicts": verdicts,
            "timestamp": _now_iso(),
            "signer_name": signer.name,
            "signer_identity": signer.public_identity(),
            "granularity": "document",
        }
        signature = signer.sign(canonical_message(payload))
        for chunk in doc_chunks:
            record = ProvenanceRecord(
                chunk_id=chunk.chunk_id,
                source_uri=chunk.source_uri,
                principal=chunk.principal,
                content_hash=doc_hash,  # inherited document hash (no per-chunk hash)
                detector_verdicts=verdicts,
                timestamp=payload["timestamp"],
                signer_name=signer.name,
                signer_identity=payload["signer_identity"],
                signature_hex=signature.hex(),
                granularity="document",
            )
            store.put(chunk, record)
    return store
