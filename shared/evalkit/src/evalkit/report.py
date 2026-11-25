"""Summaries and before/after comparisons with bootstrap confidence intervals."""

from __future__ import annotations

import random
import statistics

from pydantic import BaseModel

from evalkit.schema import Result


class MetricSummary(BaseModel):
    metric: str
    n: int
    mean: float


class Delta(BaseModel):
    metric: str
    n: int
    before: float
    after: float
    delta: float
    ci_low: float
    ci_high: float
    dropped: list[str] = []  # case ids excluded because only one run had them

    @property
    def significant(self) -> bool:
        """True when the 95% CI excludes zero."""
        return self.ci_low > 0 or self.ci_high < 0


def summarize(results: list[Result]) -> list[MetricSummary]:
    metrics = sorted({m for r in results for m in r.scores})
    out = [
        MetricSummary(
            metric=m, n=len(results), mean=statistics.fmean(r.scores.get(m, 0.0) for r in results)
        )
        for m in metrics
    ]
    out.append(MetricSummary(metric="error_rate", n=len(results),
                             mean=sum(r.error is not None for r in results) / len(results)))
    out.append(MetricSummary(metric="latency_p50_s", n=len(results),
                             mean=statistics.median(r.latency_s for r in results)))
    return out


def paired_bootstrap(
    before: list[float], after: list[float], *, iters: int = 10_000, seed: int = 0
) -> tuple[float, float]:
    """95% CI for mean(after - before), resampling cases (paired)."""
    if len(before) != len(after):
        raise ValueError("paired bootstrap needs equal-length lists")
    diffs = [a - b for a, b in zip(after, before)]
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(statistics.fmean(rng.choices(diffs, k=n)) for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters) - 1]


def bootstrap_diff(
    a: list[float], b: list[float], *, iters: int = 10_000, seed: int = 0
) -> tuple[float, float, float]:
    """(mean(b) - mean(a), 95% CI low, high) for two INDEPENDENT groups,
    resampling each group separately. Use paired_bootstrap when the same cases
    appear in both groups."""
    if not a or not b:
        raise ValueError("bootstrap_diff needs two non-empty groups")
    rng = random.Random(seed)
    diffs = sorted(statistics.fmean(rng.choices(b, k=len(b)))
                   - statistics.fmean(rng.choices(a, k=len(a))) for _ in range(iters))
    return (statistics.fmean(b) - statistics.fmean(a),
            diffs[int(0.025 * iters)], diffs[int(0.975 * iters) - 1])


def bootstrap_ci(
    items: list, statistic, *, iters: int = 10_000, seed: int = 0
) -> tuple[float, float, int]:
    """Percentile 95% CI of `statistic(items)` resampling items with replacement.
    Resamples where the statistic is undefined (NaN, e.g. a correlation with no
    variance) are dropped; returns (low, high, n_dropped) so callers can report it."""
    import math
    rng = random.Random(seed)
    vals, dropped = [], 0
    for _ in range(iters):
        v = statistic(rng.choices(items, k=len(items)))
        if v is None or math.isnan(v):
            dropped += 1
        else:
            vals.append(v)
    if not vals:
        return float("nan"), float("nan"), dropped
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[max(0, int(0.975 * len(vals)) - 1)], dropped


def _index(results: list[Result], name: str) -> dict[str, Result]:
    idx = {r.case_id: r for r in results}
    if len(idx) != len(results):
        raise ValueError(f"{name} run has duplicate case ids")
    return idx


def compare(before: list[Result], after: list[Result], *, seed: int = 0,
            allow_partial: bool = False) -> list[Delta]:
    """Paired comparison of two runs, metric by metric.

    Both runs must cover exactly the same case ids; otherwise the comparison
    would quietly be over a different subset than claimed. Pass
    allow_partial=True to compare the overlap anyway; the excluded ids are then
    listed in each Delta's `dropped`.
    """
    b = _index(before, "before")
    a = _index(after, "after")
    shared = sorted(b.keys() & a.keys())
    dropped = sorted(b.keys() ^ a.keys())
    if dropped and not allow_partial:
        raise ValueError(
            f"runs cover different cases; only in before: {sorted(b.keys() - a.keys())[:10]}, "
            f"only in after: {sorted(a.keys() - b.keys())[:10]} (allow_partial=True to override)"
        )
    if not shared:
        raise ValueError("runs share no case ids")
    metrics = sorted({m for r in before + after for m in r.scores})
    deltas = []
    for m in metrics:
        bs = [b[i].scores.get(m, 0.0) for i in shared]
        as_ = [a[i].scores.get(m, 0.0) for i in shared]
        lo, hi = paired_bootstrap(bs, as_, seed=seed)
        mb, ma = statistics.fmean(bs), statistics.fmean(as_)
        deltas.append(Delta(metric=m, n=len(shared), before=mb, after=ma,
                            delta=ma - mb, ci_low=lo, ci_high=hi, dropped=dropped))
    return deltas


def to_markdown(deltas: list[Delta]) -> str:
    rows = ["| metric | n | before | after | delta | 95% CI | sig |",
            "|---|---|---|---|---|---|---|"]
    for d in deltas:
        rows.append(
            f"| {d.metric} | {d.n} | {d.before:.3f} | {d.after:.3f} | {d.delta:+.3f} "
            f"| [{d.ci_low:+.3f}, {d.ci_high:+.3f}] | {'yes' if d.significant else 'no'} |"
        )
    return "\n".join(rows)
