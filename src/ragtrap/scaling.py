"""Full-scale ingestion, traceback, and revocation on the real BEIR NQ corpus.

This module reads the real BEIR ``nq`` passage corpus directly from its parquet file (2,681,468
Wikipedia passages, the exact clean substrate PoisonedRAG and RAGOrigin evaluate on), ingests a
bounded prefix of it plus the real PoisonedRAG adversarial passages through the RAGtrap gate, and
measures, at several corpus sizes, the two structural quantities the paper claims:

* ingestion overhead (per-chunk Ed25519 signing latency, throughput, record size); and
* mean-time-to-remediation (MTTR) of one-command ``revoke-source`` versus a full-corpus manual
  scan, whose advantage grows with corpus size.

Reading the parquet directly (rather than streaming the dataset) keeps the prefix deterministic
and the digest reproducible. The passage prefix is pinned by the SHA-256 of its concatenated
texts, recorded in the result.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from .datastore import ProvenanceDatastore
from .detectors import default_detectors
from .gate import sign_chunk
from .realdata import PoisonedRagEntry
from .records import Chunk, StorageStats
from .revocation import manual_purge, revoke_source
from .signing import Ed25519Signer, HmacSigner


def iter_beir_parquet(parquet_path: str, *, limit: int, batch_size: int = 50000):
    """Yield up to ``limit`` (id, title, text) tuples from the BEIR parquet, in file order."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    yielded = 0
    for batch in pf.iter_batches(batch_size=batch_size, columns=["_id", "title", "text"]):
        d = batch.to_pydict()
        ids, titles, texts = d["_id"], d["title"], d["text"]
        for i in range(len(ids)):
            if yielded >= limit:
                return
            yield str(ids[i]), str(titles[i] or ""), str(texts[i] or "")
            yielded += 1


@dataclass
class ScalePoint:
    """Measured ingestion + revocation quantities at one corpus size."""

    n_clean_passages: int
    n_chunks: int
    n_poison_chunks: int
    sign_latency_us: float
    throughput_per_s: float
    mean_record_bytes: float
    revoke_mttr_s: float
    manual_mttr_s: float
    mttr_ratio: float
    revoked_chunks: int
    passage_prefix_sha256: str

    def as_dict(self) -> dict[str, object]:
        return vars(self)


def poison_chunks_from_poisonedrag(
    entries: list[PoisonedRagEntry], *, n_principals: int = 5
) -> list[Chunk]:
    """Real PoisonedRAG adversarial passages as poisoned chunks across attacker principals."""
    chunks: list[Chunk] = []
    idx = 0
    for entry in entries:
        for j, text in enumerate(entry.adv_texts):
            principal = f"poisonedrag-attacker-{idx % max(1, n_principals)}"
            chunks.append(
                Chunk(
                    chunk_id=f"prag-{entry.qid}-{j}",
                    text=text,
                    source_uri=f"poisonedrag://attacker/{entry.qid}",
                    principal=principal,
                    is_poisoned=True,
                    document_id=f"prag-doc-{entry.qid}",
                )
            )
        idx += 1
    return chunks


def run_scale_point(
    parquet_path: str,
    poison: list[Chunk],
    *,
    n_clean_passages: int,
    chunk_chars: int = 512,
    overlap: int = 64,
    revoke_principal: str | None = None,
    repeats: int = 5,
) -> ScalePoint:
    """Ingest a prefix of the real corpus + the real poison, then time revocation vs manual scan.

    Returns measured ingestion overhead and MTTR. The corpus is rebuilt for each timed run so the
    revoke and manual baselines start from identical stores; the structural O(revoked) vs
    O(corpus) gap is what the scaling sweep exposes.
    """
    from .gate import chunk_text

    # Build clean chunks from the real passage prefix, pinning the prefix by digest.
    hasher = hashlib.sha256()
    clean: list[Chunk] = []
    for i, (pid, title, text) in enumerate(
        iter_beir_parquet(parquet_path, limit=n_clean_passages)
    ):
        hasher.update(text.encode("utf-8"))
        body = f"{title}\n{text}" if title else text
        clean.extend(
            chunk_text(
                body,
                chunk_chars=chunk_chars,
                overlap=overlap,
                source_uri=f"beir://nq/{pid}",
                principal=f"nq-source-{i % 256}",
                document_id=f"beir-{pid}",
                is_poisoned=False,
            )
        )
    prefix_digest = hasher.hexdigest()
    corpus = clean + poison
    target = revoke_principal or poison[0].principal

    detset = default_detectors()
    signer = Ed25519Signer.generate()

    # Ingestion overhead: sign every chunk once, timing the signing path.
    stats = StorageStats()
    start = time.perf_counter()
    store = ProvenanceDatastore()
    for ch in corpus:
        rec = sign_chunk(ch, signer, detset, granularity="chunk")
        store.put(ch, rec)
        stats.add(rec)
    sign_seconds = time.perf_counter() - start
    n_chunks = len(corpus)

    # MTTR: one-command revoke (O(revoked)) vs manual full-corpus scan (O(corpus)).
    # The compromised principal's chunks are saved so each timed purge can be undone in place,
    # avoiding a full-store deep copy per repeat (which would dominate RAM at 2.68M passages).
    target_ids = sorted(store.chunks_of_principal(target))
    saved = [(cid, store.chunks[cid], store.records[cid]) for cid in target_ids]
    revoked_count = len(target_ids)

    def _restore() -> None:
        for _cid, chunk, rec in saved:
            store.put(chunk, rec)

    rev_times: list[float] = []
    man_times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        revoke_source(store, target)
        rev_times.append(time.perf_counter() - t0)
        store.revoked_principals.discard(target)
        _restore()

        t0 = time.perf_counter()
        manual_purge(store, target)
        man_times.append(time.perf_counter() - t0)
        store.revoked_principals.discard(target)
        _restore()

    rev_mttr = min(rev_times)
    man_mttr = min(man_times)
    return ScalePoint(
        n_clean_passages=n_clean_passages,
        n_chunks=n_chunks,
        n_poison_chunks=len(poison),
        sign_latency_us=(sign_seconds / n_chunks) * 1e6,
        throughput_per_s=n_chunks / sign_seconds if sign_seconds else 0.0,
        mean_record_bytes=stats.mean_record_bytes(),
        revoke_mttr_s=rev_mttr,
        manual_mttr_s=man_mttr,
        mttr_ratio=man_mttr / rev_mttr if rev_mttr else 0.0,
        revoked_chunks=revoked_count,
        passage_prefix_sha256=prefix_digest,
    )


def measure_signing_backends(
    parquet_path: str, *, n_clean_passages: int, chunk_chars: int = 512, overlap: int = 64
) -> dict[str, object]:
    """Per-chunk signing cost of real Ed25519 vs the symmetric HMAC stand-in on real passages."""
    from .gate import chunk_text

    chunks: list[Chunk] = []
    for i, (pid, title, text) in enumerate(
        iter_beir_parquet(parquet_path, limit=n_clean_passages)
    ):
        body = f"{title}\n{text}" if title else text
        chunks.extend(
            chunk_text(
                body,
                chunk_chars=chunk_chars,
                overlap=overlap,
                source_uri=f"beir://nq/{pid}",
                principal=f"nq-source-{i % 256}",
                document_id=f"beir-{pid}",
            )
        )
    detset = default_detectors()

    def _measure(signer):
        stats = StorageStats()
        start = time.perf_counter()
        store = ProvenanceDatastore()
        for ch in chunks:
            rec = sign_chunk(ch, signer, detset, granularity="chunk")
            store.put(ch, rec)
            stats.add(rec)
        elapsed = time.perf_counter() - start
        return {
            "signer": signer.name,
            "n_chunks": len(chunks),
            "total_seconds": elapsed,
            "throughput_chunks_per_s": len(chunks) / elapsed if elapsed else 0.0,
            "mean_sign_latency_us": (elapsed / len(chunks)) * 1e6 if chunks else 0.0,
            "mean_record_bytes": stats.mean_record_bytes(),
            "mean_signature_bytes": stats.mean_signature_bytes(),
        }

    ed = _measure(Ed25519Signer.generate())
    hm = _measure(HmacSigner.generate())
    return {
        "n_clean_passages": n_clean_passages,
        "n_chunks": len(chunks),
        "ed25519": ed,
        "hmac": hm,
        "ed25519_over_hmac_time": ed["total_seconds"] / hm["total_seconds"]
        if hm["total_seconds"]
        else 0.0,
    }
