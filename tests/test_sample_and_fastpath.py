"""Guards for the fast reproduction path: the shipped frozen BEIR/nq sample and Exp. 2 contrast.

These run offline (no network, no model) and pin the structural claims the fast quickstart
reproduces, so a regression in the sample bytes or the granularity logic fails the test suite.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ragtrap.realdata import BEIR_NQ_SAMPLE_SHA256
from ragtrap.realeval3 import run_exp2_granularity

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = REPO_ROOT / "data" / "beir_nq_sample.parquet"


def test_frozen_sample_present_and_pinned():
    assert SAMPLE.exists(), f"frozen BEIR/nq sample missing at {SAMPLE}"
    digest = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert digest == BEIR_NQ_SAMPLE_SHA256, "sample bytes drifted from the pinned digest"


def test_exp2_false_purge_contrast_on_sample():
    pytest.importorskip("pyarrow")
    # A tiny synthetic poison pool is enough to exercise the per-chunk vs per-document contrast;
    # the real poison pool only changes the injected text, not the structural false-purge result.
    poison_pool = [f"adversarial passage {i} asserting a false fact." for i in range(20)]
    res = run_exp2_granularity(str(SAMPLE), poison_pool, n_documents=50, poison_per_doc=3)
    per_doc = res["per_document"]["false_purge_rate"]["point"]
    per_chunk = res["per_chunk"]["false_purge_rate"]["point"]
    # Per-chunk revocation never over-purges clean content; per-document always does on a
    # partially-poisoned document. This is the headline Exp. 2 contrast (0.00 vs ~0.52).
    assert per_chunk == 0.0
    assert per_doc > 0.3
    assert res["per_chunk"]["poison_recall"]["point"] == 1.0
