"""Turn a bench run directory into report.md + questions.csv.

    uv run python -m studyqa.report runs/smoke_public [--tau-quote 0.9 --tau-answer 0.5]

Everything is recomputed from raw per-question scores, so thresholds can be
changed here without re-running any model.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from evalkit import Result, compare, load_results, to_markdown

TAU_QUOTE_GRID = [0.8, 0.85, 0.9, 0.95, 1.0]
TAU_ANSWER_GRID = [0.3, 0.4, 0.5, 0.6, 0.7]


def load_run(run_dir: Path) -> dict[tuple[str, str, int], list[Result]]:
    """{(model_slug, mode, pass): results}"""
    runs = {}
    for f in sorted(run_dir.glob("*__*__p*.jsonl")):
        model, mode, p = f.stem.split("__")
        runs[(model, mode, int(p[1:]))] = load_results(f)
    if not runs:
        raise FileNotFoundError(f"no result files in {run_dir}")
    return runs


def _grounding(rs: list[Result]) -> list[dict]:
    return [g for r in rs if r.output for g in r.output["grounding"]]


def grounded_rate(rs: list[Result], tq: float, ta: float, *, end_to_end: bool) -> float:
    """end_to_end: invalid outputs count as 5 ungrounded questions."""
    gs = _grounding(rs)
    hits = sum(g["quote_fidelity"] >= tq and g["answer_support"] >= ta for g in gs)
    denom = 5 * len(rs) if end_to_end else len(gs)
    return hits / denom if denom else 0.0


def _tok_s(rs: list[Result]) -> list[float]:
    out = []
    for r in rs:
        for resp in (r.output or {}).get("responses", [])[:1]:
            if resp["eval_duration_s"]:
                out.append(resp["eval_count"] / resp["eval_duration_s"])
    return out


def _med(xs: list[float]) -> float:
    return statistics.median(xs) if xs else float("nan")


def summary_table(runs, meta, tq, ta) -> str:
    rows = ["| model | mode | n | valid 1st try | valid | mean retries | grounded (all) "
            "| grounded (valid only) | quote fid. p50 | ans. support p50 | tok/s p50 "
            "| peak RAM Δ MB | ctx overflow |",
            "|" + "---|" * 13]
    for (model, mode, p), rs in sorted(runs.items()):
        if p != 0:
            continue  # quality is deterministic (temp 0, fixed seed); pass 0 is canonical
        gs = _grounding(rs)
        all_tps = [t for (m2, mo2, _), rs2 in runs.items() if m2 == model and mo2 == mode
                   for t in _tok_s(rs2)]
        mem = [v["peak_delta_mb"] for k, v in meta.get("memory", {}).items()
               if k.split("|")[0].replace(":", "-") == model]
        rows.append(
            f"| {model} | {mode} | {len(rs)} "
            f"| {statistics.fmean(r.scores['valid_first_try'] for r in rs):.2f} "
            f"| {statistics.fmean(r.scores['valid'] for r in rs):.2f} "
            f"| {statistics.fmean(r.output['attempts'] - 1 for r in rs if r.output):.2f} "
            f"| {grounded_rate(rs, tq, ta, end_to_end=True):.2f} "
            f"| {grounded_rate(rs, tq, ta, end_to_end=False):.2f} "
            f"| {_med([g['quote_fidelity'] for g in gs]):.2f} "
            f"| {_med([g['answer_support'] for g in gs]):.2f} "
            f"| {_med(all_tps):.1f} "
            f"| {max(mem) if mem else 'n/a'} "
            f"| {sum(bool(r.output and r.output['ctx_overflow']) for r in rs)} |")
    return "\n".join(rows)


def rescore(rs: list[Result], tq: float, ta: float) -> list[Result]:
    """Recompute the per-section 'grounded' score at the given thresholds."""
    out = []
    for r in rs:
        gs = r.output["grounding"] if r.output else []
        g = (sum(x["quote_fidelity"] >= tq and x["answer_support"] >= ta for x in gs) / len(gs)
             if gs else 0.0)
        out.append(r.model_copy(update={"scores": {**r.scores, "grounded": g}}))
    return out


def mode_comparison(runs, tq, ta) -> str:
    parts = []
    models = sorted({m for m, _, _ in runs})
    for model in models:
        if (model, "json", 0) in runs and (model, "constrained", 0) in runs:
            d = compare(rescore(runs[(model, "json", 0)], tq, ta),
                        rescore(runs[(model, "constrained", 0)], tq, ta))
            parts.append(f"**{model}**: json (before) -> constrained (after)\n\n{to_markdown(d)}")
    return "\n\n".join(parts)


def sensitivity(runs, tq, ta) -> str:
    keys = sorted(k for k in runs if k[2] == 0)
    head = lambda name, grid: (f"| model | mode | " + " | ".join(f"{name}={x}" for x in grid)
                               + " |\n|" + "---|" * (len(grid) + 2))
    a = [head("tau_quote", TAU_QUOTE_GRID) + f"  (tau_answer={ta})"]
    b = [head("tau_answer", TAU_ANSWER_GRID) + f"  (tau_quote={tq})"]
    for k in keys:
        rs = runs[k]
        a.append(f"| {k[0]} | {k[1]} | " + " | ".join(
            f"{grounded_rate(rs, x, ta, end_to_end=False):.2f}" for x in TAU_QUOTE_GRID) + " |")
        b.append(f"| {k[0]} | {k[1]} | " + " | ".join(
            f"{grounded_rate(rs, tq, x, end_to_end=False):.2f}" for x in TAU_ANSWER_GRID) + " |")
    return "Grounded rate among valid outputs.\n\n" + "\n".join(a) + "\n\n" + "\n".join(b)


def write_questions_csv(runs, path: Path) -> int:
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "mode", "section", "q_idx", "quote_fidelity", "answer_support",
                    "section_support", "question", "answer", "source_quote"])
        for (model, mode, p), rs in sorted(runs.items()):
            if p != 0:
                continue
            for r in rs:
                if not (r.output and r.output["questions"]):
                    continue
                for i, (q, g) in enumerate(zip(r.output["questions"]["questions"],
                                               r.output["grounding"])):
                    w.writerow([model, mode, r.case_id, i, f"{g['quote_fidelity']:.3f}",
                                f"{g['answer_support']:.3f}", f"{g['section_support']:.3f}",
                                q["question"], q["answer"], q["source_quote"]])
                    n += 1
    return n


def report(run_dir: Path, tq: float, ta: float) -> str:
    runs = load_run(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text())
    n_q = write_questions_csv(runs, run_dir / "questions.csv")
    md = "\n\n".join([
        f"# Report: {run_dir.name}",
        f"commit `{meta.get('git_commit')}`{' (dirty)' if meta.get('git_dirty') else ''}, "
        f"Ollama {meta.get('ollama_version')}, prompt {meta.get('prompt_version')}, "
        f"num_ctx {meta.get('num_ctx')}, retries {meta.get('retries')}, "
        f"passes {meta.get('passes')}, on battery: {meta.get('on_battery')}. "
        f"Thresholds: tau_quote={tq}, tau_answer={ta}. {n_q} questions in questions.csv.",
        "## Summary", summary_table(runs, meta, tq, ta),
        "## Decoding mode, paired by section (95% bootstrap CI)", mode_comparison(runs, tq, ta),
        "## Threshold sensitivity", sensitivity(runs, tq, ta),
    ])
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--tau-quote", type=float, default=0.9)
    ap.add_argument("--tau-answer", type=float, default=0.5)
    a = ap.parse_args(argv)
    print(report(a.run_dir, a.tau_quote, a.tau_answer))


if __name__ == "__main__":
    main()
