"""Source-indexed removal versus an in-memory full-corpus scan.

When a principal (source) is found to be compromised, RAGtrap revokes it in one operation:
``revoke_source`` reads the principal's chunk-id set from the side index (O(1) to enumerate) and
purges exactly those chunks, marking the principal revoked so future ingestion from it is
refused. This is the recovery/remediation layer that the surveyed prior work does not build.

The manual baseline (``manual_purge``) scans the in-memory corpus and removes chunks whose
principal matches. The comparison isolates indexed enumeration from scanning; it does not measure
end-to-end remediation in a persistent vector database.
"""

from __future__ import annotations

from dataclasses import dataclass

from .datastore import ProvenanceDatastore


@dataclass
class RevocationResult:
    """Outcome of a revocation: principal, chunks purged, and scan cost."""

    principal: str
    purged_chunk_ids: list[str]
    scanned_chunks: int

    @property
    def n_purged(self) -> int:
        return len(self.purged_chunk_ids)


def revoke_source(datastore: ProvenanceDatastore, principal: str) -> RevocationResult:
    """One-command batch purge of every chunk attributable to ``principal``.

    Enumeration is O(1) via the principal side index; removal is O(k) for k revoked chunks. No
    full-corpus scan is performed (``scanned_chunks`` is the size of the principal set only).
    """
    target_ids = sorted(datastore.chunks_of_principal(principal))
    for chunk_id in target_ids:
        datastore.remove_chunk(chunk_id)
    datastore.revoked_principals.add(principal)
    return RevocationResult(
        principal=principal, purged_chunk_ids=target_ids, scanned_chunks=len(target_ids)
    )


def purge_document(datastore: ProvenanceDatastore, document_id: str) -> RevocationResult:
    """Remove every chunk in one document, regardless of its recorded source."""
    target_ids = sorted(
        chunk_id
        for chunk_id, chunk in datastore.chunks.items()
        if chunk.document_id == document_id
    )
    for chunk_id in target_ids:
        datastore.remove_chunk(chunk_id)
    return RevocationResult(
        principal=document_id, purged_chunk_ids=target_ids, scanned_chunks=len(target_ids)
    )


def manual_purge(datastore: ProvenanceDatastore, principal: str) -> RevocationResult:
    """Manual baseline: scan the whole corpus to find and remove a principal's chunks.

    Models an operator without a provenance index. Every chunk in the corpus is inspected
    (``scanned_chunks`` equals the corpus size), reproducing the linear scan such an operator
    must perform. The datastore side indices are still kept consistent on removal.
    """
    scanned = 0
    to_remove: list[str] = []
    for chunk_id, record in list(datastore.records.items()):
        scanned += 1
        if record.principal == principal:
            to_remove.append(chunk_id)
    for chunk_id in to_remove:
        datastore.remove_chunk(chunk_id)
    datastore.revoked_principals.add(principal)
    return RevocationResult(
        principal=principal, purged_chunk_ids=sorted(to_remove), scanned_chunks=scanned
    )
