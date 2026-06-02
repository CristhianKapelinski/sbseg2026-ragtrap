"""Resolved runtime configuration.

All behaviour is driven by environment variables with documented defaults; nothing that a
reviewer might need to change is hardcoded. The config object is logged verbatim at startup so
every run records the parameters that produced its outputs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_PREFIX = "RAGTRAP_"


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(_ENV_PREFIX + name, default)).expanduser().resolve()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(_ENV_PREFIX + name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # explicit, typed failure instead of a silent default
        name_full = _ENV_PREFIX + name
        raise ValueError(f"environment variable {name_full}={raw!r} is not an int") from exc


def _env_str(name: str, default: str) -> str:
    return os.environ.get(_ENV_PREFIX + name, default)


@dataclass(frozen=True)
class Config:
    """Immutable, fully resolved configuration for one run."""

    # Filesystem roots (each overridable for containerised / CI runs).
    repo_root: Path = field(default_factory=lambda: _env_path("ROOT", str(Path.cwd())))
    data_dir: Path = field(default_factory=lambda: _env_path("DATA_DIR", "data"))
    logs_dir: Path = field(default_factory=lambda: _env_path("LOGS_DIR", "logs"))
    results_dir: Path = field(default_factory=lambda: _env_path("RESULTS_DIR", "results"))

    # Signing backend: "ed25519" (real public-key, default) or "hmac" (symmetric stand-in,
    # used only to quantify the cost of real crypto in E4).
    signer: str = field(default_factory=lambda: _env_str("SIGNER", "ed25519"))

    # Chunking parameters for the ingestion gate.
    chunk_chars: int = field(default_factory=lambda: _env_int("CHUNK_CHARS", 512))
    chunk_overlap: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP", 64))

    # Bounded BEIR `nq` passage cap for a CPU-only session (stated explicitly in the paper).
    beir_dataset: str = field(default_factory=lambda: _env_str("BEIR_DATASET", "nq"))
    beir_passage_cap: int = field(default_factory=lambda: _env_int("BEIR_PASSAGE_CAP", 5000))
    hf_revision: str = field(default_factory=lambda: _env_str("HF_REVISION", "main"))

    # Reproducibility seed for synthetic generation and any sampling.
    seed: int = field(default_factory=lambda: _env_int("SEED", 1337))

    def ensure_dirs(self) -> None:
        """Create the writable output directories if they do not exist."""
        for path in (self.data_dir, self.logs_dir, self.results_dir):
            path.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, object]:
        """A JSON-serialisable view for logging and the run manifest."""
        return {
            "repo_root": str(self.repo_root),
            "data_dir": str(self.data_dir),
            "logs_dir": str(self.logs_dir),
            "results_dir": str(self.results_dir),
            "signer": self.signer,
            "chunk_chars": self.chunk_chars,
            "chunk_overlap": self.chunk_overlap,
            "beir_dataset": self.beir_dataset,
            "beir_passage_cap": self.beir_passage_cap,
            "hf_revision": self.hf_revision,
            "seed": self.seed,
        }


def load_config() -> Config:
    """Resolve configuration from the environment with documented defaults."""
    return Config()
