"""Inter-rater agreement on an ordinal scale (e.g. 1-3 grades)."""

from __future__ import annotations

import statistics


def confusion(a: list[int], b: list[int], labels: list[int]) -> list[list[int]]:
    """m[i][j] = number of items rater A labelled labels[i] and rater B labels[j]."""
    if len(a) != len(b):
        raise ValueError("raters must grade the same items")
    idx = {lab: i for i, lab in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for x, y in zip(a, b):
        m[idx[x]][idx[y]] += 1
    return m


def weighted_kappa(a: list[int], b: list[int], labels: list[int], *,
                   weights: str = "quadratic") -> float:
    """Cohen's weighted kappa. Disagreement weight |i-j| ("linear") or (i-j)^2
    ("quadratic"), normalized by the max. 1 = perfect, 0 = chance-level agreement.
    NaN if expected disagreement is 0 (e.g. both raters gave one label only)."""
    m = confusion(a, b, labels)
    k, n = len(labels), len(a)
    if weights not in ("linear", "quadratic"):
        raise ValueError(weights)
    p = 1 if weights == "linear" else 2
    w = [[(abs(i - j) / (k - 1)) ** p for j in range(k)] for i in range(k)]
    row = [sum(r) for r in m]
    col = [sum(m[i][j] for i in range(k)) for j in range(k)]
    observed = sum(w[i][j] * m[i][j] for i in range(k) for j in range(k)) / n
    expected = sum(w[i][j] * row[i] * col[j] for i in range(k) for j in range(k)) / n ** 2
    return float("nan") if expected == 0 else 1 - observed / expected


def exact_agreement(a: list[int], b: list[int]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("raters must grade the same, non-empty items")
    return statistics.fmean(float(x == y) for x, y in zip(a, b))
