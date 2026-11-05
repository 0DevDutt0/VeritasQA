"""Metric functions of the evaluation harness (ARCHITECTURE §17.7 to §17.11; D79 to D83). Standard library only.

An empty denominator gives ``None``, never 0.0 (D79). A proportion carries its count and a Wilson 95% interval. A mean
carries its count and no interval: the Wilson interval applies to proportions only, so a mean has no interval in P8a.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.evaluation.text import normalize, tokens

Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Rate:
    """A proportion. ``value``, ``low`` and ``high`` are None when ``n`` is 0."""

    successes: int
    n: int
    value: float | None
    low: float | None
    high: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {"successes": self.successes, "n": self.n, "value": self.value, "low": self.low, "high": self.high}


@dataclass(frozen=True)
class Mean:
    """A mean over the defined values. ``value`` is None when no value is defined."""

    n: int
    value: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {"n": self.n, "value": self.value}


@dataclass(frozen=True)
class CoveragePoint:
    """One point of the risk-coverage curve: the first ``accepted`` records in the ordering."""

    accepted: int
    coverage: float
    errors: int
    risk: float

    def as_dict(self) -> dict[str, float | int]:
        return {"accepted": self.accepted, "coverage": self.coverage, "errors": self.errors, "risk": self.risk}


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for a proportion, clipped to [0, 1]. Requires ``n > 0``."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError("wilson_interval needs 0 <= successes <= n and n > 0")
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def rate(successes: int, n: int) -> Rate:
    """A proportion with its Wilson interval. An empty denominator gives value None (D79)."""
    if n < 0 or not 0 <= successes <= max(n, 0):
        raise ValueError("rate needs 0 <= successes <= n")
    if n == 0:
        return Rate(0, 0, None, None, None)
    low, high = wilson_interval(successes, n)
    return Rate(successes, n, successes / n, low, high)


def mean_of(values: Sequence[float | None]) -> Mean:
    """The mean of the defined values. ``None`` entries are not counted."""
    defined = [value for value in values if value is not None]
    if not defined:
        return Mean(0, None)
    return Mean(len(defined), sum(defined) / len(defined))


def recall_at_k(first_ranks: Sequence[int | None], k: int) -> float | None:
    """The share of gold quotes whose first hit has rank at most ``k``. ``first_ranks`` has one entry per gold quote."""
    if k < 1:
        raise ValueError("k must be at least 1")
    if not first_ranks:
        return None
    covered = sum(1 for rank in first_ranks if rank is not None and rank <= k)
    return covered / len(first_ranks)


def precision_at_k(hits: Sequence[bool], k: int) -> float:
    """Hits among the first ``k`` returned units, divided by ``k`` (the denominator is ``k`` even when fewer units came back)."""
    if k < 1:
        raise ValueError("k must be at least 1")
    return sum(1 for hit in hits[:k] if hit) / k


def reciprocal_rank(hits: Sequence[bool]) -> float:
    """1 divided by the rank of the first hit in the returned list, or 0.0 when there is none."""
    for rank, hit in enumerate(hits, start=1):
        if hit:
            return 1 / rank
    return 0.0


def ndcg_at_k(credits: Sequence[bool], gold_count: int, k: int) -> float | None:
    """Binary nDCG at ``k``. ``credits`` marks the units that were credited for a gold quote (each quote is credited once).

    The ideal list puts one credited unit per gold quote at the top, so the value is at most 1. None when there is no gold quote.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if gold_count <= 0:
        return None
    dcg = sum(1 / math.log2(rank + 1) for rank, credited in enumerate(credits[:k], start=1) if credited)
    ideal = sum(1 / math.log2(position + 1) for position in range(1, min(k, gold_count) + 1))
    return dcg / ideal


def exact_match(prediction: str, gold: str) -> bool:
    """True when the two texts are equal after the whitespace rule (D76). Case and punctuation must match."""
    return normalize(prediction) == normalize(gold)


def token_f1(prediction: str, gold: str) -> float:
    """The F1 of the word tokens (``\\w+``), with multiset overlap. If either side has no token, the score is 1.0 when the
    normalized texts are equal and 0.0 otherwise."""
    predicted = tokens(prediction)
    expected = tokens(gold)
    if not predicted or not expected:
        return 1.0 if normalize(prediction) == normalize(gold) else 0.0
    shared = sum((Counter(predicted) & Counter(expected)).values())
    if shared == 0:
        return 0.0
    precision = shared / len(predicted)
    recall = shared / len(expected)
    return 2 * precision * recall / (precision + recall)


def risk_coverage(items: Sequence[tuple[tuple[int, str], bool]], total: int) -> tuple[CoveragePoint, ...]:
    """The risk-coverage points. ``items`` holds (order key, is_error) for each accepted record, and a smaller key comes first.

    Point j covers the first j records in the order: coverage = j / total, risk = errors / j. The order is the engine's
    own output, so it is an ordering and not a probability (SPEC §9).
    """
    if total < 0:
        raise ValueError("total cannot be negative")
    if total == 0:
        return ()
    points: list[CoveragePoint] = []
    errors = 0
    for accepted, (_, is_error) in enumerate(sorted(items, key=lambda item: item[0]), start=1):
        errors += int(is_error)
        points.append(CoveragePoint(accepted, accepted / total, errors, errors / accepted))
    return tuple(points)
