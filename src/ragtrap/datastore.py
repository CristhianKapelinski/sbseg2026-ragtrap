"""Provenance datastore: the signed-record index embedded in the vector store.

This module models the index a real vector store would carry alongside its embeddings. It is
deliberately a plain in-memory/JSON-backed structure so the experiments measure the *algorithmic*
cost of traceback and revocation, not the overhead of a particular vector database. The two
side indices are what make traceback constant-time:

* ``by_content_hash``: chunk content hash -> chunk_id, so a suspect chunk's text resolves to its
  signed record in O(1).
* ``by_principal``: principal -> set of chunk_ids, so revoking a compromised source enumerates
  exactly its chunks in O(k) for k revoked chunks, without scanning the corpus.

A document-granularity store (the per-document contrast for E3) reuses the same structure but is
populated with one signed record per parent document; trust then propagates to that document's
chunks. Both configurations are measured in-house; no external numbers are fabricated.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .records import Chunk, ProvenanceRecord


@dataclass
class ProvenanceDatastore:
    """In-memory signed-record index with O(1) traceback and O(k) revocation."""

    records: dict[str, ProvenanceRecord] = field(default_factory=dict)
    chunks: dict[str, Chunk] = field(default_factory=dict)
    by_content_hash: dict[str, str] = field(default_factory=dict)
    by_principal: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    revoked_principals: set[str] = field(default_factory=set)

    def put(self, chunk: Chunk, record: ProvenanceRecord) -> None:
        """Insert a chunk and its signed provenance record, updating the side indices."""
        self.records[chunk.chunk_id] = record
        self.chunks[chunk.chunk_id] = chunk
        self.by_content_hash[record.content_hash] = chunk.chunk_id
        self.by_principal[record.principal].add(chunk.chunk_id)

    def __len__(self) -> int:
        return len(self.records)

    def get_record(self, chunk_id: str) -> ProvenanceRecord | None:
        return self.records.get(chunk_id)

    def lookup_by_content_hash(self, content_hash: str) -> ProvenanceRecord | None:
        """O(1) resolution of a chunk's signed record from its content hash."""
        chunk_id = self.by_content_hash.get(content_hash)
        return self.records.get(chunk_id) if chunk_id is not None else None

    def chunks_of_principal(self, principal: str) -> set[str]:
        """O(1) access to the set of chunk ids attributed to a principal."""
        return set(self.by_principal.get(principal, set()))

    def remove_chunk(self, chunk_id: str) -> bool:
        """Remove a single chunk and its record, keeping the side indices consistent."""
        record = self.records.pop(chunk_id, None)
        if record is None:
            return False
        self.chunks.pop(chunk_id, None)
        if self.by_content_hash.get(record.content_hash) == chunk_id:
            del self.by_content_hash[record.content_hash]
        self.by_principal.get(record.principal, set()).discard(chunk_id)
        return True

    def to_json(self, path: Path) -> None:
        """Persist the datastore (records + chunks) so a run can be inspected/replayed."""
        payload = {
            "records": {cid: rec.to_dict() for cid, rec in self.records.items()},
            "chunks": {cid: vars(chunk) for cid, chunk in self.chunks.items()},
            "revoked_principals": sorted(self.revoked_principals),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
