# RAGtrap: Documentation

This document records the problem RAGtrap addresses, its narrowed contribution, its design, and,
for each experiment, the exact command, the real captured output, and its interpretation. It
closes with the list of experiments that could not run in this environment and the data or
hardware each requires. All numbers reported here were produced by code executed in this
environment; none is estimated or fabricated. Where data is synthetic it is labelled synthetic
and is never presented as a real-world measurement.

## 1. Problem

Retrieval-augmented generation (RAG) pipelines ingest untrusted web and document sources without
a trust boundary at admission time. Corpus poisoning against such pipelines is cheap, effective,
and measurable: published attacks inject a handful of malicious passages per target question to
substantially raise attack success against a knowledge base of millions of texts, and web-scale
poisoning of the very sources RAG ingests is practical. Standards now call for provenance and
quarantine at the data layer, and a recent survey identifies admission-level governance as the
layer where systematic support for provenance, rollback, and corpus recovery remains
under-developed.

The operational question this artifact answers is: once a source is found to be compromised, how
quickly and how precisely can an operator (a) attribute the poisoned chunks to their source and
(b) purge every chunk from that source, without re-running an expensive, language-model-driven
forensic procedure?

## 2. Narrowed contribution

The closest prior artifact frames RAG poisoning as a supply-chain problem and attests content at
ingestion, but it attests at the document level, simulates its signature with a symmetric HMAC,
and provides neither signature-keyed traceback nor a revocation mechanism. The supply-chain
framing and the ingestion-attestation idea are therefore not novel and do not lead this work.

After accounting for that prior art, RAGtrap claims the conjunction of four capabilities, evaluated
on an operational axis (traceback latency, attribution recall, mean-time-to-remediation) that the
prior work does not report:

1. **Per-chunk signed provenance** with the chunk's own content hash and the detector verdicts
   that admitted it, embedded natively in the vector store, in contrast to document-level
   attestation that propagates trust to fragments.
2. **Real Ed25519 public-key signatures**, so provenance is non-repudiable and verifiable by any
   holder of the public key, in contrast to a symmetric HMAC stand-in.
3. **Traceback as a single constant-time signature-keyed lookup**, the structural alternative to
   iterative, language-model-judge-driven re-retrieval.
4. **One-command source revocation** that batch-purges every chunk attributable to a compromised
   principal: the recovery layer the supply-chain analogy implies but that no surveyed tool builds.

Detection is explicitly out of scope as a contribution: the ingestion-time detectors are
best-effort and complementary to query-time filters. RAGtrap's value is forensic and operational.

## 3. Design

RAGtrap is an ingestion gate. For each chunk it computes a SHA-256 content hash, runs a
best-effort detector suite, assembles a canonical byte string over the provenance tuple (chunk id,
source URI, principal, content hash, detector verdicts, timestamp, signer identity, granularity),
signs it with the configured backend, and writes the signed provenance record into the datastore.
The datastore maintains two side indices that make traceback and revocation cheap: a content-hash
index (chunk hash to chunk id, for constant-time resolution of a suspect chunk to its signed
record) and a principal index (principal to its set of chunk ids, so revoking a source enumerates
exactly its chunks without scanning the corpus).

The modules map one-to-one to these concerns: `config` (environment-driven configuration),
`logging_setup` (console and file logging), `hashing`, `signing` (Ed25519 and HMAC backends behind
a common interface), `records` (the provenance schema and its canonical signed-message encoding),
`detectors`, `datastore`, `gate` (chunk, detect, hash, sign, store; plus a per-document
configuration for the granularity contrast), `traceback` (the constant-time lookup and the
iterative-attribution structural baseline), `revocation` (batch revoke and the manual baseline),
`synthetic` (the labelled generator), `corpus` (the BEIR `nq` loader and the poisoned-chunk
builder), `manifest`, `experiments`, and `pending` (ready-to-run harnesses for what cannot run
here). The console entry point is `ragtrap`.

### Reproducibility and logging

Behaviour is configured entirely by environment variables (prefix `RAGTRAP_`) with documented
defaults; nothing is hardcoded. Every run writes to the console and to `logs/run-<timestamp>.log`,
recording the resolved configuration, every input with its content hash, each pipeline step, every
experiment, and all outputs. A run manifest (`results/manifest.json`) pins each input by content
digest, including the BEIR passage subset (by the SHA-256 of its concatenated passage texts), the
Hugging Face revision, the passage cap, and the generated Ed25519 public key identity. The private
key is generated per run and never written to disk.

## 4. Environment of record

The runnable experiments were executed on the following CPU-only environment (captured in
`results/results.json` under `environment`):

```
python: 3.12.3
platform: Linux-6.17.0-29-generic-x86_64-with-glibc2.39
processor: x86_64
```

No GPU is used. The real corpus is the BEIR `nq` (Natural Questions) passage corpus, loaded from
the Hugging Face mirror `BeIR/nq` (configuration `corpus`, revision `main`), capped at 5000
passages for this session. The cap is stated explicitly and is configurable
(`RAGTRAP_BEIR_PASSAGE_CAP`); the cap-removed full-corpus run is experiment E7 (PENDING). Across
the run, 5000 passages yielded 8665 clean chunks at the default 512-character window with
64-character overlap. The pinned subset digest recorded in the manifest for this run is
`62bb900edf852eb50b84b53834e05fd3ff569c001ef0f8fe755a20c317012168`.

Wall-clock latencies vary slightly between runs because they are timing measurements; the
deterministic quantities (work-unit counts, attribution recall, false-purge rate, signature and
record byte sizes) are stable across runs. The numbers below are from the run logged at
`logs/run-<timestamp>.log` whose `results/results.json` is shipped with the artifact.

## 5. Experiments

All runnable experiments are produced by a single command:

```
ragtrap run-experiments
```

This writes `results/results.json`, `results/manifest.json`, and a timestamped run log, and
appends the PENDING descriptors for E5-E7. The per-experiment results below are fields of that
same results file. The headline claim for artifact evaluation is **E1**.

### E0 (RUNNABLE) -- Instrument validation on synthetic data

Purpose: establish that the instrument is correct before any real-data measurement. On a labelled
synthetic corpus of 200 chunks across 5 principals with a known poisoned subset, the experiment
checks that every signed record verifies, that tampering is detected, that signature-keyed
traceback recovers the injected attribution, and that `revoke-source` purges exactly the targeted
principal's chunks and no others.

Command (fast standalone form):

```
ragtrap selftest
```

Real captured output:

```
{
  "experiment": "E0",
  "data": "synthetic (labelled)",
  "n_chunks": 200,
  "all_records_verify": true,
  "tamper_detected": true,
  "traceback_recall": 1.0,
  "revoked_principal": "attacker-0",
  "chunks_purged": 20,
  "purged_exactly_target": true,
  "no_collateral_purge": true,
  "instrument_valid": true
}
```

Interpretation: the instrument is correct by construction. Signatures verify, a flipped message is
rejected, traceback attributes all 20 poisoned chunks to their injected principal (recall 1.0), and
revocation removes exactly those 20 chunks with no collateral removal. This validates the
mechanisms exercised on real data in E1-E3.

### E1 (RUNNABLE, headline) -- Traceback latency and recall on BEIR `nq` + PoisonedRAG injection

Purpose: the main claim. Ingest the bounded BEIR `nq` subset (clean chunks) plus a set of
PoisonedRAG-attributed poisoned chunks (reconstructed from the published black-box template, not
optimizer output, and labelled as such), then attribute the suspect chunks two ways: RAGtrap's
constant-time signature lookup, and a scripted iterative-attribution baseline that re-retrieves and
scans candidate texts (the algorithmic shape of response-triggered attribution without the
language-model judge, a deliberately conservative lower bound on the published baseline's cost).

Command:

```
ragtrap run-experiments     # field "E1" of results/results.json
```

Real captured output (field `E1`):

```
{
  "experiment": "E1",
  "data": "BEIR nq subset (real) + PoisonedRAG poisoned set (reconstructed-from-template)",
  "n_clean_chunks": 8665,
  "n_poisoned_chunks": 15,
  "n_suspects": 15,
  "ragtrap_traceback_recall": 1.0,
  "baseline_traceback_recall": 0.6,
  "ragtrap_latency_s_min": 0.0012103760382160544,
  "ragtrap_latency_s_mean": 0.001240529422648251,
  "baseline_latency_s_min": 0.35818160290364176,
  "baseline_latency_s_mean": 0.35818160290364176,
  "latency_ratio_baseline_over_ragtrap": 295.9258871578104,
  "ragtrap_work_units": 15,
  "baseline_work_units": 130200,
  "work_ratio_baseline_over_ragtrap": 8680.0
}
```

Interpretation: on the same suspect set, RAGtrap attributes every poisoned chunk to its source
(recall 1.0) while the iterative baseline attributes 60% (recall 0.6), because near-identical
poisoned texts confuse lexical re-retrieval whereas the signed content hash resolves each suspect
unambiguously. RAGtrap's traceback is about **296x faster** in wall-clock time on this run, and the
deterministic work-unit ratio is **8680x** (15 constant-time lookups versus 130200 corpus
comparisons, i.e. 15 suspects times 8680 corpus chunks). The latency advantage is therefore not
bought at the cost of correctness: RAGtrap is simultaneously faster and at least as accurate. The
work-unit ratio is the run-invariant form of the headline; the published language-model-judge
baseline would be strictly slower still, since it adds a model call per candidate.

### E2 (RUNNABLE) -- MTTR: one-command revocation vs manual purge

Purpose: demonstrate the recovery layer. On the E1 corpus, one principal is treated as compromised
and removed two ways: RAGtrap's `revoke-source` batch purge (enumerate the principal's chunk-id set
from the index, then delete) versus a manual loop that scans the whole corpus to find and remove
the principal's chunks.

Command:

```
ragtrap run-experiments     # field "E2" of results/results.json
```

Real captured output (field `E2`):

```
{
  "experiment": "E2",
  "data": "E1 corpus (BEIR nq subset + poisoned set)",
  "corpus_chunks": 8680,
  "compromised_principal": "poisonedrag-attacker-0",
  "chunks_purged": 5,
  "revoke_source_mttr_s": 1.0950025171041489e-05,
  "manual_purge_mttr_s": 0.0007224410073831677,
  "mttr_ratio_manual_over_revoke": 65.97619604507761
}
```

Interpretation: batch revocation removes the 5 chunks of the compromised source in about 11
microseconds, versus about 722 microseconds for the full-corpus manual scan, a **66x** mean-time-to-
remediation advantage on this run. The advantage is structural: revocation cost scales with the
number of chunks of the revoked principal, while the manual scan scales with the whole corpus, so
the ratio grows with corpus size (E7 removes the cap). Wall-clock ratios at this small scale vary
between runs; the structural distinction does not.

### E3 (RUNNABLE) -- Per-chunk vs per-document granularity

Purpose: show where per-chunk granularity strictly helps. A partially-poisoned document is built by
placing 50 clean chunks and 10 poisoned chunks under one parent document attributed to one
principal. The corpus is replayed under RAGtrap's per-chunk scheme and under a per-document scheme
that signs the parent and propagates trust to its chunks. Revoking the principal under the
per-document scheme purges the whole document (including its clean chunks: a false purge), whereas
per-chunk attribution localises the poisoned chunks.

Command:

```
ragtrap run-experiments     # field "E3" of results/results.json
```

Real captured output (field `E3`):

```
{
  "experiment": "E3",
  "data": "E1 corpus replayed under per-chunk and per-document schemes",
  "mixed_clean_chunks": 50,
  "mixed_poison_chunks": 10,
  "per_chunk_traceback_recall": 1.0,
  "per_document_purged_total": 60,
  "per_document_false_purged_clean": 50,
  "per_document_false_purge_rate": 0.8333333333333334,
  "per_chunk_false_purge_rate": 0.0
}
```

Interpretation: the per-document scheme over-purges 50 of the 60 chunks it removes (a false-purge
rate of **0.83**) because it cannot distinguish the clean from the poisoned fragments of a
partially-poisoned document, whereas the per-chunk scheme attributes all poisoned chunks (recall
1.0) with **zero** false purge. This is measured entirely on RAGtrap's own two configurations; no
external numbers are fabricated.

### E4 (RUNNABLE) -- Ingestion overhead and storage cost of real Ed25519 per chunk

Purpose: establish practicality and quantify the price of real public-key signing. Per-chunk
signing latency, throughput, and signed-record byte sizes are measured for real Ed25519 and for a
symmetric HMAC stand-in, swept over synthetic corpus sizes (labelled synthetic) and on the real
BEIR subset.

Command:

```
ragtrap run-experiments     # field "E4" of results/results.json
```

Real captured output (field `E4`, real-corpus point):

```
{
  "data": "BEIR nq subset (real)",
  "ed25519": {
    "signer": "ed25519",
    "n_chunks": 8665,
    "total_seconds": 0.5368115700548515,
    "throughput_chunks_per_s": 16141.604397823634,
    "mean_sign_latency_us": 61.95171033523963,
    "mean_record_bytes": 569.5678015002885,
    "mean_signature_bytes": 64.0
  },
  "hmac": {
    "signer": "hmac",
    "n_chunks": 8665,
    "total_seconds": 0.27846583805512637,
    "throughput_chunks_per_s": 31116.92285315313,
    "mean_sign_latency_us": 32.13685378593495,
    "mean_record_bytes": 451.5678015002885,
    "mean_signature_bytes": 32.0
  },
  "ed25519_over_hmac_time": 1.9277465911225413
}
```

Interpretation: real Ed25519 per-chunk signing costs about **62 microseconds per chunk** on the real
corpus (about **16000 chunks per second** single-threaded), producing a fixed **64-byte** signature
and a roughly **570-byte** signed record. Real public-key signing is about **1.9x** the wall-clock
cost of the symmetric HMAC stand-in and produces a signature twice the size; in exchange it yields
non-repudiable provenance verifiable without the secret key. The synthetic sweep (sizes 1000, 5000,
10000) confirms the per-chunk cost is stable with corpus size (about 59 microseconds per chunk at
10000 chunks). The overhead is small enough for practical ingestion.

## 6. PENDING experiments (could not run here)

These are reported as PENDING with a structured descriptor in `results/results.json` under
`pending`, and ship as ready-to-run harnesses in `ragtrap.pending`. No number is fabricated for
them.

### E5 (PENDING) -- Faithful head-to-head vs published RAGForensics / RAGOrigin

Running the baseline as published requires an iterative language-model judge (for example
GPT-4o-mini) and an embedding retriever (for example e5). This needs an API key (and realistically a
GPU for the local proxy model), which are unavailable in this CPU-only, offline session. Until then
E1 reports RAGtrap against the labelled iterative-attribution structural cost model, a lower bound
on the published baseline's cost. Needs: an LLM-judge API key, retriever weights, and a checkout of
the official `RAG-Responsibility-Attribution` repository pointed to by `RAGTRAP_BASELINE_REPO`.

### E6 (PENDING) -- End-to-end PoisonedRAG attack success rate and a GMTP query-time layer

Reproducing the attack end to end (adversarial-text optimization plus language-model generation to
measure attack success) and running the GMTP query-time filter both require a language model and a
masked-language model on a GPU, which are unavailable here. RAGtrap's claims are forensic
(traceback, recall, MTTR), not attack-success-rate, so this is positioning evidence only and must
come from a real run. Needs: a GPU, a generation model, and a masked-language-model reranker.

### E7 (PENDING) -- Full-scale corpora

Ingesting and signing the complete multi-million-passage BEIR corpora exceeds a comfortable memory
and time budget for one CPU-only session. The same E1/E4 code path runs unchanged with the passage
cap raised or removed via `RAGTRAP_BEIR_PASSAGE_CAP`. E1-E4 report the bounded-subset numbers as the
real measurements with the cap stated. Needs: more RAM, time, and cores for parallel signing.

## 7. Honest summary of scope

The supply-chain and ingestion-gate framing is not novel and does not lead this work. A faithful
language-model-judge baseline (E5) and end-to-end attack-success and GMTP measurements (E6) need an
API or a GPU and are PENDING with ready harnesses; their literature figures are cited, never
reproduced by claim. Full-scale corpora (E7) exceed this session's budget. The runnable core,
per-chunk Ed25519 signing, constant-time signature-keyed traceback, batch revocation, and the
ingestion-overhead and granularity contrasts, is pure cryptography plus indexing and runs entirely
CPU-only and offline.
