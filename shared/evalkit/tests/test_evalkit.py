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


def test_compare_uses_shared_cases_only():
    before = [Result(case_id=str(i), latency_s=0, scores={"em": 0.0}) for i in range(30)]
    after = [Result(case_id=str(i), latency_s=0, scores={"em": 1.0}) for i in range(5, 40)]
    (d,) = compare(before, after)
    assert d.n == 25 and d.delta == 1.0 and d.significant
    assert "| em | 25 |" in to_markdown([d])


def _ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama not running")
def test_ollama_structured_output():
    class Capital(BaseModel):
        country: str
        capital: str

    llm = Ollama("qwen2.5:3b")
    out = llm.structured([{"role": "user", "content": "What is the capital of France?"}], Capital)
    assert out.value.capital.lower() == "paris"
    assert out.attempts >= 1 and out.responses[0].eval_count > 0
