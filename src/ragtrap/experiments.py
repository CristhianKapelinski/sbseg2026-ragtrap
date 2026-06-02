"""E0 instrument validation (the deterministic correctness property).

E0 establishes that the instrument is correct before any real-data measurement: on a labelled
synthetic corpus, every signed record verifies, a tampered message is rejected, hash-keyed
traceback recovers the injected attribution exactly, and ``revoke-source`` purges exactly the
targeted principal's chunks and no others. This is a by-construction correctness guarantee, not a
statistical detection rate, and is framed as such.

The real, non-circular experiments on third-party PoisonedRAG / RAGOrigin data live in the
``ragtrap.realeval`` / ``ragtrap.realeval3`` / ``ragtrap.scaling`` / ``ragtrap.asr`` modules and
are driven by the scripts under ``scripts/``; ``run_all_runnable`` reports E0 plus the resolved
configuration and environment.
"""

from __future__ import annotations

import platform
import sys

from .config import Config
from .gate import ingest, verify_record
from .logging_setup import get_logger
from .revocation import revoke_source
from .signing import Ed25519Signer
from .synthetic import generate_corpus
from .traceback import ragtrap_traceback

log = get_logger()


def _env_block() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
    }


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
    suspects = [c for c in chunks if c.is_poisoned]
    ground_truth = {c.chunk_id: c.principal for c in suspects}
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


def run_all_runnable(cfg: Config) -> dict[str, object]:
    """Report E0 plus the resolved configuration and environment.

    The real, non-circular experiments (E1 traceback head-to-head, E2 MTTR scaling, E3
    granularity, E4 overhead, E5 attack-success) are run by the dedicated scripts on the pinned
    third-party datasets; this function provides the instrument-validation correctness property.
    """
    out: dict[str, object] = {"environment": _env_block(), "config": cfg.as_dict()}
    out["E0"] = run_e0(cfg)
    return out
