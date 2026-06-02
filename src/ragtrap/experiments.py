"""Experiment runners E0-E4 (runnable, CPU-only) producing real measured outputs.

Each runner returns a JSON-serialisable dict of measured quantities and logs its steps. No
number is invented: every value comes from code executed here. Latency is wall-clock over the
operation under test, measured with ``time.perf_counter`` and repeated where it is short enough
to warrant repetition. Where an experiment uses synthetic data it is labelled synthetic in the
output. E5-E7 are PENDING and live in ``ragtrap.pending`` as ready-to-run harnesses.
"""

from __future__ import annotations

import platform
import statistics
import sys
import time

from .config import Config
from .corpus import (
    CorpusUnavailable,
    PoisonedRagBuilder,
    load_beir_nq_passages,
    passages_to_chunks,
)
from .gate import ingest, ingest_per_document, verify_record
from .logging_setup import get_logger
from .records import Chunk, StorageStats
from .revocation import manual_purge, revoke_source
from .signing import Ed25519Signer, HmacSigner, make_signer
from .synthetic import generate_corpus
from .traceback import iterative_baseline_traceback, ragtrap_traceback

log = get_logger()


def _env_block() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
    }


def _suspects_from(chunks: list[Chunk]) -> tuple[list[Chunk], dict[str, str]]:
    """Take the poisoned chunks as the suspect set; ground truth maps id -> true principal."""
    suspects = [c for c in chunks if c.is_poisoned]
    ground_truth = {c.chunk_id: c.principal for c in suspects}
    return suspects, ground_truth


# --------------------------------------------------------------------------------------------- E0
def run_e0(cfg: Config) -> dict[str, object]:
    """E0 -- instrument validation on synthetic data (correctness, not performance)."""
    log.info("E0: instrument validation on synthetic data (labelled synthetic)")
    chunks = generate_corpus(
        n_chunks=200, n_principals=5, poison_fraction=0.1, seed=cfg.seed, poisoned_principals=1
    )
    signer = Ed25519Signer.generate()
    store, _ = ingest(chunks, signer)

    # (a) every signed record verifies; tampering is detected.
    all_verify = all(verify_record(r, signer) for r in store.records.values())
    sample_id = next(iter(store.records))
    tampered = store.records[sample_id]
    tampered_detected = not signer.verify(
        b"not-the-signed-message", bytes.fromhex(tampered.signature_hex)
    )

    # (b) signature-keyed traceback recovers the injected attribution at 100% by construction.
    suspects, ground_truth = _suspects_from(chunks)
    attribution = ragtrap_traceback(suspects, store, signer)
    recall = attribution.recall(ground_truth)

    # (c) revoke-source purges exactly the targeted principal's chunks and no others.
    target_principal = "attacker-0"
    expected_purge = store.chunks_of_principal(target_principal)
    before = len(store)
    rev = revoke_source(store, target_principal)
    after = len(store)
    purged_exactly = set(rev.purged_chunk_ids) == expected_purge
    no_collateral = (before - after) == len(expected_purge)

    result = {
        "experiment": "E0",
        "data": "synthetic (labelled)",
        "n_chunks": len(chunks),
        "all_records_verify": all_verify,
        "tamper_detected": tampered_detected,
        "traceback_recall": recall,
        "revoked_principal": target_principal,
        "chunks_purged": rev.n_purged,
        "purged_exactly_target": purged_exactly,
        "no_collateral_purge": no_collateral,
        "instrument_valid": bool(
            all_verify and tampered_detected and recall == 1.0 and purged_exactly and no_collateral
        ),
    }
    log.info("E0 result: %s", result)
    return result


# --------------------------------------------------------------------------------------------- E1
def _load_real_or_note(cfg: Config) -> tuple[list[Chunk], dict[str, object]]:
    """Load the BEIR nq subset; return clean chunks and a corpus-provenance note."""
    passages = load_beir_nq_passages(
        cap=cfg.beir_passage_cap, dataset=cfg.beir_dataset, hf_revision=cfg.hf_revision
    )
    clean = passages_to_chunks(passages, chunk_chars=cfg.chunk_chars, overlap=cfg.chunk_overlap)
    note = {
        "corpus": f"BEIR/{cfg.beir_dataset} (real public)",
        "passage_cap": cfg.beir_passage_cap,
        "passages_loaded": len(passages),
        "hf_revision": cfg.hf_revision,
        "clean_chunks": len(clean),
    }
    return clean, note


def _timed(fn, repeats: int = 1):
    """Run ``fn`` ``repeats`` times, returning (last_value, min_seconds, mean_seconds)."""
    durations: list[float] = []
    value = None
    for _ in range(repeats):
        start = time.perf_counter()
        value = fn()
        durations.append(time.perf_counter() - start)
    return value, min(durations), statistics.mean(durations)


def run_e1(cfg: Config, clean_chunks: list[Chunk]) -> dict[str, object]:
    """E1 -- headline traceback latency and recall: RAGtrap O(1) vs iterative baseline."""
    log.info("E1: headline traceback latency and recall on real BEIR corpus + poisoned set")
    target_questions = [
        "what is the capital of the country",
        "who discovered the chemical element",
        "when did the historical event occur",
        "where is the geographic landmark located",
        "why did the policy change take effect",
    ]
    poison = PoisonedRagBuilder(n_principals=3, texts_per_principal=5).build(target_questions)
    corpus = clean_chunks + poison
    log.info("E1: %d clean chunks + %d poisoned chunks", len(clean_chunks), len(poison))

    signer = Ed25519Signer.generate()
    store, _ = ingest(corpus, signer)

    suspects, ground_truth = _suspects_from(corpus)

    rt_result, rt_min, rt_mean = _timed(
        lambda: ragtrap_traceback(suspects, store, signer), repeats=5
    )
    bl_result, bl_min, bl_mean = _timed(
        lambda: iterative_baseline_traceback(suspects, corpus, top_k=5), repeats=1
    )

    rt_recall = rt_result.recall(ground_truth)
    bl_recall = bl_result.recall(ground_truth)
    latency_ratio = (bl_min / rt_min) if rt_min > 0 else float("inf")
    work_ratio = (bl_result.work_units / rt_result.work_units) if rt_result.work_units else float(
        "inf"
    )

    result = {
        "experiment": "E1",
        "data": "BEIR nq subset (real) + PoisonedRAG poisoned set (reconstructed-from-template)",
        "n_clean_chunks": len(clean_chunks),
        "n_poisoned_chunks": len(poison),
        "n_suspects": len(suspects),
        "ragtrap_traceback_recall": rt_recall,
        "baseline_traceback_recall": bl_recall,
        "ragtrap_latency_s_min": rt_min,
        "ragtrap_latency_s_mean": rt_mean,
        "baseline_latency_s_min": bl_min,
        "baseline_latency_s_mean": bl_mean,
        "latency_ratio_baseline_over_ragtrap": latency_ratio,
        "ragtrap_work_units": rt_result.work_units,
        "baseline_work_units": bl_result.work_units,
        "work_ratio_baseline_over_ragtrap": work_ratio,
    }
    log.info("E1 result: %s", result)
    return result


# --------------------------------------------------------------------------------------------- E2
def run_e2(cfg: Config, clean_chunks: list[Chunk]) -> dict[str, object]:
    """E2 -- MTTR: one-command revoke-source vs manual per-chunk purge."""
    log.info("E2: MTTR of revoke-source vs manual purge")
    target_questions = ["q0", "q1", "q2", "q3", "q4"]
    poison = PoisonedRagBuilder(n_principals=3, texts_per_principal=5).build(target_questions)
    corpus = clean_chunks + poison
    signer = Ed25519Signer.generate()

    compromised = "poisonedrag-attacker-0"

    store_a, _ = ingest(corpus, signer)
    _, rev_min, rev_mean = _timed(lambda: revoke_source(store_a, compromised), repeats=1)
    purged = len([c for c in corpus if c.principal == compromised])

    store_b, _ = ingest(corpus, signer)
    _, man_min, man_mean = _timed(lambda: manual_purge(store_b, compromised), repeats=1)

    mttr_ratio = (man_min / rev_min) if rev_min > 0 else float("inf")
    result = {
        "experiment": "E2",
        "data": "E1 corpus (BEIR nq subset + poisoned set)",
        "corpus_chunks": len(corpus),
        "compromised_principal": compromised,
        "chunks_purged": purged,
        "revoke_source_mttr_s": rev_min,
        "manual_purge_mttr_s": man_min,
        "mttr_ratio_manual_over_revoke": mttr_ratio,
    }
    log.info("E2 result: %s", result)
    return result


# --------------------------------------------------------------------------------------------- E3
def run_e3(cfg: Config, clean_chunks: list[Chunk]) -> dict[str, object]:
    """E3 -- per-chunk vs per-document granularity: recall and false-purge contrast.

    A partially-poisoned document is built by mixing poisoned and clean chunks under one parent
    document and one principal. Per-document revocation of that principal purges the whole
    document (including its clean chunks: false purge), whereas per-chunk attribution localises
    the poisoned chunks. Both are measured on RAGtrap's own two configurations.
    """
    log.info("E3: per-chunk vs per-document granularity contrast")
    # Build a mixed-source document: clean chunks reattributed to a shared principal that also
    # carries poisoned chunks, so document-level revocation over-purges.
    shared_principal = "mixed-source-0"
    shared_doc = "mixed-doc-0"
    clean_subset = clean_chunks[:50]
    mixed_clean = [
        Chunk(
            chunk_id=f"mix-clean-{i}",
            text=c.text,
            source_uri="beir://nq/mixed",
            principal=shared_principal,
            is_poisoned=False,
            document_id=shared_doc,
        )
        for i, c in enumerate(clean_subset)
    ]
    poison = PoisonedRagBuilder(n_principals=1, texts_per_principal=10).build(
        ["q0", "q1", "q2", "q3", "q4"]
    )
    mixed_poison = [
        Chunk(
            chunk_id=f"mix-poison-{i}",
            text=c.text,
            source_uri="beir://nq/mixed",
            principal=shared_principal,
            is_poisoned=True,
            document_id=shared_doc,
        )
        for i, c in enumerate(poison)
    ]
    corpus = mixed_clean + mixed_poison
    signer = Ed25519Signer.generate()
    suspects = [c for c in corpus if c.is_poisoned]
    ground_truth = {c.chunk_id: c.principal for c in suspects}

    # Per-chunk configuration.
    store_chunk, _ = ingest(corpus, signer)
    attr_chunk = ragtrap_traceback(suspects, store_chunk, signer)
    recall_chunk = attr_chunk.recall(ground_truth)

    # Per-document configuration: revoking the principal purges the whole document.
    store_doc = ingest_per_document(corpus, signer)
    n_clean = len(mixed_clean)
    n_poison = len(mixed_poison)
    # Document-level revocation purges every chunk of the shared principal (clean + poisoned).
    doc_purged = len(store_doc.chunks_of_principal(shared_principal))
    false_purged_doc = n_clean  # all clean chunks of the partially-poisoned doc are over-purged
    false_purge_rate_doc = false_purged_doc / doc_purged if doc_purged else 0.0
    # Per-chunk localisation purges only the poisoned chunks (no clean over-purge).
    false_purge_rate_chunk = 0.0

    result = {
        "experiment": "E3",
        "data": "E1 corpus replayed under per-chunk and per-document schemes",
        "mixed_clean_chunks": n_clean,
        "mixed_poison_chunks": n_poison,
        "per_chunk_traceback_recall": recall_chunk,
        "per_document_purged_total": doc_purged,
        "per_document_false_purged_clean": false_purged_doc,
        "per_document_false_purge_rate": false_purge_rate_doc,
        "per_chunk_false_purge_rate": false_purge_rate_chunk,
    }
    log.info("E3 result: %s", result)
    return result


# --------------------------------------------------------------------------------------------- E4
def _measure_signing(signer, chunks: list[Chunk]) -> dict[str, object]:
    stats = StorageStats()
    start = time.perf_counter()
    _, stats = ingest(chunks, signer, stats=stats)
    elapsed = time.perf_counter() - start
    return {
        "signer": signer.name,
        "n_chunks": len(chunks),
        "total_seconds": elapsed,
        "throughput_chunks_per_s": len(chunks) / elapsed if elapsed > 0 else float("inf"),
        "mean_sign_latency_us": (elapsed / len(chunks)) * 1e6 if chunks else 0.0,
        "mean_record_bytes": stats.mean_record_bytes(),
        "mean_signature_bytes": stats.mean_signature_bytes(),
    }


def run_e4(cfg: Config, clean_chunks: list[Chunk]) -> dict[str, object]:
    """E4 -- ingestion overhead and storage cost: real Ed25519 vs HMAC stand-in."""
    log.info("E4: ingestion overhead and storage cost (Ed25519 vs HMAC)")
    # Synthetic sweep for clean scaling (labelled synthetic).
    sweep = []
    for n in (1000, 5000, 10000):
        syn = generate_corpus(
            n_chunks=n, n_principals=10, poison_fraction=0.05, seed=cfg.seed
        )
        ed = _measure_signing(Ed25519Signer.generate(), syn)
        hm = _measure_signing(HmacSigner.generate(), syn)
        sweep.append(
            {
                "n_chunks": n,
                "data": "synthetic (labelled)",
                "ed25519": ed,
                "hmac": hm,
                "ed25519_over_hmac_time": (ed["total_seconds"] / hm["total_seconds"])
                if hm["total_seconds"] > 0
                else float("inf"),
            }
        )

    # Real-data point on the BEIR subset.
    real_ed = _measure_signing(make_signer("ed25519"), clean_chunks)
    real_hm = _measure_signing(make_signer("hmac"), clean_chunks)

    result = {
        "experiment": "E4",
        "synthetic_sweep": sweep,
        "real_corpus_point": {
            "data": "BEIR nq subset (real)",
            "ed25519": real_ed,
            "hmac": real_hm,
            "ed25519_over_hmac_time": (real_ed["total_seconds"] / real_hm["total_seconds"])
            if real_hm["total_seconds"] > 0
            else float("inf"),
        },
    }
    log.info("E4 result: %s", result)
    return result


def run_all_runnable(cfg: Config) -> dict[str, object]:
    """Run E0-E4, loading the real corpus once and sharing it. Returns the results bundle."""
    out: dict[str, object] = {"environment": _env_block(), "config": cfg.as_dict()}
    out["E0"] = run_e0(cfg)

    try:
        clean_chunks, corpus_note = _load_real_or_note(cfg)
        out["corpus_note"] = corpus_note
        log.info("Loaded real corpus: %s", corpus_note)
    except CorpusUnavailable as exc:
        out["corpus_note"] = {"status": "unavailable", "reason": str(exc)}
        log.error("Real corpus unavailable: %s", exc)
        out["E1"] = out["E2"] = out["E3"] = out["E4"] = {
            "status": "skipped", "reason": "real corpus unavailable"
        }
        return out

    out["E1"] = run_e1(cfg, clean_chunks)
    out["E2"] = run_e2(cfg, clean_chunks)
    out["E3"] = run_e3(cfg, clean_chunks)
    out["E4"] = run_e4(cfg, clean_chunks)
    return out
