"""Console entry point for RAGtrap.

Subcommands:

* ``run-experiments`` -- run the runnable experiments (E0-E4), write ``results/results.json``
  and the run manifest, and append the PENDING descriptors (E5-E7). This is the main-claim
  reproduction path used by artifact evaluation.
* ``selftest`` -- run only E0 (instrument validation on synthetic data) for a fast smoke test.
* ``demo`` -- a minimal end-to-end demonstration of ingest -> traceback -> revoke-source on a
  small synthetic corpus, printing the constant-time lookup and the one-command purge.

Everything is configured via environment variables (see ``config.py``); nothing is hardcoded.
Every run writes a timestamped log under ``logs/`` and records inputs by content digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .experiments import run_all_runnable
from .gate import ingest
from .logging_setup import setup_logging
from .manifest import Manifest
from .pending import run_all_pending
from .revocation import revoke_source
from .signing import Ed25519Signer
from .synthetic import generate_corpus
from .traceback import ragtrap_traceback


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_run_experiments(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg.ensure_dirs()
    logger, log_path = setup_logging(cfg.logs_dir)
    logger.info("RAGtrap %s starting run-experiments", __version__)
    logger.info("Resolved config: %s", cfg.as_dict())

    signer_identity = Ed25519Signer.generate().public_identity()
    manifest = Manifest(
        config=cfg.as_dict(), signer_identity=signer_identity, log_path=str(log_path)
    )

    results = run_all_runnable(cfg)
    results["pending"] = run_all_pending()

    # Record the synthetic E0 corpus and (if loaded) the real corpus in the manifest.
    e0_chunks = generate_corpus(
        n_chunks=200, n_principals=5, poison_fraction=0.1, seed=cfg.seed, poisoned_principals=1
    )
    manifest.add_corpus_input(
        "e0_synthetic", e0_chunks, description="E0 synthetic corpus (labelled)"
    )
    corpus_note = results.get("corpus_note", {})
    if isinstance(corpus_note, dict) and corpus_note.get("clean_chunks"):
        manifest.add_input(
            "beir_nq_subset",
            digest="see-corpus_note",
            description="BEIR nq passage subset (real public)",
            **corpus_note,
        )

    results_path = cfg.results_dir / "results.json"
    manifest_path = cfg.results_dir / "manifest.json"
    _write_json(results_path, results)
    manifest.write(manifest_path)
    logger.info("Wrote results to %s", results_path)
    logger.info("Wrote manifest to %s", manifest_path)
    logger.info("Run log at %s", log_path)
    print(f"results: {results_path}")
    print(f"manifest: {manifest_path}")
    print(f"log: {log_path}")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg.ensure_dirs()
    logger, log_path = setup_logging(cfg.logs_dir)
    logger.info("RAGtrap %s selftest (E0 instrument validation)", __version__)
    from .experiments import run_e0

    result = run_e0(cfg)
    print(json.dumps(result, indent=2))
    ok = bool(result.get("instrument_valid"))
    logger.info("Selftest %s", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def cmd_demo(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg.ensure_dirs()
    logger, _ = setup_logging(cfg.logs_dir)
    logger.info("RAGtrap %s demo: ingest -> traceback -> revoke-source", __version__)

    chunks = generate_corpus(
        n_chunks=args.n_chunks, n_principals=4, poison_fraction=0.1, seed=cfg.seed,
        poisoned_principals=1,
    )
    signer = Ed25519Signer.generate()
    store, _ = ingest(chunks, signer)
    logger.info("Ingested %d chunks; signer=%s", len(store), signer.public_identity())

    suspects = [c for c in chunks if c.is_poisoned]
    attribution = ragtrap_traceback(suspects, store, signer)
    attributed = {cid: p for cid, p in attribution.attributions.items() if p is not None}
    print(f"ingested chunks: {len(store)}")
    print(f"suspect chunks: {len(suspects)}")
    print(f"traceback attributed {len(attributed)} suspects via O(1) lookup")
    print(f"traceback work units (lookups): {attribution.work_units}")

    target = "attacker-0"
    before = len(store)
    rev = revoke_source(store, target)
    print(f"revoke-source {target}: purged {rev.n_purged} chunks ({before} -> {len(store)})")
    logger.info("Demo complete")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragtrap", description=__doc__)
    parser.add_argument("--version", action="version", version=f"ragtrap {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run-experiments", help="run E0-E4 and write results + manifest")
    p_run.set_defaults(func=cmd_run_experiments)

    p_self = sub.add_parser("selftest", help="fast E0 instrument-validation smoke test")
    p_self.set_defaults(func=cmd_selftest)

    p_demo = sub.add_parser("demo", help="minimal end-to-end ingest/traceback/revoke demo")
    p_demo.add_argument("--n-chunks", type=int, default=100, dest="n_chunks")
    p_demo.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
