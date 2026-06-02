"""Tests for the third-party data loaders, statistics, and non-circular evaluation logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragtrap.realdata import (
    DataIntegrityError,
    feedback_file_digest,
    load_poisonedrag,
    load_ragorigin_feedback,
)
from ragtrap.realeval import (
    ATTACKER_PRINCIPAL,
    ConfusionCounts,
    build_corpus_from_feedback,
    run_e1_ragtrap,
)
from ragtrap.stats import bootstrap_ci, wilson


def _write_feedback(path: Path) -> None:
    data = [
        {
            "question_id": "nq_0",
            "question": "q0",
            "correct_answer": "23",
            "target_answer": "20",
            "RAG_response": "the answer is 20",
            "context_texts": ["poison a", "poison b", "clean c", "clean d"],
            "context_labels": [True, True, False, False],
            "retrieval_scores": [0.9, 0.89, 0.5, 0.4],
        }
    ]
    path.write_text(json.dumps(data), encoding="utf-8")


def test_wilson_known_values():
    p = wilson(50, 100)
    assert abs(p.point - 0.5) < 1e-9
    assert p.low < 0.5 < p.high
    # perfect proportion: point 1.0, lower bound below 1.0
    perfect = wilson(20, 20)
    assert perfect.point == 1.0
    assert perfect.low < 1.0
    assert perfect.high == pytest.approx(1.0)


def test_wilson_zero_n():
    p = wilson(0, 0)
    assert p.point == 0.0 and p.low == 0.0 and p.high == 0.0


def test_bootstrap_ci_constant():
    ci = bootstrap_ci([2.0, 2.0, 2.0])
    assert abs(ci["point"] - 2.0) < 1e-9
    assert ci["ci_low"] <= ci["point"] <= ci["ci_high"]


def test_confusion_metrics():
    c = ConfusionCounts()
    c.add(True, True)  # tp
    c.add(True, False)  # fp
    c.add(False, True)  # fn
    c.add(False, False)  # tn
    m = c.metrics()
    assert m["tp"] == 1 and m["fp"] == 1 and m["fn"] == 1 and m["tn"] == 1
    assert abs(m["recall"]["point"] - 0.5) < 1e-9
    assert abs(m["precision"]["point"] - 0.5) < 1e-9
    assert abs(m["fpr"]["point"] - 0.5) < 1e-9


def test_load_feedback_and_digest_mismatch(tmp_path):
    fp = tmp_path / "fb.json"
    _write_feedback(fp)
    fb = load_ragorigin_feedback(fp)
    assert len(fb) == 1
    assert fb[0].contexts[0].is_poison is True
    assert fb[0].contexts[2].is_poison is False
    # digest verification rejects a wrong pin
    with pytest.raises(DataIntegrityError):
        load_ragorigin_feedback(fp, expected_sha256="deadbeef")
    assert feedback_file_digest(fp) == feedback_file_digest(fp)


def test_build_corpus_attributes_principals(tmp_path):
    fp = tmp_path / "fb.json"
    _write_feedback(fp)
    fb = load_ragorigin_feedback(fp)
    corpus = build_corpus_from_feedback(fb)
    attacker = [c for c in corpus if c.principal == ATTACKER_PRINCIPAL]
    benign = [c for c in corpus if c.principal != ATTACKER_PRINCIPAL]
    assert all(c.is_poisoned for c in attacker)
    assert all(not c.is_poisoned for c in benign)
    assert len(attacker) == 2 and len(benign) == 2


def test_ragtrap_e1_by_construction_and_drift(tmp_path):
    fp = tmp_path / "fb.json"
    _write_feedback(fp)
    fb = load_ragorigin_feedback(fp)
    # no drift: exact-hash recovery is a deterministic correctness property -> recall 1.0
    clean = run_e1_ragtrap(fb, top_k=4, drift_fraction=0.0, repeats=2)
    assert clean["detection"]["recall"]["point"] == 1.0
    assert clean["detection"]["precision"]["point"] == 1.0
    assert clean["detection"]["fpr"]["point"] == 0.0
    # full drift on poison -> all poison suspects miss the hash -> recall 0, precision still exact
    drift = run_e1_ragtrap(fb, top_k=4, drift_fraction=1.0, repeats=1, seed=7)
    assert drift["n_drifted"] >= 1
    assert drift["detection"]["recall"]["point"] < 1.0
    # precision is exact even under drift (no false positives from a hash match)
    prec = drift["detection"]["precision"]
    assert prec is None or prec["point"] == 1.0


def test_load_poisonedrag(tmp_path):
    fp = tmp_path / "nq.json"
    fp.write_text(
        json.dumps(
            {
                "test1": {
                    "id": "test1",
                    "question": "q",
                    "correct answer": "a",
                    "incorrect answer": "b",
                    "adv_texts": ["x", "y"],
                }
            }
        ),
        encoding="utf-8",
    )
    # unknown dataset name -> no pinned digest -> no integrity check
    entries = load_poisonedrag(fp, dataset="unknown")
    assert len(entries) == 1 and entries[0].adv_texts == ["x", "y"]
