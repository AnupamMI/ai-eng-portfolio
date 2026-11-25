import json
from functools import partial

import httpx
import pytest

from text2sql import bench, freeze, report
from text2sql.generate import SQLAnswer
from text2sql.score import score
from text2sql.testset import TESTSET_DIR, Interpretation, load
from text2sql.validate_testset import databases


@pytest.fixture(scope="module")
def dbs():
    return databases()


def it(sql, ordered=False):
    return Interpretation(id="r", description="d", gold_sql=sql, ordered=ordered)


def test_frozen_files_unchanged():
    # Tripwire: a frozen file was edited. Restore it, or log the change and update freeze.py.
    assert freeze.changed() == []


def test_sql_answer_rejects_empty():
    with pytest.raises(ValueError):
        SQLAnswer(sql="   ")


def test_score_lenient_strict_and_types(dbs):
    g = it("SELECT name FROM products WHERE category = 'Toys'")
    ok = score(g, "SELECT name FROM products WHERE category = 'Toys';", dbs)
    assert (ok["lenient"], ok["strict"], ok["auto_type"]) == (1.0, 1.0, None)
    extra = score(g, "SELECT product_id, name FROM products WHERE category = 'Toys'", dbs)
    assert (extra["lenient"], extra["strict"]) == (1.0, 0.0)
    assert score(g, "SELEC name FROM products", dbs)["auto_type"] == "syntax"
    assert score(g, "SELECT nam FROM products", dbs)["auto_type"] == "schema"
    assert score(g, None, dbs)["auto_type"] == "empty"
    assert score(g, None, dbs, gen_error="ReadTimeout: timed out")["auto_type"] == "timeout"
    assert score(g, "DROP TABLE products", dbs)["auto_type"] == "other"
    wrong = score(g, "SELECT name FROM products WHERE category = 'Books'", dbs)
    assert (wrong["lenient"], wrong["auto_type"]) == (0.0, "unclassified")
    two = it("SELECT category, COUNT(*) FROM products GROUP BY category")
    assert score(two, "SELECT category FROM products GROUP BY category", dbs)["auto_type"] == "shape"


def test_score_needs_both_seeds(dbs):
    # A constant that happens to equal the seed-0 answer must not pass.
    g = it("SELECT COUNT(*) FROM orders WHERE status = 'placed'")
    seed0 = score(g, "SELECT COUNT(*) FROM orders WHERE status = 'placed'", dbs)["seeds"][0]
    const = seed0["gold"]["first_rows"][0][0]
    s = score(g, f"SELECT {const}", dbs)
    assert s["seeds"][0]["match"] and not s["seeds"][1]["match"] and s["lenient"] == 0.0


def _fake_ollama(answers: dict[str, str]):
    """Mock /api/chat: the reply for a question is answers[question] (raw content string)."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/generate":
            return httpx.Response(200, json={})
        body = json.loads(req.content)
        q = body["messages"][1]["content"]
        content = answers.get(q, json.dumps({"sql": "SELECT 1"}))
        return httpx.Response(200, json={
            "message": {"content": content}, "done_reason": "stop", "eval_count": 20,
            "eval_duration": 1e9, "prompt_eval_count": 30, "prompt_eval_duration": 1e8,
            "load_duration": 0, "total_duration": 2e9})
    return httpx.MockTransport(handler)


def test_bench_end_to_end_resume_and_report(tmp_path, monkeypatch):
    dev = [q for q in load(TESTSET_DIR / "dev.jsonl") if q.label == "clear"]
    answers = {q.question: json.dumps({"sql": q.spec.interpretations[0].gold_sql}) for q in dev}
    answers[dev[0].question] = json.dumps({"sql": "SELEC broken"})
    answers[dev[1].question] = "not json"  # invalid twice -> empty
    calls = []
    transport = _fake_ollama(answers)
    monkeypatch.setattr(bench, "Ollama", partial(bench.Ollama, transport=transport))
    monkeypatch.setattr(bench, "pulled_models", lambda url: {"m:1"})
    monkeypatch.setattr(bench, "loaded_models", lambda url: calls.append("ps") or [])
    monkeypatch.setattr(bench.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))
    argv = ["--out", str(tmp_path), "--models", "m:1", "--splits", "dev", "--stall-dump-s", "0"]
    assert bench.main(argv) == 0
    rs = [json.loads(x) for x in (tmp_path / "m-1.jsonl").read_text().splitlines()]
    assert len(rs) == 5
    by = {r["meta"]["qid"]: r for r in rs}
    assert by[dev[0].id]["meta"]["auto_type"] == "syntax"
    assert by[dev[1].id]["meta"]["auto_type"] == "empty" and by[dev[1].id]["output"]["attempts"] == 2
    assert sum(r["scores"]["lenient"] for r in rs) == 3
    log = (tmp_path / "log.txt").read_text()
    assert log.count(" start ") == 5
    # resume: nothing left to do, nothing appended, no model loaded
    calls.clear()
    assert bench.main(argv) == 0
    assert len((tmp_path / "m-1.jsonl").read_text().splitlines()) == 5 and calls == []
    # report and labels template
    assert report.main([str(tmp_path), "--labels-template"]) == 0
    md = (tmp_path / "report.md").read_text()
    assert "| m:1 |" in md and "syntax" in md
    assert len((tmp_path / "failure_labels.csv").read_text(encoding="utf-8-sig").splitlines()) == 3


def test_bench_refuses_when_frozen_file_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "changed", lambda: ["testset/questions.jsonl"])
    assert bench.main(["--out", str(tmp_path), "--models", "m:1"]) == 2
    assert "REFUSING" in (tmp_path / "log.txt").read_text()
