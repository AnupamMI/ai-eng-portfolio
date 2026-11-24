"""Run a system under test over cases, timing it and capturing errors."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from evalkit.schema import Case, Result

# A scorer gets the case and the system's output and returns a score in [0, 1].
Scorer = Callable[[Case, Any], float]


def run(
    system: Callable[[Any], Any],
    cases: list[Case],
    scorers: dict[str, Scorer],
    *,
    on_result: Callable[[Result], None] | None = None,
) -> list[Result]:
    """Call `system(case.input)` for each case and score the output.

    Exceptions are recorded, not raised: a crash counts as score 0 on every
    scorer, so failures lower the metric instead of disappearing from it.
    """
    results = []
    for case in cases:
        start = time.perf_counter()
        output, error = None, None
        try:
            output = system(case.input)
        except Exception as e:  # noqa: BLE001 - we want every failure recorded
            error = f"{type(e).__name__}: {e}"
        latency = time.perf_counter() - start

        if error is None:
            scores = {name: float(fn(case, output)) for name, fn in scorers.items()}
        else:
            scores = {name: 0.0 for name in scorers}

        result = Result(
            case_id=case.id, output=output, error=error, latency_s=latency, scores=scores
        )
        results.append(result)
        if on_result:
            on_result(result)
    return results
