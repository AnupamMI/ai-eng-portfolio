import hashlib
import json

import pytest

from evalkit import Case, Result, save_results
from studyqa.report import failure_kind, grounded_rate, load_run, report, rescore

Q = {"question": "q?", "answer": "a", "difficulty": "easy", "source_quote": "quote here"}


def _result(cid, valid, fids, sups, attempts=1):
    gs = [{"quote_fidelity": f, "answer_support": s, "section_support": s}
          for f, s in zip(fids, sups)] if valid else []
    return Result(case_id=cid, latency_s=1.0,
                  scores={"valid_first_try": float(valid and attempts == 1),
                          "valid": float(valid), "grounded": 0.0},
                  output={"valid": valid, "attempts": attempts, "ctx_overflow": False,
                          "questions": {"questions": [Q] * 5} if valid else None,
                          "grounding": gs,
                          "responses": [{"eval_count": 30, "eval_duration_s": 2.0}]})


def test_grounded_rate_end_to_end_counts_invalid_as_ungrounded():
    rs = [_result("a", True, [1, 1, 1, 0.5, 1], [1, 1, 0.2, 1, 1]),
          _result("b", False, [], [], attempts=3)]
    assert grounded_rate(rs, 0.9, 0.5, end_to_end=False) == 3 / 5
    assert grounded_rate(rs, 0.9, 0.5, end_to_end=True) == 3 / 10
    assert grounded_rate(rs, 0.4, 0.1, end_to_end=False) == 1.0
    assert rescore(rs, 0.9, 0.5)[0].scores["grounded"] == 0.6


def test_report_end_to_end(tmp_path):
    for mode, fid in [("json", 0.5), ("constrained", 1.0)]:
        rs = [_result(f"s{i}", True, [fid] * 5, [1] * 5) for i in range(10)]
        save_results(rs, tmp_path / f"m-3b__{mode}__p0.jsonl")
    (tmp_path / "meta.json").write_text(json.dumps(
        {"memory": {"m:3b|pass0": {"peak_delta_mb": 2100, "loaded_delta_mb": 1900,
                                   "baseline_mb": 50}}, "git_commit": "abc"}))
    md = report(tmp_path, 0.9, 0.5, reground=False)
    assert "| m-3b | constrained | 10 | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0.00 | 0 | 0 | 15.0 |" in md
    assert "| m-3b | constrained | 1.00 | 1.00 | 1.00 | 0.00 |" in md  # groundedness table
    assert "| m-3b | json | 0.00 | 0.00 | 1.00 | 1.00 |" in md  # all wrong-quote
    assert "|---|---|---|---|---|---|---|\n| m-3b" in md  # sensitivity tables well-formed
    assert "| grounded | 10 | 0.000 | 1.000 | +1.000 |" in md  # paired mode comparison
    assert "| m-3b | 1900 | n/a | n/a | n/a | 50 |" in md  # memory table
    assert (tmp_path / "questions.csv").read_text().count("\n") == 1 + 100


def test_reground_uses_current_metric_and_checks_hash(tmp_path):
    proj = tmp_path / "proj"
    run = proj / "runs" / "r"
    run.mkdir(parents=True)
    text = "A closure is a function bundled with references to its surrounding state."
    cases = proj / "data" / "c.jsonl"
    cases.parent.mkdir()
    cases.write_text(Case(id="s0", input={"text": text}).model_dump_json() + "\n")
    q = {**Q, "question": "What is a closure?", "answer": "function bundled with state",
         "source_quote": text}
    r = _result("s0", True, [0.0] * 5, [0.0] * 5)  # stale stored scores
    r.output["questions"] = {"questions": [q] * 5}
    save_results([r], run / "m-3b__json__p0.jsonl")
    sha = hashlib.sha256(cases.read_bytes()).hexdigest()[:16]
    (run / "meta.json").write_text(json.dumps({"cases_file": "data/c.jsonl",
                                               "cases_sha256": sha}))
    (r2,) = load_run(run)[("m-3b", "json", 0)]
    assert r2.output["grounding"][0]["quote_fidelity"] == 1.0
    cases.write_text(cases.read_text() + "\n")
    with pytest.raises(ValueError, match="changed since the run"):
        load_run(run)


def _run_dir(path, model, meta, results):
    path.mkdir(parents=True)
    for mode in ("json", "constrained"):
        save_results(results, path / f"{model}__{mode}__p0.jsonl")
    (path / "meta.json").write_text(json.dumps(meta))


def test_report_merges_sessions_and_keeps_their_provenance(tmp_path):
    proto = {"cases_sha256": "x", "num_predict": 1536}
    recovered = _result("s0", True, [1] * 5, [1] * 5, attempts=2)
    recovered.output["responses"] = [{"eval_count": 1536, "eval_duration_s": 9,
                                      "done_reason": "length"},
                                     {"eval_count": 300, "eval_duration_s": 9,
                                      "done_reason": "stop"}]
    _run_dir(tmp_path / "a", "m-3b", {**proto, "git_commit": "aaa", "system_ram_at_start_mb":
             {"used": 9000, "available": 6800},
             "memory": {"m:3b|pass0": {"loaded_delta_mb": 2000,
                                       "system_available_before_mb": 8800}}},
             [_result("s0", True, [1] * 5, [1] * 5)])
    _run_dir(tmp_path / "b", "p-3b", {**proto, "git_commit": "bbb", "system_ram_at_start_mb":
             {"used": 6500, "available": 9300},
             "memory": {"p:3b|pass0": {"loaded_delta_mb": 3600,
                                       "system_available_before_mb": 9284}}}, [recovered])
    md = report([tmp_path / "a", tmp_path / "b"], 0.85, 0.4, out_dir=tmp_path / "c",
                reground=False)
    assert "| m-3b | 2000 |" in md and "| p-3b | 3600 |" in md  # each model's own meta
    assert "| 9000 / 6800 | m:3b: 8800 |" in md and "| 6500 / 9300 | p:3b: 9284 |" in md
    # recovered runaway: valid, 1 section retried, 1 cap hit, not a failure
    assert "| p-3b | json | 1 | 0.00 | 1.00 | 0 | 0 | 0 | 1 | 1.00 | 1 |" in md
    assert (tmp_path / "c" / "report.md").exists()

    with pytest.raises(ValueError, match="more than one run dir"):
        report([tmp_path / "a", tmp_path / "a"], 0.85, 0.4, out_dir=tmp_path / "c",
               reground=False)
    _run_dir(tmp_path / "d", "q-3b", {**proto, "num_predict": 1024}, [recovered])
    with pytest.raises(ValueError, match="differ in num_predict"):
        report([tmp_path / "a", tmp_path / "d"], 0.85, 0.4, out_dir=tmp_path / "c",
               reground=False)


def test_failure_kinds():
    ok = _result("a", True, [1] * 5, [1] * 5)
    schema = _result("b", False, [], [], attempts=3)
    runaway = _result("c", False, [], [], attempts=3)
    runaway.output["responses"] = [{"eval_count": 1536, "eval_duration_s": 9,
                                    "done_reason": "length"}]
    err = Result(case_id="d", latency_s=600, error="ReadTimeout: timed out",
                 scores={"valid_first_try": 0, "valid": 0, "grounded": 0})
    assert [failure_kind(r) for r in (ok, schema, runaway, err)] == [
        None, "schema", "runaway", "error"]
