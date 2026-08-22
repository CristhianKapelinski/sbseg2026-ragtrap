# RAGtrap: Documentation

This document records the problem RAGtrap addresses, its narrowed contribution, its design, and,
for each experiment, the exact command, the real captured output, and its interpretation. Every
number here is produced by code executed on the stated third-party datasets; none is estimated or
fabricated. Small inputs are checksum-pinned, and the full BEIR snapshot uses an immutable
revision. The attack, the dense retrieval, the ground-truth labels, and both baselines are
third-party artifacts that RAGtrap did not author, so the suspect set used for attribution is
independent of the mechanism under test.

## 1. Problem

Retrieval-augmented generation (RAG) pipelines ground a language model on passages fetched from an
external corpus, but that corpus is ingested from untrusted web and document sources with no trust
boundary at admission. Corpus poisoning is cheap and effective: PoisonedRAG injects a handful of
malicious passages per target question to reach ~90% attack success against a knowledge base of
millions of texts, and web-scale poisoning of the very sources RAG ingests is practical. Standards
(OWASP LLM04:2025) now call for data provenance and quarantine.

The operational question this artifact answers: once a source is found compromised, how quickly
and how precisely can an operator (a) attribute the poisoned chunks to their source and (b) purge
every chunk from that source, without re-running an expensive, language-model-driven forensic
procedure?

## 2. Narrowed contribution

The idea of an ingestion gate is not itself novel. RAGtrap's contribution is the recovery layer
that no surveyed tool builds. RAGtrap
claims the conjunction of:

1. **Per-chunk signed provenance** with the chunk's own content hash and admitting detector
   verdicts. The prototype stores these records in memory; vector-database integration is future
   work.
2. **Real Ed25519 public-key signatures**, so provenance is non-repudiable and verifiable by any
   holder of the public key.
3. **Traceback as a single indexed content-hash lookup**, the structural alternative to
   re-retrieving and scoring suspects with a language model.
4. **One-command source revocation** that batch-purges every chunk of a compromised principal.

The forensic attributors RAGForensics (LLM-judge) and RAGOrigin (proxy-LLM responsibility scoring)
are accurate but reactive and pay many model calls per incident; both are run here as baselines on
identical suspects. Detection is explicitly out of scope as a contribution; ingestion detectors are
best-effort and complementary to query-time filters (GMTP, RAGPart/RAGMask). RAGtrap's value is
forensic and operational. RAGShield (Patil 2026, arXiv:2604.00387) is an orthogonal third-party
work: it verifies extracted numerical claims (dollar amounts, percentages) in government RAG text
against a cross-source registry; it does not attest provenance, attribute sources, or revoke, so it
is a complementary content-level check, not the closest prior work.

## 3. Design

RAGtrap is an ingestion gate: for each chunk it computes a SHA-256 content hash, runs a
best-effort detector suite, assembles a canonical byte string over the provenance tuple (chunk id,
source URI, principal, content hash, detector verdicts, timestamp, signer identity, granularity),
signs it (real Ed25519), and writes the signed record into the datastore. Two side indices make
traceback and revocation cheap: a content-hash index (chunk hash to matching chunk ids, one indexed
resolution) and a principal index (principal to its chunk-id set, O(k) revocation without a corpus
scan).

### 3.1 Module reference

The package is 23 modules under `src/ragtrap/`, one per concern. Every signature below is the
one in the code; `*` marks the start of keyword-only arguments, as in the source.

**Foundations — configuration, logging, hashing.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `config` | `Config` (frozen dataclass) | Resolved run parameters: `repo_root`, `data_dir`, `logs_dir`, `results_dir`, `signer`, `chunk_chars`, `chunk_overlap`, `beir_dataset`, `beir_passage_cap`, `hf_revision`, `seed` | environment variables prefixed `RAGTRAP_` | immutable config object |
| | `Config.ensure_dirs() -> None` | Create `data_dir`, `logs_dir`, `results_dir` if absent | — | — |
| | `Config.as_dict() -> dict[str, object]` | JSON-serialisable view for the log and the manifest | — | plain dict |
| | `load_config() -> Config` | The single entry point every script uses to read configuration | environment | `Config` |
| `logging_setup` | `setup_logging(logs_dir: Path, level: int = logging.INFO) -> tuple[logging.Logger, Path]` | Attach a console and a file handler; idempotent within a process | log directory | the logger and the path of `run-<timestamp>.log` |
| | `get_logger() -> logging.Logger` | Return the shared `ragtrap` logger | — | logger |
| | `utc_timestamp() -> str` | Filesystem-safe UTC stamp used in the log filename | — | `YYYYmmddTHHMMSSZ` |
| `hashing` | `sha256_text(text: str) -> str` | The canonical content hash: SHA-256 over UTF-8 bytes. Used for chunk hashes, manifest digests, and the bytes that are signed | string | hex digest |
| | `sha256_bytes(data: bytes) -> str` | Same digest over raw bytes | bytes | hex digest |
| | `sha256_file(path: Path, chunk_size: int = 1 << 20) -> str` | Digest of a file read in bounded blocks | path | hex digest |

**The signed record — schema, canonical encoding, signing backends.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `records` | `Chunk` (frozen dataclass) | The unit of ingestion: `chunk_id`, `text`, `source_uri`, `principal`, `is_poisoned`, `document_id`. `is_poisoned` is an evaluation label and is never read at ingestion time | — | — |
| | `ProvenanceRecord` (frozen dataclass) | The sealed artifact: `chunk_id`, `source_uri`, `principal`, `content_hash`, `detector_verdicts`, `timestamp`, `signer_name`, `signer_identity`, `signature_hex`, `granularity` | — | — |
| | `ProvenanceRecord.signed_payload() -> dict[str, object]` | The fields the signature covers, i.e. every field except `signature_hex` | — | dict |
| | `canonical_message(payload: dict[str, object]) -> bytes` | Deterministic encoding of a payload (JSON, sorted keys, compact separators) so signing and verification agree across processes | signed payload | message bytes |
| | `StorageStats.add(record: ProvenanceRecord) -> None` | Accumulate record and signature sizes for the scaling sweep; `mean_record_bytes()` / `mean_signature_bytes()` read them back | record | — |
| `signing` | `Signer` (ABC) | The backend interface: `name`, `sign(message: bytes) -> bytes`, `verify(message: bytes, signature: bytes) -> bool`, `public_identity() -> str` | — | — |
| | `Ed25519Signer.generate() -> Ed25519Signer` | The default backend. Generates a fresh keypair; the private key never leaves the process and is never written to disk | — | signer |
| | `Ed25519Signer.public_key_hex() -> str` | The raw 32-byte verification key as hex; `public_identity()` prefixes it with `ed25519:` | — | hex string |
| | `HmacSigner.generate() -> HmacSigner` | The symmetric HMAC-SHA256 stand-in, present only to price real public-key crypto in the scaling sweep. Not a deployment mode: the verifier would need the secret | — | signer |
| | `make_signer(name: str) -> Signer` | Factory by backend name; raises `ValueError` on anything but `ed25519` or `hmac` | `"ed25519"` / `"hmac"` | `Signer` |
| `detectors` | `Detector` (type alias) | `Callable[[str], str]`: text in, verdict string out | — | — |
| | `entropy_detector(text: str, low: float = 2.0, high: float = 6.5) -> str` | Flag character entropy outside a plausible natural-language band | chunk text | `"benign"` / `"suspect"` / `"error"` |
| | `repetition_detector(text: str, threshold: float = 0.5) -> str` | Flag text dominated by one repeated token | chunk text | `"benign"` / `"suspect"` / `"error"` |
| | `default_detectors() -> dict[str, Detector]` | The default suite, keyed `entropy` and `repetition` | — | name → detector |
| | `run_detectors(text: str, detectors: dict[str, Detector]) -> dict[str, str]` | Run the suite and collect verdicts. A detector that raises yields `"error"`, so one bad chunk cannot abort ingestion | text, suite | name → verdict |

**The datastore and its two side indices.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `datastore` | `ProvenanceDatastore` (dataclass) | The in-memory store. `records: dict[str, ProvenanceRecord]` and `chunks: dict[str, Chunk]` keyed by chunk id, plus the two indices that make recovery cheap: `by_content_hash: dict[str, set[str]]` and `by_principal: dict[str, set[str]]`, and the `revoked_principals: set[str]` deny list | — | — |
| | `put(chunk: Chunk, record: ProvenanceRecord) -> None` | Insert and update both indices. Raises `ValueError` if the record's principal is already revoked, so a revoked source cannot re-enter the corpus | chunk + record | — |
| | `lookup_by_content_hash(content_hash: str) -> ProvenanceRecord \| None` | The traceback primitive. Returns a record only when **every** record carrying those bytes agrees on one principal; ambiguous bytes return `None` rather than a guess | hex digest | record or `None` |
| | `chunks_of_principal(principal: str) -> set[str]` | The revocation primitive: enumerate a source's chunk ids from the index, with no corpus scan | principal | copy of the chunk-id set |
| | `remove_chunk(chunk_id: str) -> bool` | Delete one chunk and its record, keeping both indices consistent (an emptied hash bucket is dropped) | chunk id | `True` if it existed |
| | `get_record(chunk_id: str) -> ProvenanceRecord \| None`, `__len__() -> int`, `to_json(path: Path) -> None` | Direct record access, corpus size, and a dump of records + chunks + revoked principals for inspection | — | — |

**The ingestion gate.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `gate` | `chunk_text(text, *, chunk_chars, overlap, source_uri, principal, document_id, is_poisoned=False) -> list[Chunk]` | Split a document into overlapping character windows, one `Chunk` each, ids `<document_id>::c<i>`. `overlap` is clamped so the window always advances | document text + provenance fields | chunk list |
| | `sign_chunk(chunk, signer, detectors, *, granularity="chunk", timestamp=None) -> ProvenanceRecord` | The core of the gate: hash the text, run the detectors, build the canonical message, sign it | chunk, `Signer`, detector suite | signed record |
| | `verify_record(record: ProvenanceRecord, signer: Signer) -> bool` | Re-derive the canonical message from the record and check its signature | record, signer | verdict |
| | `ingest(chunks, signer, *, datastore=None, detectors=None, stats=None) -> tuple[ProvenanceDatastore, StorageStats]` | Per-chunk ingestion, the RAGtrap configuration. Never drops a chunk on a detector verdict: an undetected poisoned chunk still ends up attributable and revocable | chunk iterable, signer | populated store and size stats |
| | `ingest_per_document(chunks, signer, *, datastore=None, detectors=None) -> ProvenanceDatastore` | The document-granularity contrast for Exp. 2: one hash and one signature per parent document, inherited by all its chunks | chunk iterable, signer | populated store |

**Recovery — traceback and revocation.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `traceback` | `ragtrap_traceback(suspects: list[Chunk], datastore: ProvenanceDatastore, signer: Signer) -> AttributionResult` | One content-hash lookup per suspect, then a signature check on the record found. No re-retrieval and no model call. A lookup miss, an ambiguous hash, or a failed verification yields `None` for that suspect | suspect chunks, store, signer | `AttributionResult` |
| | `AttributionResult` (dataclass) | `attributions: dict[str, str \| None]` (suspect id → principal), `work_units: int` (the auditable lookup count), `verification_failures: list[str]` (tamper evidence) | — | — |
| | `AttributionResult.recall(ground_truth: dict[str, str]) -> float` | Fraction of suspects attributed to their true principal | id → true principal | recall |
| `revocation` | `revoke_source(datastore, principal) -> RevocationResult` | The main operation: read the principal's chunk ids from the index, remove exactly those, and add the principal to `revoked_principals`. `scanned_chunks` is the size of the principal's own set, not the corpus | store, principal | `RevocationResult` |
| | `manual_purge(datastore, principal) -> RevocationResult` | The scan baseline: walk every record and remove matches. `scanned_chunks` equals the corpus size, which is what makes the comparison a scan-versus-index one | store, principal | `RevocationResult` |
| | `purge_document(datastore, document_id) -> RevocationResult` | The document-level contrast: remove every chunk of one document whatever its recorded source. This is what over-purges clean content in Exp. 2 | store, document id | `RevocationResult` |
| | `RevocationResult` (dataclass) | `principal`, `purged_chunk_ids`, `scanned_chunks`, and the `n_purged` property | — | — |

**Data loading — synthetic, BEIR, and the third-party attack files.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `synthetic` | `generate_corpus(*, n_chunks, n_principals, poison_fraction, seed, words_per_chunk=60, poisoned_principals=1) -> list[Chunk]` | Seeded labelled corpus for the instrument check. Poisoned chunks go only to `attacker-<i>` principals, so a revoke has a known-correct expected purge set; every `source_uri` starts `synthetic://` so it cannot be mistaken for real data | sizes and seed | labelled chunks |
| `corpus` | `load_beir_nq_passages(*, cap, dataset="nq", hf_revision="main") -> list[tuple[str, str, str]]` | Stream up to `cap` BEIR passages as (id, title, text). Raises `CorpusUnavailable` when `datasets` or the network is missing, rather than fabricating a corpus | cap, dataset, revision | passage tuples |
| | `passages_to_chunks(passages, *, chunk_chars, overlap, principals=8) -> list[Chunk]` | Turn passages into clean chunks round-robined over benign principals, reusing `gate.chunk_text` so chunking matches ingestion | passages | chunks |
| `realdata` | `load_poisonedrag(path, *, dataset="nq") -> list[PoisonedRagEntry]` | Load the released PoisonedRAG adversarial passages; verifies the file against `POISONEDRAG_SHA256[dataset]` and raises `DataIntegrityError` on mismatch | file path | entries with `adv_texts` |
| | `load_ragorigin_feedback(path, *, expected_sha256=None) -> list[FeedbackQuestion]` | Load the released RAGOrigin feedback: per question, the top-100 e5-retrieved contexts with third-party poison labels and retrieval scores | file path, pinned digest | questions with `contexts` |
| | `feedback_file_digest(path) -> str` | The measured digest, for the run manifest | path | hex digest |
| | `FeedbackQuestion` / `FeedbackContext` (frozen dataclasses) | `question_id`, `question`, `correct_answer`, `target_answer`, `rag_response`, `contexts`; each context carries `text`, `is_poison`, `retrieval_score`, `rank` | — | — |
| | `POISONEDRAG_SHA256`, `RAGORIGIN_FEEDBACK_SHA256`, `BEIR_NQ_SAMPLE_SHA256` | The pinned digests of every third-party input, including the frozen sample shipped in `data/` | — | — |

**Experiments.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `experiments` | `run_check(cfg: Config) -> dict[str, object]` | The instrument check: 200 synthetic chunks over 5 principals; asserts that every record verifies, that a tampered message is rejected, that traceback recall is 1.0, and that revoking `attacker-0` purges exactly its chunks. Sets `instrument_valid` | `Config` | result dict |
| | `run_all_runnable(cfg: Config) -> dict[str, object]` | The check plus the resolved config and the environment block | `Config` | result dict |
| `realeval` | `build_corpus_from_feedback(feedback, *, benign_principals=32) -> list[Chunk]` | Assign every retrieved context a source before ingestion: poisoned contexts to `ATTACKER_PRINCIPAL`, clean ones round-robined over benign principals | feedback questions | chunks |
| | `run_exp1_ragtrap(feedback, *, top_k=5, drift_fraction=0.0, seed=1337, repeats=5) -> dict[str, object]` | Exp. 1, RAGtrap side: ingest the corpus, take the top-`k` contexts per question as suspects, optionally paraphrase a fraction of the poisoned ones (drift), and time `ragtrap_traceback` over `repeats` passes | feedback | detection metrics, attribution recall, latency, work units |
| | `run_exp1_baseline_judge(feedback, judge, *, top_k=5, max_questions=None) -> dict[str, object]` | Exp. 1, RAGForensics baseline: one judge call per context over the identical suspects | feedback, `LocalLLMJudge` | same metric shape plus `model_calls` |
| | `run_exp1_baseline_ragorigin(feedback, *, proxy_model="Qwen/Qwen2.5-3B-Instruct", top_k=10, device="cuda", dtype="float16", max_questions=None) -> dict[str, object]` | Exp. 1, RAGOrigin baseline: per-suspect answer loss and question loss from a local proxy plus the released retrieval score, z-normalised, averaged, then K-means thresholded per question. Two forward passes per context | feedback | same metric shape plus `model_calls` |
| | `ConfusionCounts` (dataclass) | `tp` / `fp` / `tn` / `fn` with `add(predicted_poison, truth_poison)` and `metrics()`, which returns recall, precision, FPR and FNR each as a Wilson interval. All three attributors report through it, so their numbers are comparable | — | — |
| `realeval3` | `run_exp2_granularity(parquet_path, poison_pool, *, n_documents=200, poison_per_doc=3, min_clean_chunks=3, seed=1337, passages=None) -> dict[str, object]` | Exp. 2, the main claim: build mixed documents from real BEIR passages plus injected PoisonedRAG passages under one `compromised-source`, then contrast `purge_document` against `revoke_source` and report each false-purge rate with a Wilson CI | parquet path, poison pool | per-document and per-chunk blocks |
| | `sweep_exp2_poison_per_doc(parquet_path, poison_pool, *, n_documents=200, poison_per_doc_values=(1, 2, 3, 5), min_clean_chunks=3, seed=1337) -> dict[str, object]` | Re-run that contrast across injection budgets on one fixed, once-shuffled passage sample, so only `poison_per_doc` varies | parquet path, poison pool | one point per budget |
| `scaling` | `iter_beir_parquet(parquet_path, *, limit, batch_size=50000)` | Generator over (id, title, text) straight from the BEIR parquet, in file order, so a prefix is deterministic | parquet path, limit | passage tuples |
| | `poison_chunks_from_poisonedrag(entries, *, n_principals=5) -> list[Chunk]` | Turn released adversarial passages into poisoned chunks spread over attacker principals | PoisonedRAG entries | chunks |
| | `run_scale_point(parquet_path, poison, *, n_clean_passages, chunk_chars=512, overlap=64, revoke_principal=None, repeats=5) -> ScalePoint` | One point of the scaling sweep: ingest a corpus prefix plus the poison, time per-chunk signing, then time `revoke_source` against `manual_purge`, restoring the purged chunks in place between repeats instead of deep-copying the store | parquet path, poison chunks, size | `ScalePoint` |
| | `ScalePoint` (dataclass) | `n_clean_passages`, `n_chunks`, `n_poison_chunks`, `sign_latency_us`, `throughput_per_s`, `mean_record_bytes`, `revoke_mttr_s`, `manual_mttr_s`, `mttr_ratio`, `revoked_chunks`, `passage_prefix_sha256`; `as_dict()` for the results JSON | — | — |
| | `measure_signing_backends(parquet_path, *, n_clean_passages, chunk_chars=512, overlap=64) -> dict[str, object]` | Price real Ed25519 against the HMAC stand-in over the same real chunks | parquet path, size | per-backend latency, throughput, record size |
| `llm_judge` | `LocalLLMJudge(model_name, *, device="cuda", max_new_tokens=200, dtype="float16")` | Serves the published RAGForensics judge from a local instruction-tuned model. **Note for the CPU path:** `dtype` decides the memory footprint. `scripts/run_check_exp2_exp3.py` passes `float32` whenever `--judge-device cpu` is used, which is what makes the CPU route of Claim \#3 far more memory-hungry than the GPU route — see the RAM figures in the README | model name, device, dtype | judge object |
| | `judge_contexts(question, answer, contexts) -> JudgeResult` | One greedy generation per context; returns `labels`, `n_calls`, `total_seconds`, `raw` | question, response, contexts | `JudgeResult` |
| | `judge_prompt(question, answer, corpus) -> str` | The verbatim upstream `judge_content_by_incorrect_answer` template | strings | prompt |
| | `parse_label(response_text: str) -> bool` | Parse the trailing `[Label: Yes\|No]` tag exactly as upstream, defaulting to `No` | model output | poisoned verdict |
| `asr` | `run_asr(feedback, judge, *, top_k=5, max_questions=None) -> dict[str, object]` | Exp. 3: feed the top-`k` retrieved contexts to the generation model and count how often the answer contains the attacker's target answer rather than the correct one | feedback, `LocalLLMJudge` | attack-success and correct-answer rates with Wilson CIs |

**Reporting.**

| Module | Function / class | Responsibility | In | Out |
|---|---|---|---|---|
| `stats` | `wilson(k: int, n: int, z: float = 1.96) -> Proportion` | The 95% Wilson score interval used for every proportion in the paper; well-behaved at 0, at 1, and for small N | successes, trials | `Proportion` with `point`, `low`, `high` and `as_dict()` |
| | `bootstrap_ci(values, *, reducer=None, n_boot=10000, z=0.95, seed=1337) -> dict[str, float]` | Seeded nonparametric bootstrap interval over repeated measurements | values | point and interval |
| `manifest` | `Manifest(config, signer_identity, log_path, ...)` | The audit record of a run | config dict, signer identity, log path | manifest object |
| | `add_input(name, *, digest, description, **extra) -> None` | Record one input by content digest | digest, description | — |
| | `add_corpus_input(name, chunks, *, description) -> None` | Record a corpus by the digest of its concatenated texts, with chunk, principal, and poison counts | chunk list | — |
| | `write(path: Path) -> None` | Serialise to `results/manifest.json` | path | file |
| `cli` | `main(argv: list[str] \| None = None) -> int` | Console entry point `ragtrap`, built by `build_parser()` | argv | exit code |
| | `cmd_selftest` | `ragtrap selftest`: run `experiments.run_check` and exit non-zero unless `instrument_valid` | — | JSON on stdout |
| | `cmd_demo` | `ragtrap demo --n-chunks N`: a concrete ingest → traceback → revoke run over a synthetic corpus | `--n-chunks` (default 100) | counts and the purge line |
| | `cmd_run_experiments` | `ragtrap run-experiments`: the check plus config and environment, into `results/e0_results.json` and `results/manifest.json` | — | result and manifest files |

### 3.2 How the components fit together

Ingestion is a chain, and each link is one module:

```
Chunk (records)
  -> gate.chunk_text            split a document into overlapping windows
  -> hashing.sha256_text        the chunk's own content hash
  -> detectors.run_detectors    best-effort verdicts, recorded and not enforced
  -> records.canonical_message  deterministic bytes over the provenance tuple
  -> signing.Signer.sign        real Ed25519 by default
  -> datastore.put              record stored, both side indices updated
```

`gate.sign_chunk` is where the middle four of those steps meet, and `gate.ingest` is the loop
around it that also calls `datastore.put`. `gate` is the only module that ever constructs a
`ProvenanceRecord`: `sign_chunk` builds the per-chunk one, and `ingest_per_document` builds the
document-granularity one for the Exp. 2 contrast. Nothing outside `gate` seals a record.

Recovery then reads the indices that ingestion filled, and this is the whole point of building
them:

- `traceback.ragtrap_traceback` calls `datastore.lookup_by_content_hash` once per suspect and
  `gate.verify_record` on whatever it finds. It touches no model and re-retrieves nothing.
- `revocation.revoke_source` calls `datastore.chunks_of_principal` once and then
  `datastore.remove_chunk` per revoked chunk, so its cost tracks the number of revoked chunks
  and not the size of the corpus.
- `revocation.manual_purge` is the deliberate contrast: it iterates `datastore.records` in full.
  The two functions differ only in how they *find* the chunks, which is what makes Exp. 2's
  latency ratio a statement about the index rather than about deletion.

The experiment modules compose those primitives and never reach past them:

- `experiments.run_check` drives `synthetic.generate_corpus` → `gate.ingest` →
  `gate.verify_record` → `traceback.ragtrap_traceback` → `revocation.revoke_source`. It is the
  only experiment with no third-party input, which is why it is also the minimal test.
- `realeval` (Exp. 1) ingests the RAGOrigin feedback through the same gate and then runs three
  attributors over one identical suspect list: `ragtrap_traceback`, the `llm_judge` baseline, and
  the RAGOrigin proxy baseline. All three report through `ConfusionCounts.metrics`, so their
  numbers are directly comparable.
- `realeval3` (Exp. 2) is the only place both gate configurations run on the same content:
  `ingest_per_document` + `purge_document` for the document-level scheme, and `ingest` +
  `revoke_source` for RAGtrap. The poison labels are read afterwards, to count collateral
  removal; they never select what is removed.
- `scaling` (Exp. 2 latency) drives `gate.sign_chunk` and `datastore.put` directly, so its
  ingestion timing measures signing and indexing without the bookkeeping `gate.ingest` adds.
- `asr` (Exp. 3) reuses the `llm_judge` model as a plain generator, which is why Exp. 1's
  baseline and Exp. 3 need the same model and the same memory.

Everything that leaves the package is a plain `dict` scored through `stats.wilson`, written as
JSON by the scripts under `scripts/`, and aggregated into `results/macros.tex` — so no number in
the paper is produced anywhere but here.

### 3.3 Reproducibility

Behaviour is environment-driven (prefix `RAGTRAP_`). Every run logs to console and to
`logs/run-<timestamp>.log`. Each third-party input is pinned by content digest. Heavy data
(corpus, models, repos) lives under `$RAGTRAP_DATA_ROOT` (default `~/.cache/ragtrap`)
so the repo holds only code, results, and the paper. One command runs everything:
`bash scripts/reproduce.sh`.

## 4. Datasets

| Artifact | Source | Role | Pinned digest (sha256, first 16) |
|---|---|---|---|
| PoisonedRAG `nq.json` (500 adv passages) | github.com/sleeepeer/PoisonedRAG | the attack | `44df711454a9bada` |
| RAGOrigin feedback `k5_m5_e5_gpt-4o-mini.json` | github.com/zhangbl6618/RAG-Responsibility-Attribution | suspects + labels + the baseline's own input | `658419c9411ee685` |
| BEIR `nq` corpus (2,681,468 passages) | HF `BeIR/nq` (config `corpus`) | clean substrate | parquet `num_rows=2681468` |
| `intfloat/e5-base-v2` | HF | the dense retriever (third-party, as released the feedback was built with e5) | n/a |
| `Qwen/Qwen2.5-3B-Instruct` | HF | local model serving the RAGForensics judge, the RAGOrigin proxy scorer, and the Exp. 3 generation | n/a |

The RAGOrigin feedback is the key substrate: for each of 100 NQ target questions it carries the
top-100 contexts surfaced by the real e5 retriever, each with a third-party poisoned/clean label
and the retrieval score. The top-10 contexts per question give 1000 suspects (500 poisoned, 500
clean) at forensic time. This is the exact format and input the published RAGForensics and
RAGOrigin baselines consume, so both run on it verbatim and RAGtrap attribution is measured on
identical suspects.

## 5. Experiments

Run all: `bash scripts/reproduce.sh`. The RAGOrigin baseline is added by
`scripts/run_ragorigin_baseline.py`. Per-experiment commands and outputs below; results land in
`results/{e0_results,real_results,scaling_results,aux_results}.json` and are aggregated into
`results/results.json` and `results/macros.tex`.

### Experiment mapping

| Paper label | Code identifier | What it measures |
|---|---|---|
| check | `check` | Instrument validation on synthetic data (verify, tamper-detect, attribute, revoke) |
| Exp. 1 | `exp1` | Attribution cost + drift sensitivity (RAGtrap indexed lookup vs LLM-judge and RAGOrigin baselines) |
| Exp. 2 | `exp2` | Source revocation / false purge (per-document vs per-chunk granularity) |
| Exp. 3 | `exp3` | Attack success on generated answers (end-to-end ASR context) |

### Instrument check

Command: `ragtrap selftest`. On a labelled corpus of 200 chunks across 5 principals, all signed
records verify, a tampered message is rejected, and `revoke-source` purges exactly the targeted
principal's 20 chunks with no collateral removal (`instrument_valid: true`). This confirms the
gate, signature verification, and the revocation index behave as specified before any comparison.

### Exp. 1 -- Forensic-time attribution on the real attack (two baselines, identical suspects)

Commands:
```
python scripts/run_real_eval.py --feedback <RAGOrigin feedback> \
  --judge-model Qwen/Qwen2.5-3B-Instruct --top-k 10 --drift 0.0,0.3,0.5
python scripts/run_ragorigin_baseline.py --feedback <RAGOrigin feedback> \
  --proxy-model Qwen/Qwen2.5-3B-Instruct --top-k 10
```
The released feedback contains poison labels but no admission provenance. The evaluation assigns
poisoned passages to one attacker principal and clean passages to synthetic benign principals
before ingesting them through the gate. Suspects are the top-10 retrieved contexts per question (1000 suspects: 500
poison, 500 clean). Three attributors run on the identical suspects: RAGtrap's content-hash lookup;
the published RAGForensics judge loop (one local-model call per context, parsing the verbatim
`[Label: Yes/No]` tag from `RAGForensics/main.py`); and the published RAGOrigin responsibility
scoring (`measure_responsibility` + `determine_threshold` from the released code: per-suspect
answer-loss and question-loss from a local proxy plus the released retrieval score, z-normalized,
averaged as variant_0, and K-means-thresholded per question, two proxy calls per context).

Real captured output (top-10, 1000 suspects = 500 poison + 500 clean):

```
RAGForensics judge:  recall 0.956 [0.934,0.971]  precision 0.882 [0.852,0.906]  FPR 0.128  FNR 0.044
(Qwen2.5-3B-Instruct) latency 1.65 s/suspect (total 1654 s), 1000 model calls
RAGOrigin scoring:   recall 1.000 [0.992,1.000]  precision 0.988 [0.974,0.995]  FPR 0.012  FNR 0.000
(Qwen2.5-3B-Instruct) latency 64.5 ms/suspect (total 64.5 s), 2000 model calls
RAGtrap lookup:      latency 78.7 us/suspect (total 0.079 s), 1000 lookups, 0 model calls
latency ratio:       21026x vs RAGForensics, 819x vs RAGOrigin
```

All three attributors run locally (the judge and proxy served by a local Qwen2.5-3B-Instruct), so
there is NO API billing and no dollar figure is reported; the cost signal is the model-call count
and the wall-clock latency. RAGOrigin's measured FPR (0.012) matches its published low
false-positive profile (FPR <= 0.03 across datasets), confirming the implementation is faithful.

Interpretation: both baselines are accurate forensic tools but pay 1000 and 2000 local model calls
respectively over the 1000 suspects. RAGtrap reads the principal sealed at ingestion with one
content-hash lookup per suspect (78.7 us/suspect), about **21026x** the judge latency and
**819x** the proxy latency, with no model invocation. A lookup returns a principal only when all
records with identical bytes agree on one source. Five poisoned suspects are ambiguous because
the same bytes occur under different source identities.

Exp. 1 drift: recall is 0.990 [0.977,0.996] without drift because five cross-source duplicates are
ambiguous. Rewriting a fraction `p` of poisoned suspects adds hash misses. Recall is 0.694
[0.652,0.733] at p=0.3 and 0.504 [0.460,0.548] at p=0.5; returned attributions remain precise.

### Exp. 2 -- Source revocation and in-memory removal cost

Command:
```
python scripts/run_scaling.py --parquet <BEIR nq parquet> --poisonedrag <PoisonedRAG nq.json> \
  --sizes 10000,100000,1000000,2681468
```
Real captured output (in-memory scan/indexed-removal ratio):
```
   10000 passages ->   17748 chunks; sign 86.9 us/chunk; revoke 41.4 us; manual    1.8 ms; ratio    44x
  100000 passages ->  171989 chunks; sign 86.0 us/chunk; revoke 52.0 us; manual   32.6 ms; ratio   627x
 1000000 passages -> 1662710 chunks; sign 89.6 us/chunk; revoke 48.1 us; manual  335.9 ms; ratio  6977x
 2681468 passages -> 4364162 chunks; sign 69.2 us/chunk; revoke 46.2 us; manual  782.0 ms; ratio 16931x
signing backends @100k: ed25519 63.4 us/chunk, hmac 33.0 us/chunk, ratio 1.92x
```
Interpretation: `revoke-source` enumerates the compromised principal's 100 chunks from the index
and removes them in ~46 microseconds in the prototype, while an in-memory full-corpus scan grows
to 782 ms at 4.36M chunks. The ratio is structural (O(revoked) vs O(corpus)) and grows with
corpus size (44x -> 627x -> 6977x -> 16931x). It excludes database persistence, network access,
cache invalidation, and detector latency. Real Ed25519 per-chunk signing is ~69-90 us/chunk
(11k-16k chunks/s single-threaded), about 1.9x the symmetric HMAC stand-in, in exchange for
non-repudiable public-key provenance. Exp. 2 also contrasts source-indexed revocation with
document-level purging. Each mixed document retains benign-source identities for its NQ chunks
and assigns the injected PoisonedRAG passages to one compromised source. The
per-document scheme over-purges clean fragments at a false-purge rate of **0.521** (95% Wilson CI
[0.494, 0.548]; 672 of 1290 removed chunks were clean), while source-indexed revocation has
false-purge rate **0.000**. Poison labels evaluate collateral and recall but never select removals.
Exact numbers are in `results/aux_results.json`.

### Exp. 3 -- End-to-end attack-success context

Command (part of `scripts/run_check_exp2_exp3.py`). Feeding the top-5 retrieved contexts to a local
Qwen2.5-3B-Instruct generation model and checking the answer: the attack steers it to the
attacker's target answer in **98.0%** of the 100 questions (95% Wilson CI [0.930, 0.994]), with a
0.0% correct-answer rate, confirming the suspects are genuinely dangerous. Exact numbers in
`results/aux_results.json`.

## 6. Scope and future work

RAGtrap's exact-hash attribution misses post-ingestion byte drift (quantified in Exp. 1 drift);
recovering drifted variants needs near-duplicate or semantic matching. Adaptive and multi-attacker
regimes, and the other corpora whose released attack data we also obtained (HotpotQA, MS-MARCO),
are future work. Detection is out of scope and best-effort, with query-time filters as the
complementary layer.
