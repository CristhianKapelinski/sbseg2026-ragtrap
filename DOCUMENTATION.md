# RAGtrap: Documentation

This document records the problem RAGtrap addresses, its narrowed contribution, its design, and,
for each experiment, the exact command, the real captured output, and its interpretation. Every
number here is produced by code executed on the pinned third-party datasets; none is estimated or
fabricated. The attack, the dense retrieval, the ground-truth labels, and both baselines are
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

The supply-chain framing and the idea of an ingestion gate are not themselves novel; RAGtrap's
contribution is the recovery layer that framing implies but that no surveyed tool builds. RAGtrap
claims the conjunction of:

1. **Per-chunk signed provenance** with the chunk's own content hash and admitting detector
   verdicts, embedded in the vector store.
2. **Real Ed25519 public-key signatures**, so provenance is non-repudiable and verifiable by any
   holder of the public key.
3. **Traceback as a single constant-time signature-keyed lookup**, the structural alternative to
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
traceback and revocation cheap: a content-hash index (chunk hash to chunk id, O(1) suspect
resolution) and a principal index (principal to its chunk-id set, O(k) revocation without a corpus
scan).

Modules: `config`, `logging_setup`, `hashing`, `signing` (Ed25519 + HMAC), `records`, `detectors`,
`datastore`, `gate`, `traceback` (the constant-time lookup), `revocation` (batch revoke + manual
baseline), `synthetic` (labelled generator for the instrument-validation run), `corpus` (BEIR
loader), `realdata` (third-party PoisonedRAG/RAGOrigin loaders, pinned by SHA-256), `llm_judge`
(the published RAGForensics judge served by a local model), `realeval` (E2: RAGtrap lookup, the
RAGForensics judge baseline, and the RAGOrigin responsibility-scoring baseline, all on identical
suspects) / `realeval3`, `scaling` (E3 MTTR + ingestion cost on the full corpus), `asr` (E4),
`stats` (Wilson + bootstrap CIs), `manifest`, `experiments`. Console entry point: `ragtrap`.

### Reproducibility

Behaviour is environment-driven (prefix `RAGTRAP_`). Every run logs to console and to
`logs/run-<timestamp>.log`. Each third-party input is pinned by content digest. Heavy data
(corpus, models, repos) lives under `$RAGTRAP_DATA_ROOT` (default `~/.cache/ragtrap`)
so the repo holds only code, results, and the paper. One command runs everything:
`bash scripts/reproduce.sh`.

## 4. Datasets (all third-party, pinned by SHA-256)

| Artifact | Source | Role | Pinned digest (sha256, first 16) |
|---|---|---|---|
| PoisonedRAG `nq.json` (500 adv passages) | github.com/sleeepeer/PoisonedRAG | the attack | `44df711454a9bada` |
| RAGOrigin feedback `k5_m5_e5_gpt-4o-mini.json` | github.com/zhangbl6618/RAG-Responsibility-Attribution | suspects + labels + the baseline's own input | `658419c9411ee685` |
| BEIR `nq` corpus (2,681,468 passages) | HF `BeIR/nq` (config `corpus`) | clean substrate | parquet `num_rows=2681468` |
| `intfloat/e5-base-v2` | HF | the dense retriever (third-party, as released the feedback was built with e5) | — |
| `Qwen/Qwen2.5-3B-Instruct` | HF | local model serving the RAGForensics judge, the RAGOrigin proxy scorer, and the E4 generation | — |

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
`results/results.json` and `paper/macros.tex`. The paper labels the four experiments E1-E4.

### E1 -- Instrument validation

Command: `ragtrap selftest`. On a labelled corpus of 200 chunks across 5 principals, all signed
records verify, a tampered message is rejected, and `revoke-source` purges exactly the targeted
principal's 20 chunks with no collateral removal (`instrument_valid: true`). This confirms the
gate, signature verification, and the revocation index behave as specified before any comparison.

### E2 -- Forensic-time attribution on the real attack (two baselines, identical suspects)

Commands:
```
python scripts/run_real_eval.py --feedback <RAGOrigin feedback> \
  --judge-model Qwen/Qwen2.5-3B-Instruct --top-k 10 --drift 0.0,0.3,0.5
python scripts/run_ragorigin_baseline.py --feedback <RAGOrigin feedback> \
  --proxy-model Qwen/Qwen2.5-3B-Instruct --top-k 10
```
Ingest each question's retrieved contexts through the gate (poison -> attacker principal, clean ->
benign sources). Suspects are the top-10 retrieved contexts per question (1000 suspects: 500
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
RAGtrap lookup:      latency 101.7 us/suspect (total 0.10 s), 1000 lookups, 0 model calls
end-to-end latency speedup: 16274x vs RAGForensics, 634x vs RAGOrigin
```

All three attributors run locally (the judge and proxy served by a local Qwen2.5-3B-Instruct), so
there is NO API billing and no dollar figure is reported; the cost signal is the model-call count
and the wall-clock latency. RAGOrigin's measured FPR (0.012) matches its published low
false-positive profile (FPR <= 0.03 across datasets), confirming the implementation is faithful.

Interpretation: both baselines are accurate forensic tools but pay 1000 and 2000 local model calls
respectively over the 1000 suspects. RAGtrap reads the principal sealed at ingestion with one
content-hash lookup per suspect (101.7 us/suspect), about **16274x** faster than the judge and
**634x** faster than the proxy scorer, with no model invocation. While provenance is intact a
lookup returns the recorded principal directly, so RAGtrap's accuracy under intact provenance is
not a detection score and is not reported as one; the informative axes are the cost comparison
above and the drift curve below.

E2-drift: paraphrasing a fraction `p` of poisoned suspects after ingestion makes their retrieved
bytes differ from the sealed bytes, so the hash lookup misses them. Recall drops from 1.00 at p=0
to 0.702 [0.660,0.740] at p=0.3 and 0.508 [0.464,0.552] at p=0.5; precision stays exact (a hash
match is exact, the missed chunks are false negatives).

### E3 -- Revocation MTTR and ingestion cost at full corpus scale

Command:
```
python scripts/run_scaling.py --parquet <BEIR nq parquet> --poisonedrag <PoisonedRAG nq.json> \
  --sizes 10000,100000,1000000,2681468
```
Real captured output (MTTR ratio = manual / revoke):
```
   10000 passages ->   17748 chunks; sign 86.9 us/chunk; revoke 41.4 us; manual    1.8 ms; ratio    44x
  100000 passages ->  171989 chunks; sign 86.0 us/chunk; revoke 52.0 us; manual   32.6 ms; ratio   627x
 1000000 passages -> 1662710 chunks; sign 89.6 us/chunk; revoke 48.1 us; manual  335.9 ms; ratio  6977x
 2681468 passages -> 4364162 chunks; sign 69.2 us/chunk; revoke 46.2 us; manual  782.0 ms; ratio 16931x
signing backends @100k: ed25519 63.4 us/chunk, hmac 33.0 us/chunk, ratio 1.92x
```
Interpretation: `revoke-source` enumerates the compromised principal's 100 chunks from the index
and purges them in ~46 microseconds regardless of corpus size, while the manual full-corpus scan
grows linearly to 782 ms at 4.36M chunks: a **16931x** MTTR advantage on the full
2,681,468-passage corpus. The advantage is structural (O(revoked) vs O(corpus)) and grows with
corpus size (44x -> 627x -> 6977x -> 16931x). Real Ed25519 per-chunk signing is ~69-90 us/chunk
(11k-16k chunks/s single-threaded), about 1.9x the symmetric HMAC stand-in, in exchange for
non-repudiable public-key provenance. E3 also contrasts per-chunk against per-document granularity:
for 206 real NQ passages each injected with 3 real PoisonedRAG passages under one principal, the
per-document scheme over-purges clean fragments at a false-purge rate of **0.521** (95% Wilson CI
[0.494, 0.548]; 672 of 1290 removed chunks were clean), while RAGtrap's per-chunk scheme has
false-purge rate **0.000**. Exact numbers in `results/aux_results.json`.

### E4 -- End-to-end attack-success context

Command (part of `scripts/run_e0_e3_e5.py`). Feeding the top-5 retrieved contexts to a local
Qwen2.5-3B-Instruct generation model and checking the answer: the attack steers it to the
attacker's target answer in **98.0%** of the 100 questions (95% Wilson CI [0.930, 0.994]), with a
0.0% correct-answer rate, confirming the suspects are genuinely dangerous. Exact numbers in
`results/aux_results.json`.

## 6. Scope and future work

RAGtrap's exact-hash attribution misses post-ingestion byte drift (quantified in E2-drift);
recovering drifted variants needs near-duplicate or semantic matching. Adaptive and multi-attacker
regimes, and the other corpora whose released attack data we also obtained (HotpotQA, MS-MARCO),
are future work. Detection is out of scope and best-effort, with query-time filters as the
complementary layer.
