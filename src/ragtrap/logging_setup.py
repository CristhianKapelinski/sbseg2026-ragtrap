"""Logging subsystem: writes to console AND to ``logs/run-<timestamp>.log``.

Every run records its resolved configuration, every input with its content hash, each pipeline
step, every experiment command, and all outputs. The log path is returned so callers can record
it in the run manifest. Reproducibility is built in: a reviewer can replay a run from its log.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOGGER_NAME = "ragtrap"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


def utc_timestamp() -> str:
    """A filesystem-safe UTC timestamp for the run log filename."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> tuple[logging.Logger, Path]:
    """Configure the root ``ragtrap`` logger with console and file handlers.

    Returns the configured logger and the absolute path of the run log file. Idempotent:
    repeated calls in the same process reuse the already-configured handlers.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"run-{utc_timestamp()}.log"

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:  # already configured in this process
        return logger, Path(getattr(logger, "_ragtrap_log_path", log_path))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Stash the resolved path so a second call returns it without reconfiguring.
    logger._ragtrap_log_path = log_path  # type: ignore[attr-defined]
    return logger, log_path


def get_logger() -> logging.Logger:
    """Return the shared ``ragtrap`` logger (configure it first via :func:`setup_logging`)."""
    return logging.getLogger(_LOGGER_NAME)
