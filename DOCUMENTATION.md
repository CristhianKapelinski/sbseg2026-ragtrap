# RAGtrap: Documentation

This document records the problem RAGtrap addresses, its narrowed contribution, its design, and,
for each experiment, the exact command, the real captured output, and its interpretation. Every
number here is produced by code executed on the pinned third-party datasets; none is estimated or
fabricated. The evaluation is non-circular: the attack, the dense retrieval, the ground-truth
labels, and the baseline are all third-party artifacts that RAGtrap did not author.

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

The closest prior artifact (RAGShield) frames RAG poisoning as a supply-chain problem and attests
content at ingestion, but at the document level, with a symmetric HMAC standing in for its
signature, and with neither signature-keyed traceback nor revocation. That framing is therefore
not novel and does not lead this work. RAGtrap claims the conjunction of:

1. **Per-chunk signed provenance** with the chunk's own content hash and admitting detector
   verdicts, embedded in the vector store.
2. **Real Ed25519 public-key signatures**, so provenance is non-repudiable and verifiable by any
   holder of the public key.
3. **Traceback as a single constant-time signature-keyed lookup**, the structural alternative to
   iterative LLM-judge re-retrieval.
4. **One-command source revocation** that batch-purges every chunk of a compromised principal.

Detection is explicitly out of scope as a contribution; ingestion detectors are best-effort and
complementary to query-time filters (GMTP, RAGPart/RAGMask). RAGtrap's value is forensic and
operational.

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
baseline), `synthetic` (labelled generator for E0), `corpus` (BEIR loader), `realdata` (third-party
PoisonedRAG/RAGOrigin loaders, pinned by SHA-256), `llm_judge` (the published RAGForensics judge
served by a local model), `realeval`/`realeval3` (E1/E3), `scaling` (E2/E4 on the full corpus),
`asr` (E5), `stats` (Wilson + bootstrap CIs), `manifest`, `experiments` (E0). Console entry point:
`ragtrap`.

### Reproducibility

Behaviour is environment-driven (prefix `RAGTRAP_`). Every run logs to console and to
`logs/run-<timestamp>.log`. Each third-party input is pinned by content digest. Heavy data
(corpus, models, repos) lives under `$RAGTRAP_DATA_ROOT` (default `/mnt/win_ssd/sbseg-work/ragtrap`)
so the repo holds only code, results, and the paper. One command runs everything:
`bash scripts/reproduce.sh`.

## 4. Datasets (all third-party, pinned by SHA-256)

| Artifact | Source | Role | Pinned digest (sha256, first 16) |
|---|---|---|---|
| PoisonedRAG `nq.json` (500 adv passages) | github.com/sleeepeer/PoisonedRAG | the attack | `44df711454a9bada` |
| RAGOrigin feedback `k5_m5_e5_gpt-4o-mini.json` | github.com/zhangbl6618/RAG-Responsibility-Attribution | suspects + labels + the baseline's own input | `658419c9411ee685` |
| BEIR `nq` corpus (2,681,468 passages) | HF `BeIR/nq` (config `corpus`) | clean substrate | parquet `num_rows=2681468` |
| `intfloat/e5-base-v2` | HF | the dense retriever (third-party, as released the feedback was built with e5) | — |
| `Qwen/Qwen2.5-3B-Instruct` | HF | local model serving the RAGForensics judge + the E5 generation | — |

The RAGOrigin feedback is the key substrate: for each of 100 NQ target questions it carries the
top-100 contexts surfaced by the real e5 retriever, each with a third-party poisoned/clean label
(5 poisoned per question, 500 total) and the retrieval score. This is the exact format and input
the published RAGForensics baseline consumes, so the baseline runs on it verbatim and RAGtrap
attribution is measured on identical suspects.

## 5. Experiments

Run all: `bash scripts/reproduce.sh`. Per-experiment commands and outputs below; results land in
`results/{e0_results,real_results,scaling_results,aux_results}.json` and are aggregated into
`results/results.json` and `paper/macros.tex`.

### E0 (correctness property) -- Instrument validation

Command: `ragtrap selftest`. On a labelled synthetic corpus of 200 chunks across 5 principals, all
signed records verify, a tampered message is rejected, hash-keyed traceback recovers the injected
attribution, and `revoke-source` purges exactly the targeted principal's 20 chunks with no
collateral. This is a deterministic, by-construction guarantee (`instrument_valid: true`), framed
as a correctness property, not a statistical detection rate.

### E1 (headline) -- Traceback on the real attack: RAGtrap O(1) vs RAGForensics LLM judge

Command:
```
python scripts/run_real_eval.py --feedback <RAGOrigin feedback> \
  --judge-model Qwen/Qwen2.5-3B-Instruct --top-k 10 --drift 0.0,0.3,0.5
```
Ingest each question's retrieved contexts through the gate (poison -> attacker principal, clean ->
benign sources). Suspects are the top-10 retrieved contexts per question (1000 suspects: 500
poison, 500 clean -- a balanced, meaningful FPR). Two attributors run on the identical suspects:
RAGtrap's content-hash lookup, and the published RAGForensics judge loop (one local-model call per
context, parsing the verbatim `[Label: Yes/No]` tag from `RAGForensics/main.py`).

Real captured output (top-10, 1000 suspects = 500 poison + 500 clean):

```
RAGtrap (no drift):  recall 1.000 [0.992,1.000]  precision 1.000 [0.992,1.000]  FPR 0.000
                     latency 101.7 us/suspect (total 0.10 s), 1000 lookups, 0 model calls
RAGForensics judge:  recall 0.956 [0.934,0.971]  precision 0.882 [0.852,0.906]  FPR 0.128  FNR 0.044
(Qwen2.5-3B-Instruct) latency 1.65 s/suspect (total 1654 s), 1000 model calls
end-to-end latency speedup: 16274x
```

Both the judge and RAGtrap run locally (the judge served by a local Qwen2.5-3B-Instruct), so there
is NO API billing and no dollar figure is reported; the honest cost signal is the model-call count
(1000 calls vs 1 constant-time lookup) and the wall-clock latency.

Interpretation: with intact signed provenance RAGtrap's content-hash traceback is **exact by
construction** -- the principal is sealed at ingestion from the same content the suspect is later
hashed against, so for admitted (undrifted) chunks recall = precision = 1.00 and FPR = 0.00
*deterministically*; this is a correctness guarantee, not a learned detector's score, so it is NOT
the evaluative headline. The evaluative headline is operational: RAGtrap's single lookup
(101.7 us/suspect) is about **16274x** faster end to end than the real, genuinely imperfect
RAGForensics LLM-judge baseline (recall 0.956, precision 0.882, FPR 0.128) on the identical
suspects, replacing 1000 model calls with one constant-time lookup. The honest detection result is
the drift-robustness curve (recall 1.00 -> 0.70 at 30% drift -> 0.51 at 50%) plus the latency and
revocation MTTR, not the by-construction 1.00.

E1-drift: paraphrasing a fraction of poisoned suspects after ingestion makes their retrieved bytes
differ from the sealed bytes, so the hash lookup misses them -- honest false negatives reported,
not hidden. Recall drops to 0.702 [0.660,0.740] at 30% drift and 0.508 at 50% drift; precision
stays exact.

### E2 / E4 -- MTTR and ingestion overhead at full corpus scale

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
grows linearly to 782 ms at 4.36M chunks -- a **16931x** MTTR advantage on the full
2,681,468-passage corpus. The advantage is structural (O(revoked) vs O(corpus)) and grows with
corpus size (44x -> 627x -> 6977x -> 16931x). Real Ed25519 per-chunk signing is ~69-90 us/chunk
(11k-16k chunks/s single-threaded), about 1.9x the symmetric HMAC stand-in, in exchange for
non-repudiable public-key provenance.

### E3 -- Per-chunk vs per-document granularity on real partially-poisoned documents

Command (part of `scripts/run_e0_e3_e5.py`). For 230 real NQ passages, each split into clean
chunks and injected with 3 real PoisonedRAG passages under one principal: the per-document scheme
(sign the parent, propagate trust) over-purges clean fragments at a false-purge rate of
**0.521** (95% Wilson CI [0.495, 0.547]; 751 of 1441 removed chunks were clean), because it cannot
localise the poison; RAGtrap's per-chunk scheme has false-purge rate **0.000**. Exact numbers in
`results/aux_results.json`.

### E5 -- End-to-end attack-success context

Command (part of `scripts/run_e0_e3_e5.py`). Feeding the top-5 retrieved contexts to a local
Qwen2.5-3B-Instruct generation model and checking the answer: the attack steers it to the
attacker's target answer in **98.0%** of the 100 questions (95% Wilson CI [0.930, 0.994]), with a
0.0% correct-answer rate, confirming the suspects are genuinely dangerous (positioning context,
not the headline). Exact numbers in `results/aux_results.json`.

## 6. Scope and future work (research terms, not tooling excuses)

RAGtrap's exact-hash attribution misses post-ingestion byte drift (quantified in E1-drift);
recovering drifted variants needs near-duplicate or semantic matching. Adaptive and multi-attacker
regimes (RAGOrigin's harder settings), and the other corpora whose released attack data we also
obtained (HotpotQA, MS-MARCO), are future work. Detection is out of scope and best-effort, with
query-time filters as the complementary layer.
