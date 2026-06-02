"""Real BEIR ``nq`` passage-corpus loading (the clean substrate).

The clean substrate is the BEIR ``nq`` (Natural Questions) passage corpus, the exact corpus
PoisonedRAG and RAGOrigin evaluate on, pulled from the Hugging Face mirror ``BeIR/nq`` (the
``corpus`` configuration). The full corpus is 2,681,468 passages; a passage cap may be set for a
bounded run. The exact passages used are pinned by a content digest in the run manifest.

The *attack* is never authored here. Poisoned passages come from the released PoisonedRAG
adversarial set and the released RAGOrigin attack-feedback (see :mod:`ragtrap.realdata`), so the
evaluation is non-circular: the detector under test does not produce the attack it is scored on.

If ``datasets`` is unavailable or the network cannot be reached, loading raises a typed
:class:`CorpusUnavailable` so the caller can report the condition instead of fabricating data.
"""

from __future__ import annotations

import os

from .records import Chunk


class CorpusUnavailable(RuntimeError):
    """Raised when the real corpus cannot be obtained (no network / no `datasets`)."""


def load_beir_nq_passages(
    *,
    cap: int,
    dataset: str = "nq",
    hf_revision: str = "main",
) -> list[tuple[str, str, str]]:
    """Load up to ``cap`` BEIR passages as (passage_id, title, text) tuples.

    Uses the Hugging Face ``datasets`` library and the ``BeIR/<dataset>`` mirror, streaming so the
    full multi-million-passage corpus is never materialised. Raises :class:`CorpusUnavailable`
    if the dependency or network is missing, so the caller never silently fabricates a corpus.
    """
    if cap <= 0:
        raise ValueError("cap must be positive")
    # Force the standard HTTP backend: the optional xet backend can trigger a thread-state
    # race during interpreter shutdown after streaming, which would corrupt an otherwise clean
    # run. Setting this before importing `datasets` keeps loading deterministic and offline-safe.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from datasets import load_dataset
    except ImportError as exc:  # optional `data` extra not installed
        raise CorpusUnavailable(
            "the `datasets` package is required to load the real BEIR corpus; "
            "install the 'data' extra (pip install .[data])"
        ) from exc

    try:
        stream = load_dataset(
            f"BeIR/{dataset}",
            "corpus",
            split="corpus",
            streaming=True,
            revision=hf_revision,
        )
    except Exception as exc:  # noqa: BLE001 -- network / dataset resolution failure
        raise CorpusUnavailable(f"could not load BeIR/{dataset} corpus: {exc}") from exc

    passages: list[tuple[str, str, str]] = []
    for row in stream:
        pid = str(row.get("_id", len(passages)))
        title = str(row.get("title", ""))
        text = str(row.get("text", ""))
        if not text:
            continue
        passages.append((pid, title, text))
        if len(passages) >= cap:
            break
    if not passages:
        raise CorpusUnavailable(f"BeIR/{dataset} corpus returned no passages")
    return passages


def passages_to_chunks(
    passages: list[tuple[str, str, str]],
    *,
    chunk_chars: int,
    overlap: int,
    principals: int = 8,
) -> list[Chunk]:
    """Turn loaded passages into clean chunks, attributing them to benign principals.

    Each passage is a parent document; benign principals model distinct trusted sources. The gate
    chunker is reused so chunking is identical to ingestion. ``principals`` benign sources are
    round-robined across passages.
    """
    from .gate import chunk_text

    chunks: list[Chunk] = []
    for i, (pid, title, text) in enumerate(passages):
        principal = f"beir-source-{i % max(1, principals)}"
        uri = f"beir://nq/{pid}"
        body = f"{title}\n{text}" if title else text
        chunks.extend(
            chunk_text(
                body,
                chunk_chars=chunk_chars,
                overlap=overlap,
                source_uri=uri,
                principal=principal,
                document_id=f"beir-{pid}",
                is_poisoned=False,
            )
        )
    return chunks
