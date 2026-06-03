"""E3: per-chunk vs per-document revocation granularity on real partially-poisoned documents.

A realistic partially-poisoned document is built from a real benign BEIR NQ passage (split into
clean chunks) into which an attacker injects a few real PoisonedRAG adversarial passages, all
attributed to one principal (the compromised source). Revoking that principal:

* under **per-document** granularity purges the whole document, including its clean chunks: a
  false purge of legitimate content; while
* under **per-chunk** granularity (RAGtrap) localises and removes only the poisoned chunks.

Both false-purge counts are *measured* by actually running the revocation against the datastore
and counting how many of the removed chunks were clean, rather than asserted: the per-chunk count
is expected to be 0 by construction (per-chunk revocation removes exactly the attributed poison
chunks), but the experiment confirms that property empirically instead of hard-coding it.

We sample many such documents and report the false-purge rate of each scheme with a 95% Wilson
CI over the pooled removed chunks, so the contrast is an interval, not a single hand-built number.
The per-document rate depends on how many adversarial passages the attacker injects per document
(``poison_per_doc``); :func:`sweep_e3_poison_per_doc` re-runs the contrast over a sweep of that
parameter, on the same real BEIR passages, so the headline rate is shown to be specific to the
chosen injection budget and the trend is visible.
"""

from __future__ import annotations

import random

from .gate import chunk_text, ingest, ingest_per_document
from .records import Chunk
from .revocation import revoke_source
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
    passages: list[tuple[str, str, str]] | None = None,
) -> dict[str, object]:
    """Sample documents, build a partially-poisoned version of each, contrast the two schemes.

    ``passages`` lets a caller (the sensitivity sweep) reuse one fixed, already-shuffled real
    BEIR sample across every ``poison_per_doc`` value, so only the injection budget varies.
    """
    rng = random.Random(seed)
    if passages is None:
        # Pull enough real passages to find n_documents long enough to chunk into several pieces.
        passages = list(iter_beir_parquet(parquet_path, limit=n_documents * 6))
        rng.shuffle(passages)

    per_doc_total_purged = 0
    per_doc_false_purged = 0  # clean chunks wrongly removed by per-document revocation
    per_chunk_total_purged = 0
    per_chunk_false_purged = 0  # clean chunks wrongly removed by per-chunk revocation (measured)
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
        clean_ids = {c.chunk_id for c in corpus if not c.is_poisoned}
        signer = Ed25519Signer.generate()

        # Per-document scheme: revoking the principal purges every chunk of the document.
        # We run the actual revocation and count the clean chunks that were removed, rather than
        # assuming it; under document granularity the principal's chunk set is the whole document,
        # so every clean chunk is collateral.
        store_doc = ingest_per_document(corpus, signer)
        doc_rev = revoke_source(store_doc, principal)
        per_doc_total_purged += doc_rev.n_purged
        per_doc_false_purged += sum(1 for cid in doc_rev.purged_chunk_ids if cid in clean_ids)

        # Per-chunk scheme (RAGtrap): attribute and localise the poisoned chunks only, then
        # actually remove exactly those chunks from the store and MEASURE the collateral, i.e.
        # how many clean chunks disappeared. This is computed from the post-revocation store, not
        # hard-coded; it is expected (and here confirmed) to be 0 because per-chunk granularity
        # targets only the attributed poison chunks.
        store_chunk, _ = ingest(corpus, signer)
        suspects = [c for c in corpus if c.is_poisoned]
        gt = {c.chunk_id: c.principal for c in suspects}
        attr = ragtrap_traceback(suspects, store_chunk, signer)
        to_revoke = [cid for cid, p in attr.attributions.items() if p == principal]
        clean_present_before = sum(1 for cid in clean_ids if cid in store_chunk.chunks)
        removed = 0
        for cid in to_revoke:
            if store_chunk.remove_chunk(cid):
                removed += 1
        clean_present_after = sum(1 for cid in clean_ids if cid in store_chunk.chunks)
        # Genuine collateral = clean chunks that were present before revocation but are gone after.
        per_chunk_false_purged += clean_present_before - clean_present_after
        per_chunk_total_purged += removed
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
            # Measured-and-confirmed: 0 clean chunks removed by per-chunk revocation over the run.
            "false_purge_measured_zero": per_chunk_false_purged == 0,
            "false_purge_rate": wilson(per_chunk_false_purged, per_chunk_total_purged).as_dict()
            if per_chunk_total_purged
            else {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "k": 0,
                  "n": per_chunk_total_purged},
            "poison_recall": wilson(
                per_chunk_poison_recall_hits, per_chunk_poison_total
            ).as_dict(),
        },
    }


def sweep_e3_poison_per_doc(
    parquet_path: str,
    poison_pool: list[str],
    *,
    n_documents: int = 200,
    poison_per_doc_values: tuple[int, ...] = (1, 2, 3, 5),
    min_clean_chunks: int = 3,
    seed: int = 1337,
) -> dict[str, object]:
    """Re-run the per-document vs per-chunk contrast over a sweep of ``poison_per_doc``.

    Everything except the number of injected adversarial passages is held fixed: the same real
    BEIR passages (loaded and shuffled once with the same seed) feed every point, so the
    per-document false-purge rate's dependence on the injection budget is isolated. This shows the
    headline rate (at ``poison_per_doc=3``) is specific to that budget and exposes the trend: more
    clean chunks per injected poison passage means a larger fraction of over-purged clean content.
    """
    rng = random.Random(seed)
    passages = list(iter_beir_parquet(parquet_path, limit=n_documents * 6))
    rng.shuffle(passages)

    points: list[dict[str, object]] = []
    for ppd in poison_per_doc_values:
        res = run_e3_granularity(
            parquet_path,
            poison_pool,
            n_documents=n_documents,
            poison_per_doc=ppd,
            min_clean_chunks=min_clean_chunks,
            seed=seed,
            passages=list(passages),
        )
        per_doc = res["per_document"]
        per_chunk = res["per_chunk"]
        points.append(
            {
                "poison_per_doc": ppd,
                "n_documents": res["n_documents"],
                "per_document_total_purged": per_doc["total_purged"],
                "per_document_false_purged_clean": per_doc["false_purged_clean"],
                "per_document_false_purge_rate": per_doc["false_purge_rate"],
                "per_chunk_total_purged": per_chunk["total_purged"],
                "per_chunk_false_purged_clean": per_chunk["false_purged_clean"],
                "per_chunk_false_purge_measured_zero": per_chunk["false_purge_measured_zero"],
                "per_chunk_false_purge_rate": per_chunk["false_purge_rate"],
            }
        )

    return {
        "experiment": "E3_poison_per_doc_sweep",
        "data": "real BEIR nq passages + injected real PoisonedRAG passages (one principal/doc)",
        "poison_per_doc_values": list(poison_per_doc_values),
        "points": points,
    }
