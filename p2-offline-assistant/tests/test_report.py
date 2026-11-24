import json

from evalkit import Result, save_results
from studyqa.report import grounded_rate, report, rescore

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
        {"memory": {"m:3b|pass0": {"peak_delta_mb": 2100}}, "git_commit": "abc"}))
    md = report(tmp_path, 0.9, 0.5)
    assert "| m-3b | constrained | 10 | 1.00 | 1.00 | 0.00 | 1.00 |" in md
    assert "| 2100 |" in md and "15.0" in md  # RAM and tok/s columns
    assert "| grounded | 10 | 0.000 | 1.000 | +1.000 |" in md  # paired mode comparison
    assert (tmp_path / "questions.csv").read_text().count("\n") == 1 + 100
