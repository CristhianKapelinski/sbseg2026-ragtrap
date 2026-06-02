#!/usr/bin/env python3
"""Auto-fetch the exact BEIR `nq` passage subset used by the experiments and pin it.

A reviewer runs this once; it downloads the bounded subset (cap from ``RAGTRAP_BEIR_PASSAGE_CAP``,
default 5000), writes it to ``data/beir_nq_subset.jsonl``, and prints the content digest that the
run manifest pins. Nothing is fabricated: if the corpus cannot be reached, the script exits with
a clear message instead of writing placeholder data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ragtrap.config import load_config
from ragtrap.corpus import CorpusUnavailable, load_beir_nq_passages
from ragtrap.hashing import sha256_text


def main() -> int:
    cfg = load_config()
    cfg.ensure_dirs()
    out_path = cfg.data_dir / "beir_nq_subset.jsonl"
    try:
        passages = load_beir_nq_passages(
            cap=cfg.beir_passage_cap, dataset=cfg.beir_dataset, hf_revision=cfg.hf_revision
        )
    except CorpusUnavailable as exc:
        print(f"corpus unavailable: {exc}", file=sys.stderr)
        return 1

    lines = [json.dumps({"_id": pid, "title": title, "text": text}) for pid, title, text in passages]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    digest = sha256_text("\n".join(text for _, _, text in passages))
    print(f"wrote {len(passages)} passages to {out_path}")
    print(f"passage-text sha256: {digest}")
    print(f"dataset: BEIR/{cfg.beir_dataset}  revision: {cfg.hf_revision}  cap: {cfg.beir_passage_cap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
