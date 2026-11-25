import csv
import json

import pytest

from evalkit import Case, Result, save_results
from studyqa.grading import export, import_grades, spearman

Q = {"question": "q?", "answer": "a", "difficulty": "easy", "source_quote": "quote here"}


def _r(cid, valid):
    return Result(case_id=cid, latency_s=1, scores={"valid": float(valid)},
                  output={"questions": {"questions": [Q] * 5} if valid else None,
                          "grounding": [{"quote_fidelity": 1.0, "answer_support": 1.0,
                                         "section_support": 1.0}] * 5 if valid else []})


@pytest.fixture
def run_dir(tmp_path):
    run = tmp_path / "run"
    for model in ["a-3b", "b-3b"]:
        for mode in ["json", "constrained"]:
            # s0 invalid in json for every model: must never be sampled.
            rs = [_r(f"s{i}", not (i == 0 and mode == "json")) for i in range(6)]
            save_results(rs, run / f"{model}__{mode}__p0.jsonl")
    cases = tmp_path / "cases.jsonl"
    cases.write_text("".join(Case(id=f"s{i}", input={"title": f"T{i}", "text": "x"}
                                  ).model_dump_json() + "\n" for i in range(6)))
    return run, cases


def test_export_is_blind_paired_and_skips_invalid(run_dir, tmp_path):
    run, cases = run_dir
    out = tmp_path / "grading"
    export(run, cases, out, n=3, seed=0)
    rows = list(csv.DictReader(open(out / "to_grade.csv", encoding="utf-8")))
    key = list(csv.DictReader(open(out / "key.csv", encoding="utf-8")))
    assert len(rows) == 2 * 3 * 2  # models x sections x modes
    assert "model" not in rows[0] and "mode" not in rows[0]
    for model in ["a-3b", "b-3b"]:
        by_mode = {m: {k["section"] for k in key if k["model"] == model and k["mode"] == m}
                   for m in ["json", "constrained"]}
        assert by_mode["json"] == by_mode["constrained"]  # paired
        assert "s0" not in by_mode["json"]


def test_import_requires_all_grades_then_reports(run_dir, tmp_path):
    run, cases = run_dir
    out = tmp_path / "grading"
    export(run, cases, out, n=3, seed=0)
    rows = list(csv.DictReader(open(out / "to_grade.csv", encoding="utf-8")))
    with pytest.raises(ValueError, match="without a 1-3 grade"):
        import_grades(run, out, reground=False)
    key = {k["id"]: k for k in csv.DictReader(open(out / "key.csv", encoding="utf-8"))}
    for r in rows:
        r["grade"] = "3" if key[r["id"]]["mode"] == "constrained" else "1"
    with open(out / "to_grade.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    md = import_grades(run, out, reground=False)
    assert "| a-3b | constrained | 3 | 3.00 |" in md and "| a-3b | json | 3 | 1.00 |" in md
    assert "| human | 3 | 0.000 | 1.000 | +1.000 |" in md


def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) != spearman([1, 1, 1], [1, 2, 3])  # nan: no variance


def test_key_can_live_outside_the_grading_folder(run_dir, tmp_path):
    run, cases = run_dir
    out, key = tmp_path / "grading", tmp_path / "keys" / "key.csv"
    export(run, cases, out, n=3, seed=0, key_path=key)
    assert key.exists() and not (out / "key.csv").exists()
    rows = list(csv.DictReader(open(out / "to_grade.csv", encoding="utf-8")))
    for r in rows:
        r["grade"] = "2"
    with open(out / "to_grade.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert "| a-3b | json | 3 | 2.00 |" in import_grades(run, out, reground=False, key_path=key)
