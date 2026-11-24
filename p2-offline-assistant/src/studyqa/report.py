"""Turn a bench run directory into report.md + questions.csv.

    uv run python -m studyqa.report runs/smoke_public [--tau-quote 0.9 --tau-answer 0.5]

Grounding is recomputed from the stored questions and the frozen section file
(hash-checked against meta.json), so metric fixes and threshold changes never
require re-running a model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

from evalkit import Result, compare, load_cases, load_results, to_markdown
from studyqa.grounding import ground
from studyqa.schema import QuestionSet

TAU_QUOTE_GRID = [0.8, 0.85, 0.9, 0.95, 1.0]
TAU_ANSWER_GRID = [0.3, 0.4, 0.5, 0.6, 0.7]


def _sections(run_dir: Path, meta: dict) -> dict[str, str]:
    path = Path(meta["cases_file"])
    if not path.is_absolute():
        path = run_dir.resolve().parents[1] / path  # bench runs from the project dir
    sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    if sha != meta["cases_sha256"]:
        raise ValueError(f"{path} changed since the run (sha {sha} != {meta['cases_sha256']})")
    return {c.id: c.input["text"] for c in load_cases(path)}


def load_run(run_dir: Path, *, reground: bool = True) -> dict[tuple[str, str, int], list[Result]]:
    """{(model_slug, mode, pass): results}, with grounding recomputed by the
    current metric unless reground=False."""
    runs = {}
    for f in sorted(run_dir.glob("*__*__p*.jsonl")):
        model, mode, p = f.stem.split("__")
        runs[(model, mode, int(p[1:]))] = load_results(f)
    if not runs:
        raise FileNotFoundError(f"no result files in {run_dir}")
    if reground:
        texts = _sections(run_dir, json.loads((run_dir / "meta.json").read_text()))
        for rs in runs.values():
            for r in rs:
                if r.output and r.output.get("questions"):
                    qs = QuestionSet.model_validate(r.output["questions"])
                    r.output["grounding"] = [g.model_dump() for g in ground(qs, texts[r.case_id])]
    return runs


def _grounding(rs: list[Result]) -> list[dict]:
    return [g for r in rs if r.output for g in r.output["grounding"]]


def _is_grounded(g: dict, tq: float, ta: float) -> bool:
    return g["quote_fidelity"] >= tq and g["answer_support"] >= ta


def grounded_rate(rs: list[Result], tq: float, ta: float, *, end_to_end: bool) -> float:
    """end_to_end: invalid outputs count as 5 ungrounded questions."""
    gs = _grounding(rs)
    hits = sum(_is_grounded(g, tq, ta) for g in gs)
    denom = 5 * len(rs) if end_to_end else len(gs)
    return hits / denom if denom else 0.0


def section_supported_rate(rs: list[Result], ta: float) -> float:
    """Among valid outputs: answer's content words found in the whole section."""
    gs = _grounding(rs)
    return sum(g["section_support"] >= ta for g in gs) / len(gs) if gs else 0.0


def wrong_quote_rate(rs: list[Result], tq: float, ta: float) -> float:
    """Among valid outputs: answer supported by the section but not quote-grounded."""
    gs = _grounding(rs)
    return (sum(g["section_support"] >= ta and not _is_grounded(g, tq, ta) for g in gs) / len(gs)
            if gs else 0.0)


def _tok_s(rs: list[Result]) -> list[float]:
    out = []
    for r in rs:
        for resp in (r.output or {}).get("responses", [])[:1]:
            if resp["eval_duration_s"]:
                out.append(resp["eval_count"] / resp["eval_duration_s"])
    return out


def _med(xs: list[float]) -> float:
    return statistics.median(xs) if xs else float("nan")


def failure_kind(r: Result) -> str | None:
    """None if valid. Otherwise: 'error' (HTTP error/timeout: no output at all),
    'runaway' (an attempt hit num_predict), or 'schema' (invalid, not truncated)."""
    if r.error:
        return "error"
    if r.output["valid"]:
        return None
    if any(resp.get("done_reason") == "length" for resp in r.output["responses"]):
        return "runaway"
    return "schema"


def _mem(meta: dict, model: str) -> dict:
    vals = [v for k, v in meta.get("memory", {}).items()
            if k.split("|")[0].replace(":", "-") == model]
    return vals[0] if vals else {}


def memory_table(runs, meta) -> str:
    """Per model (memory does not depend on decoding mode). MB above the idle
    ollama-server baseline. 'Loaded' (after warm-up) is the headline number."""
    cols = [("loaded_delta_mb", "loaded"), ("gen_peak_delta_mb", "generation peak"),
            ("load_peak_delta_mb", "load peak"), ("end_delta_mb", "end of run"),
            ("baseline_mb", "server baseline")]
    rows = ["MB of working set above the idle `ollama serve` baseline. *Loaded* = after "
            "warm-up (model ready); *load peak* includes the transient weight-repack copy.", "",
            "| model | " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for model in sorted({m for m, _, _ in runs}):
        mem = _mem(meta, model)
        rows.append(f"| {model} | " + " | ".join(str(mem.get(k, "n/a")) for k, _ in cols) + " |")
    return "\n".join(rows)


def reliability_table(runs, meta) -> str:
    rows = ["| model | mode | n | valid 1st try | valid | schema fail | runaway | infra error "
            "| mean retries | ctx overflow | tok/s p50 |",
            "|" + "---|" * 11]
    for (model, mode, p), rs in sorted(runs.items()):
        if p != 0:
            continue  # quality is deterministic (temp 0, fixed seed); pass 0 is canonical
        kinds = [failure_kind(r) for r in rs]
        all_tps = [t for (m2, mo2, _), rs2 in runs.items() if m2 == model and mo2 == mode
                   for t in _tok_s(rs2)]
        rows.append(
            f"| {model} | {mode} | {len(rs)} "
            f"| {statistics.fmean(r.scores['valid_first_try'] for r in rs):.2f} "
            f"| {statistics.fmean(r.scores['valid'] for r in rs):.2f} "
            f"| {kinds.count('schema')} | {kinds.count('runaway')} | {kinds.count('error')} "
            f"| {statistics.fmean(r.output['attempts'] - 1 for r in rs if r.output):.2f} "
            f"| {sum(bool(r.output and r.output['ctx_overflow']) for r in rs)} "
            f"| {_med(all_tps):.1f} |")
    return "\n".join(rows)


def groundedness_table(runs, tq, ta) -> str:
    rows = ["Grounded = quote_fidelity >= tau_quote and answer support vs the QUOTE >= "
            "tau_answer. Section-supported = answer support vs the whole SECTION >= tau_answer. "
            "Wrong quote = section-supported but not grounded. All but 'grounded (all)' "
            "are over questions from valid outputs.", "",
            "| model | mode | grounded (all) | grounded (valid only) | section-supported "
            "| wrong quote | quote fid. p50 | ans. support (quote) p50 "
            "| ans. support (section) p50 |",
            "|" + "---|" * 9]
    for (model, mode, p), rs in sorted(runs.items()):
        if p != 0:
            continue
        gs = _grounding(rs)
        rows.append(
            f"| {model} | {mode} "
            f"| {grounded_rate(rs, tq, ta, end_to_end=True):.2f} "
            f"| {grounded_rate(rs, tq, ta, end_to_end=False):.2f} "
            f"| {section_supported_rate(rs, ta):.2f} "
            f"| {wrong_quote_rate(rs, tq, ta):.2f} "
            f"| {_med([g['quote_fidelity'] for g in gs]):.2f} "
            f"| {_med([g['answer_support'] for g in gs]):.2f} "
            f"| {_med([g['section_support'] for g in gs]):.2f} |")
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


def _grid(runs, title: str, name: str, grid: list[float], fn) -> str:
    rows = [title, "", "| model | mode | " + " | ".join(f"{name}={x}" for x in grid) + " |",
            "|" + "---|" * (len(grid) + 2)]
    for k in sorted(k for k in runs if k[2] == 0):
        rows.append(f"| {k[0]} | {k[1]} | "
                    + " | ".join(f"{fn(runs[k], x):.2f}" for x in grid) + " |")
    return "\n".join(rows)


def sensitivity(runs, tq, ta) -> str:
    """All rates among questions from valid outputs."""
    return "\n\n".join([
        _grid(runs, f"Grounded rate vs tau_quote (tau_answer fixed at {ta}):", "tau_quote",
              TAU_QUOTE_GRID, lambda rs, x: grounded_rate(rs, x, ta, end_to_end=False)),
        _grid(runs, f"Grounded rate vs tau_answer (tau_quote fixed at {tq}):", "tau_answer",
              TAU_ANSWER_GRID, lambda rs, x: grounded_rate(rs, tq, x, end_to_end=False)),
        _grid(runs, "Section-supported rate vs tau_answer:", "tau_answer",
              TAU_ANSWER_GRID, section_supported_rate),
    ])


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


def report(run_dir: Path, tq: float, ta: float, *, reground: bool = True) -> str:
    runs = load_run(run_dir, reground=reground)
    meta = json.loads((run_dir / "meta.json").read_text())
    n_q = write_questions_csv(runs, run_dir / "questions.csv")
    md = "\n\n".join([
        f"# Report: {run_dir.name}",
        f"commit `{meta.get('git_commit')}`{' (dirty)' if meta.get('git_dirty') else ''}, "
        f"Ollama {meta.get('ollama_version')}, prompt {meta.get('prompt_version')}, "
        f"num_ctx {meta.get('num_ctx')}, retries {meta.get('retries')}, "
        f"passes {meta.get('passes')}, on battery: {meta.get('on_battery')}. "
        f"Thresholds: tau_quote={tq}, tau_answer={ta}. {n_q} questions in questions.csv.",
        f"num_predict {meta.get('num_predict')}.",
        "## Reliability", reliability_table(runs, meta),
        "## Groundedness", groundedness_table(runs, tq, ta),
        "## Memory", memory_table(runs, meta),
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
