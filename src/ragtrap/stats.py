"""Small statistics helpers: Wilson score intervals and bootstrap CIs.

Proportions (recall, precision, FPR, FNR, false-purge rate) are reported with a 95% Wilson score
interval, which is well-behaved near 0 and 1 and for small N, unlike the normal approximation.
Latency helpers support nonparametric bootstrap intervals over repeated measurements.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Proportion:
    """A proportion k/n with its 95% Wilson score interval."""

    k: int
    n: int
    point: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "k": self.k,
            "n": self.n,
            "point": self.point,
            "ci_low": self.low,
            "ci_high": self.high,
        }


def wilson(k: int, n: int, z: float = 1.96) -> Proportion:
    """95% Wilson score interval for k successes out of n trials."""
    if n == 0:
        return Proportion(k=0, n=0, point=0.0, low=0.0, high=0.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return Proportion(k=k, n=n, point=p, low=max(0.0, centre - half), high=min(1.0, centre + half))


def bootstrap_ci(
    values: list[float], *, reducer=None, n_boot: int = 10000, z: float = 0.95, seed: int = 1337
) -> dict[str, float]:
    """Nonparametric bootstrap CI (default 95%) of a reducer (mean by default) over ``values``."""
    if not values:
        return {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    reduce = reducer or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    point = reduce(values)
    if len(values) == 1:
        return {"point": point, "ci_low": point, "ci_high": point, "n": 1}
    stats = []
    n = len(values)
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(reduce(sample))
    stats.sort()
    lo = stats[int((1 - z) / 2 * n_boot)]
    hi = stats[int((1 - (1 - z) / 2) * n_boot) - 1]
    return {"point": point, "ci_low": lo, "ci_high": hi, "n": n}
