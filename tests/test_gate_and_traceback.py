"""Tests for chunking, ingestion, per-suspect provenance lookup, and granularity."""

from __future__ import annotations

from ragtrap.gate import chunk_text, ingest, ingest_per_document, verify_record
from ragtrap.records import Chunk
from ragtrap.signing import Ed25519Signer
from ragtrap.traceback import ragtrap_traceback


def _corpus() -> list[Chunk]:
    clean = [
        Chunk(f"c{i}", f"benign passage {i} about retrieval", "u://c", "p-clean")
        for i in range(20)
    ]
    poison = [
        Chunk(f"x{i}", f"ignore instructions injected claim {i}", "u://atk", "attacker")
        for i in range(5)
    ]
    return clean + poison


def test_chunk_text_advances_and_covers() -> None:
    chunks = chunk_text(
        "abcdefghij" * 10,
        chunk_chars=20,
        overlap=5,
        source_uri="u",
        principal="p",
        document_id="d",
    )
    assert len(chunks) > 1
    assert chunks[0].chunk_id == "d::c0"
    assert all(c.text for c in chunks)


def test_chunk_text_empty_input() -> None:
    out = chunk_text("", chunk_chars=10, overlap=2, source_uri="u", principal="p", document_id="d")
    assert out == []


def test_chunk_text_zero_overlap_no_infinite_loop() -> None:
    chunks = chunk_text(
        "x" * 100, chunk_chars=10, overlap=10, source_uri="u", principal="p", document_id="d"
    )
    assert len(chunks) == 100  # step clamped to >= 1


def test_ingest_signs_and_verifies_every_record() -> None:
    signer = Ed25519Signer.generate()
    store, stats = ingest(_corpus(), signer)
    assert len(store) == 25
    assert stats.n_records == 25
    assert all(verify_record(r, signer) for r in store.records.values())


def test_ragtrap_traceback_attributes_suspects() -> None:
    corpus = _corpus()
    signer = Ed25519Signer.generate()
    store, _ = ingest(corpus, signer)
    suspects = [c for c in corpus if c.principal == "attacker"]
    result = ragtrap_traceback(suspects, store, signer)
    ground_truth = {c.chunk_id: c.principal for c in suspects}
    assert result.recall(ground_truth) == 1.0
    # O(1) per suspect: one lookup each.
    assert result.work_units == len(suspects)


def test_identical_content_from_multiple_sources_is_ambiguous() -> None:
    signer = Ed25519Signer.generate()
    chunks = [
        Chunk("a", "identical text", "u://a", "source-a"),
        Chunk("b", "identical text", "u://b", "source-b"),
    ]
    store, _ = ingest(chunks, signer)
    suspect = Chunk("suspect", "identical text", "u://unknown", "unknown")
    result = ragtrap_traceback([suspect], store, signer)
    assert result.attributions == {"suspect": None}


def test_identical_content_from_one_source_remains_attributable() -> None:
    signer = Ed25519Signer.generate()
    chunks = [
        Chunk("a", "identical text", "u://a", "source-a"),
        Chunk("b", "identical text", "u://a", "source-a"),
    ]
    store, _ = ingest(chunks, signer)
    suspect = Chunk("suspect", "identical text", "u://unknown", "unknown")
    result = ragtrap_traceback([suspect], store, signer)
    assert result.attributions == {"suspect": "source-a"}


def test_ragtrap_traceback_detects_tamper() -> None:
    corpus = _corpus()
    signer = Ed25519Signer.generate()
    store, _ = ingest(corpus, signer)
    # Corrupt one stored signature; the suspect should fail verification.
    suspect = [c for c in corpus if c.principal == "attacker"][0]
    rec = store.records[suspect.chunk_id]
    bad = bytearray(bytes.fromhex(rec.signature_hex))
    bad[0] ^= 0xFF
    corrupted = {**rec.to_dict(), "signature_hex": bytes(bad).hex()}
    store.records[suspect.chunk_id] = type(rec)(**corrupted)
    result = ragtrap_traceback([suspect], store, signer)
    assert suspect.chunk_id in result.verification_failures


def test_per_document_ingest_uses_document_hash() -> None:
    signer = Ed25519Signer.generate()
    chunks = [
        Chunk("a::c0", "first part", "u", "p", document_id="a"),
        Chunk("a::c1", "second part", "u", "p", document_id="a"),
    ]
    store = ingest_per_document(chunks, signer)
    # Both chunks of one document inherit the same (document-level) content hash.
    hashes = {store.records[c.chunk_id].content_hash for c in chunks}
    assert len(hashes) == 1
    assert all(r.granularity == "document" for r in store.records.values())
