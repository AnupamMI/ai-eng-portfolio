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


def compare(before: list[Result], after: list[Result], *, seed: int = 0) -> list[Delta]:
    """Compare two runs on the cases they share, metric by metric."""
    b = {r.case_id: r for r in before}
    a = {r.case_id: r for r in after}
    shared = sorted(b.keys() & a.keys())
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
                            delta=ma - mb, ci_low=lo, ci_high=hi))
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
