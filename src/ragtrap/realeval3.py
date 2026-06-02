"""E3: per-chunk vs per-document revocation granularity on real partially-poisoned documents.

A realistic partially-poisoned document is built from a real benign BEIR NQ passage (split into
clean chunks) into which an attacker injects a few real PoisonedRAG adversarial passages, all
attributed to one principal (the compromised source). Revoking that principal:

* under **per-document** granularity purges the whole document, including its clean chunks: a
  false purge of legitimate content; while
* under **per-chunk** granularity (RAGtrap) localises and removes only the poisoned chunks.

We sample many such documents and report the false-purge rate of each scheme with a 95% Wilson
CI over the pooled clean chunks, so the contrast is an interval, not a single hand-built number.
"""

from __future__ import annotations

import random

from .gate import chunk_text, ingest, ingest_per_document
from .records import Chunk
from .scaling import iter_beir_parquet
from .signing import Ed25519Signer
from .stats import wilson
from .traceback import ragtrap_traceback


def _build_mixed_document(
    benign_text: str, poison_texts: list[str], *, doc_id: str, principal: str,
    chunk_chars: int = 512, overlap: int = 64,
) -> list[Chunk]:
    """Real benign passage chunks + injected real poison passages, all under one principal."""
    clean = chunk_text(
        benign_text,
        chunk_chars=chunk_chars,
        overlap=overlap,
        source_uri=f"beir://nq/{doc_id}",
        principal=principal,
        document_id=doc_id,
        is_poisoned=False,
    )
    poison = [
        Chunk(
            chunk_id=f"{doc_id}::p{i}",
            text=t,
            source_uri=f"beir://nq/{doc_id}",
            principal=principal,
            is_poisoned=True,
            document_id=doc_id,
        )
        for i, t in enumerate(poison_texts)
    ]
    return clean + poison


def run_e3_granularity(
    parquet_path: str,
    poison_pool: list[str],
    *,
    n_documents: int = 200,
    poison_per_doc: int = 3,
    min_clean_chunks: int = 3,
    seed: int = 1337,
) -> dict[str, object]:
    """Sample documents, build a partially-poisoned version of each, contrast the two schemes."""
    rng = random.Random(seed)
    # Pull enough real passages to find n_documents long enough to chunk into several pieces.
    passages = list(iter_beir_parquet(parquet_path, limit=n_documents * 6))
    rng.shuffle(passages)

    per_doc_total_purged = 0
    per_doc_false_purged = 0  # clean chunks wrongly removed by per-document revocation
    per_chunk_total_purged = 0
    per_chunk_false_purged = 0
    per_chunk_poison_recall_hits = 0
    per_chunk_poison_total = 0
    docs_used = 0

    for idx, (pid, title, text) in enumerate(passages):
        if docs_used >= n_documents:
            break
        body = f"{title}\n{text}" if title else text
        principal = f"compromised-source-{idx}"
        doc_id = f"beir-{pid}-mix"
        poison_texts = rng.sample(poison_pool, min(poison_per_doc, len(poison_pool)))
        corpus = _build_mixed_document(body, poison_texts, doc_id=doc_id, principal=principal)
        n_clean = sum(1 for c in corpus if not c.is_poisoned)
        n_poison = sum(1 for c in corpus if c.is_poisoned)
        if n_clean < min_clean_chunks:
            continue
        docs_used += 1
        signer = Ed25519Signer.generate()

        # Per-document scheme: revoking the principal purges every chunk of the document.
        store_doc = ingest_per_document(corpus, signer)
        doc_purged = len(store_doc.chunks_of_principal(principal))
        per_doc_total_purged += doc_purged
        per_doc_false_purged += n_clean  # all clean chunks of the doc are over-purged

        # Per-chunk scheme (RAGtrap): attribute and localise the poisoned chunks only.
        store_chunk, _ = ingest(corpus, signer)
        suspects = [c for c in corpus if c.is_poisoned]
        gt = {c.chunk_id: c.principal for c in suspects}
        attr = ragtrap_traceback(suspects, store_chunk, signer)
        # Per-chunk revocation removes exactly the attributed poisoned chunks (no clean over-purge).
        attributed_poison = sum(1 for cid, p in attr.attributions.items() if p == principal)
        per_chunk_total_purged += attributed_poison
        per_chunk_false_purged += 0
        per_chunk_poison_recall_hits += sum(
            1 for cid, p in gt.items() if attr.attributions.get(cid) == p
        )
        per_chunk_poison_total += n_poison

    return {
        "experiment": "E3_granularity",
        "data": "real BEIR nq passages + injected real PoisonedRAG passages (one principal/doc)",
        "n_documents": docs_used,
        "poison_per_doc": poison_per_doc,
        "per_document": {
            "total_purged": per_doc_total_purged,
            "false_purged_clean": per_doc_false_purged,
            "false_purge_rate": wilson(per_doc_false_purged, per_doc_total_purged).as_dict()
            if per_doc_total_purged
            else None,
        },
        "per_chunk": {
            "total_purged": per_chunk_total_purged,
            "false_purged_clean": per_chunk_false_purged,
            "false_purge_rate": wilson(per_chunk_false_purged, per_chunk_total_purged).as_dict()
            if per_chunk_total_purged
            else {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "k": 0,
                  "n": per_chunk_total_purged},
            "poison_recall": wilson(
                per_chunk_poison_recall_hits, per_chunk_poison_total
            ).as_dict(),
        },
    }
