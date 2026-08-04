"""RAGtrap: per-chunk signed provenance, O(1) traceback, and source revocation for RAG.

RAGtrap is an ingestion gate for retrieval-augmented-generation (RAG) corpora. For each
ingested chunk it writes a cryptographically signed provenance record (source URI, principal,
chunk content hash, detector verdicts, timestamp) beside the corpus. This turns
poisoning traceback into an indexed content-hash lookup and enables one-command
revocation that batch-purges every chunk attributable to a compromised principal.

The runnable core (signing, datastore indexing, traceback, revocation) is pure cryptography
plus indexing work; it runs CPU-only and offline, with no LLM and no GPU.
"""

__version__ = "0.1.0"
