"""Best-effort, cheap ingestion-time detectors.

These detectors are deliberately lightweight and CPU-only. They are NOT a detection
contribution: prior work (GMTP, RAGPart/RAGMask, RevPRAG) owns poisoned-content detection, and
those are positioned as complementary query-time layers. RAGtrap's value is forensic and
operational, so the detectors are recorded as *verdicts inside the signed provenance record*
rather than used as a gate that drops content. A false negative here still leaves a signed,
attributable, revocable record, which is the whole point.

Each detector returns a verdict string ("benign" / "suspect") and never raises on a bad input;
an internal error is recorded as the verdict "error" so one bad chunk cannot abort ingestion.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable

Detector = Callable[[str], str]


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def entropy_detector(text: str, low: float = 2.0, high: float = 6.5) -> str:
    """Flag content whose character entropy is outside a plausible natural-language band.

    Very low entropy (repeated tokens) or very high entropy (random/obfuscated payloads) are
    weak poisoning signals. The band is intentionally permissive: detectors are best-effort.
    """
    try:
        h = _shannon_entropy(text)
        return "suspect" if (h < low or h > high) else "benign"
    except Exception:  # noqa: BLE001 -- never let a detector abort ingestion
        return "error"


def repetition_detector(text: str, threshold: float = 0.5) -> str:
    """Flag content dominated by a single repeated token (a common injection padding pattern)."""
    try:
        tokens = text.split()
        if len(tokens) < 4:
            return "benign"
        most_common = Counter(tokens).most_common(1)[0][1]
        return "suspect" if most_common / len(tokens) >= threshold else "benign"
    except Exception:  # noqa: BLE001
        return "error"


def default_detectors() -> dict[str, Detector]:
    """The default best-effort detector suite keyed by name."""
    return {
        "entropy": entropy_detector,
        "repetition": repetition_detector,
    }


def run_detectors(text: str, detectors: dict[str, Detector]) -> dict[str, str]:
    """Run every detector over ``text`` and return a name -> verdict mapping."""
    return {name: detector(text) for name, detector in detectors.items()}
