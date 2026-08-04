"""Verify that generated result macros exactly match the camera-ready paper values."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

COMMAND = re.compile(r"^\\newcommand\{\\([^}]+)\}\{(.*)\}$")
ROOT = Path(__file__).resolve().parent.parent


def load_macros(path: Path) -> dict[str, str]:
    """Parse LaTeX newcommand values from one macro file."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = COMMAND.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, default=ROOT / "results" / "macros.tex")
    parser.add_argument("--expected", type=Path, default=ROOT / "expected" / "paper_macros.tex")
    args = parser.parse_args()

    expected = load_macros(args.expected)
    actual = load_macros(args.actual)
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    wrong = sorted(
        name for name in expected.keys() & actual.keys() if expected[name] != actual[name]
    )

    for name in missing:
        print(f"FAIL missing {name}={expected[name]}")
    for name in unexpected:
        print(f"FAIL unexpected {name}={actual[name]}")
    for name in wrong:
        print(f"FAIL {name}: expected {expected[name]}, got {actual[name]}")

    passed = len(expected) - len(missing) - len(wrong)
    failed = len(missing) + len(unexpected) + len(wrong)
    print(f"PAPER VALUES: {passed} PASS / {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
