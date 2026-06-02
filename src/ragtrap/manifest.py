"""Run manifest: maps each input to the exact bytes processed.

The manifest pins inputs by content digest and records the run's configuration, the signer's
public identity, the log path, and the dataset provenance (BEIR subset cap, Hugging Face
revision, poisoned-set digest). Writing it makes a result regenerable and auditable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_text
from .records import Chunk


@dataclass
class Manifest:
    """A JSON-serialisable record of everything that produced a run's outputs."""

    config: dict[str, object]
    signer_identity: str
    log_path: str
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inputs: dict[str, object] = field(default_factory=dict)

    def add_input(self, name: str, *, digest: str, description: str, **extra: object) -> None:
        """Record an input by content digest with a human-readable description."""
        self.inputs[name] = {"sha256": digest, "description": description, **extra}

    def add_corpus_input(self, name: str, chunks: list[Chunk], *, description: str) -> None:
        """Record a corpus input: digest over the concatenated chunk texts plus its size."""
        joined = "\n".join(c.text for c in chunks)
        self.add_input(
            name,
            digest=sha256_text(joined),
            description=description,
            n_chunks=len(chunks),
            n_principals=len({c.principal for c in chunks}),
            n_poisoned=sum(1 for c in chunks if c.is_poisoned),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "created_utc": self.created_utc,
            "config": self.config,
            "signer_identity": self.signer_identity,
            "log_path": self.log_path,
            "inputs": self.inputs,
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
