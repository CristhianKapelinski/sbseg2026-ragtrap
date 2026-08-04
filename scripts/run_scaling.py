"""Run the full-scale ingestion-overhead and in-memory removal sweep on BEIR NQ.

Writes results/scaling_results.json: at each corpus size, the per-chunk Ed25519 signing latency
and throughput, and indexed removal latency versus a full-corpus in-memory scan, with
the ratio. The sweep shows the revoke advantage grows with corpus size, measured up to the full
2,681,468-passage corpus.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ragtrap.realdata import POISONEDRAG_SHA256, load_poisonedrag
from ragtrap.scaling import (
    measure_signing_backends,
    poison_chunks_from_poisonedrag,
    run_scale_point,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--poisonedrag", required=True, help="PoisonedRAG nq.json")
    ap.add_argument("--sizes", default="10000,100000,1000000,2681468")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="results/scaling_results.json")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    prag = load_poisonedrag(args.poisonedrag, dataset="nq")
    poison = poison_chunks_from_poisonedrag(prag, n_principals=5)
    revoke_principal = poison[0].principal  # one compromised attacker principal

    out: dict[str, object] = {
        "data": {
            "corpus": "BEIR/nq (real, 2,681,468 passages)",
            "parquet": str(args.parquet),
            "poison": "PoisonedRAG nq.json released adversarial passages",
            "poison_sha256_pinned": POISONEDRAG_SHA256["nq"],
            "n_poison_chunks": len(poison),
            "revoke_principal": revoke_principal,
        },
        "sizes": sizes,
        "scale_points": [],
    }

    for n in sizes:
        # large sizes are heavy to rebuild many times; bound the repeats for the top end.
        repeats = args.repeats if n <= 100000 else (3 if n <= 1000000 else 2)
        print(f"[{time.strftime('%H:%M:%S')}] scale point n_passages={n} repeats={repeats} ...",
              flush=True)
        t0 = time.time()
        sp = run_scale_point(
            args.parquet,
            poison,
            n_clean_passages=n,
            revoke_principal=revoke_principal,
            repeats=repeats,
        )
        out["scale_points"].append(sp.as_dict())
        print(f"    chunks={sp.n_chunks} sign={sp.sign_latency_us:.1f}us/chunk "
              f"revoke={sp.revoke_mttr_s:.2e}s manual={sp.manual_mttr_s:.2e}s "
              f"ratio={sp.mttr_ratio:.0f}x ({time.time()-t0:.0f}s)", flush=True)

    # Dedicated Ed25519 vs HMAC overhead point at a representative size.
    print(f"[{time.strftime('%H:%M:%S')}] signing-backend comparison ...", flush=True)
    out["signing_backends"] = measure_signing_backends(args.parquet, n_clean_passages=100000)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[{time.strftime('%H:%M:%S')}] wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
