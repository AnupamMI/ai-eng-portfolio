import httpx
import pytest
from pydantic import BaseModel

from evalkit import (Case, Ollama, Result, compare, load_cases, load_results, paired_bootstrap,
                     run, save_results, summarize, to_markdown)
from evalkit.scorers import contains, exact_match, token_f1


def test_scorers():
    c = Case(id="1", input="q", expected="Paris")
    assert exact_match(c, " paris. ") == 1.0
    assert exact_match(c, "London") == 0.0
    assert contains(c, "The answer is Paris!") == 1.0
    assert token_f1(Case(id="2", input="", expected="the big cat"), "big cat") == pytest.approx(0.8)


def test_run_records_errors_as_zero():
    cases = [Case(id="ok", input=2, expected=4), Case(id="boom", input=0, expected=0)]

    def system(x):
        if x == 0:
            raise RuntimeError("bad input")
        return x * 2

    results = run(system, cases, {"em": exact_match})
    assert results[0].scores == {"em": 1.0} and results[0].error is None
    assert results[1].scores == {"em": 0.0} and "RuntimeError" in results[1].error
    summary = {s.metric: s.mean for s in summarize(results)}
    assert summary["error_rate"] == 0.5


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text('{"id":"a","input":"x","expected":"y"}\n\n{"id":"b","input":"z"}\n')
    assert [c.id for c in load_cases(p)] == ["a", "b"]

    p.write_text('{"id":"a","input":"x"}\n', encoding="utf-8-sig")  # BOM, as PowerShell writes
    assert [c.id for c in load_cases(p)] == ["a"]

    p.write_text('{"id":"a","input":1}\n{"id":"a","input":2}\n')
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(p)

    rs = [Result(case_id="a", output={"k": 1}, latency_s=0.1, scores={"em": 1.0})]
    save_results(rs, tmp_path / "runs" / "r.jsonl")
    assert load_results(tmp_path / "runs" / "r.jsonl") == rs


def test_bootstrap_detects_real_improvement_and_not_noise():
    before = [0.0] * 50 + [1.0] * 50
    after = [1.0] * 80 + [0.0] * 20  # +30 points, overlapping cases
    lo, hi = paired_bootstrap(before, after)
    assert lo > 0

    lo, hi = paired_bootstrap([0.0, 1.0] * 20, [1.0, 0.0] * 20)  # same mean, shuffled
    assert lo < 0 < hi


def _results(ids, score):
    return [Result(case_id=str(i), latency_s=0, scores={"em": score}) for i in ids]


def test_compare_refuses_mismatched_cases():
    with pytest.raises(ValueError, match="different cases"):
        compare(_results(range(30), 0.0), _results(range(5, 40), 1.0))


def test_compare_partial_lists_dropped_cases():
    (d,) = compare(_results(range(30), 0.0), _results(range(5, 40), 1.0), allow_partial=True)
    assert d.n == 25 and d.delta == 1.0 and d.significant
    assert len(d.dropped) == 15 and "0" in d.dropped and "39" in d.dropped
    assert "| em | 25 |" in to_markdown([d])


def test_compare_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        compare(_results([1, 1], 0.0), _results([1], 1.0))


def test_compare_is_paired_by_case_id_not_position():
    # Same per-case scores, opposite order: a paired comparison sees zero change.
    before = [Result(case_id=str(i), latency_s=0, scores={"em": float(i % 2)}) for i in range(20)]
    after = list(reversed(before))
    (d,) = compare(before, after)
    assert d.delta == 0 and d.ci_low == 0 and d.ci_high == 0


def _ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.live
@pytest.mark.skipif(not _ollama_up(), reason="Ollama not running")
def test_ollama_structured_output():
    class Capital(BaseModel):
        country: str
        capital: str

    llm = Ollama("qwen2.5:3b")
    out = llm.structured([{"role": "user", "content": "What is the capital of France?"}], Capital)
    assert out.value.capital.lower() == "paris"
    assert out.attempts >= 1 and out.responses[0].eval_count > 0


def test_bootstrap_diff_for_independent_groups():
    from evalkit import bootstrap_diff
    d, lo, hi = bootstrap_diff([1.0] * 15 + [2.0] * 5, [3.0] * 15 + [2.0] * 5)
    assert d == 1.5 and 0 < lo <= d <= hi
    d, lo, hi = bootstrap_diff([1.0, 3.0] * 10, [3.0, 1.0] * 7)  # different sizes, same mean
    assert d == 0 and lo < 0 < hi
    with pytest.raises(ValueError):
        bootstrap_diff([], [1.0])


def test_bootstrap_ci_covers_statistic_and_counts_undefined_resamples():
    import statistics as st
    from evalkit import bootstrap_ci
    lo, hi, dropped = bootstrap_ci([1.0, 2.0, 3.0, 4.0] * 10, st.fmean)
    assert lo < 2.5 < hi and dropped == 0
    # statistic undefined unless the resample contains both values
    f = lambda xs: float("nan") if len(set(xs)) < 2 else 1.0
    lo, hi, dropped = bootstrap_ci([0, 1], f, iters=1000)
    assert lo == hi == 1.0 and 300 < dropped < 700  # P(all same) = 1/2 for k=2
