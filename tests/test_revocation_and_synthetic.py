"""Tests for revocation correctness and the synthetic generator's labelled invariants."""

from __future__ import annotations

import pytest

from ragtrap.gate import ingest
from ragtrap.revocation import manual_purge, revoke_source
from ragtrap.signing import Ed25519Signer
from ragtrap.synthetic import generate_corpus


def test_revoke_source_purges_exactly_target_principal() -> None:
    chunks = generate_corpus(
        n_chunks=100, n_principals=5, poison_fraction=0.2, seed=7, poisoned_principals=1
    )
    signer = Ed25519Signer.generate()
    store, _ = ingest(chunks, signer)
    expected = store.chunks_of_principal("attacker-0")
    before = len(store)
    result = revoke_source(store, "attacker-0")
    assert set(result.purged_chunk_ids) == expected
    assert len(store) == before - len(expected)
    # No chunk of any other principal was removed.
    assert all(r.principal != "attacker-0" for r in store.records.values())


def test_revoke_and_manual_purge_remove_the_same_chunks() -> None:
    chunks = generate_corpus(
        n_chunks=100, n_principals=5, poison_fraction=0.2, seed=7, poisoned_principals=1
    )
    signer = Ed25519Signer.generate()
    store_a, _ = ingest(chunks, signer)
    store_b, _ = ingest(chunks, signer)
    a = revoke_source(store_a, "attacker-0")
    b = manual_purge(store_b, "attacker-0")
    assert set(a.purged_chunk_ids) == set(b.purged_chunk_ids)


def test_revoke_scans_fewer_than_manual() -> None:
    chunks = generate_corpus(
        n_chunks=200, n_principals=8, poison_fraction=0.1, seed=11, poisoned_principals=1
    )
    signer = Ed25519Signer.generate()
    store_a, _ = ingest(chunks, signer)
    store_b, _ = ingest(chunks, signer)
    rev = revoke_source(store_a, "attacker-0")
    man = manual_purge(store_b, "attacker-0")
    # Batch revocation enumerates only the principal's chunks; manual scans the whole corpus.
    assert rev.scanned_chunks < man.scanned_chunks
    assert man.scanned_chunks == 200


def test_synthetic_poison_only_attributed_to_attacker() -> None:
    chunks = generate_corpus(
        n_chunks=100, n_principals=4, poison_fraction=0.25, seed=3, poisoned_principals=1
    )
    for c in chunks:
        if c.is_poisoned:
            assert c.principal.startswith("attacker-")
            assert c.source_uri.startswith("synthetic://")
        else:
            assert not c.principal.startswith("attacker-")


def test_synthetic_validates_arguments() -> None:
    with pytest.raises(ValueError):
        generate_corpus(n_chunks=0, n_principals=2, poison_fraction=0.1, seed=1)
    with pytest.raises(ValueError):
        generate_corpus(n_chunks=10, n_principals=2, poison_fraction=2.0, seed=1)
    with pytest.raises(ValueError):
        generate_corpus(
            n_chunks=10, n_principals=2, poison_fraction=0.1, seed=1, poisoned_principals=5
        )
