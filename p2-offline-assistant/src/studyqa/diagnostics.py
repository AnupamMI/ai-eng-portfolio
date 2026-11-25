"""Copy diagnostic: do near-verbatim answers explain why groundedness and grades disagree?

    uv run python -m studyqa.diagnostics runs/notes_full runs/notes_full_phi3 \
        --cases data/notes_full.jsonl --sheet grading/notes_full/graded_to_grade.csv \
        --key grading/_keys/notes_full_key.csv --grader "LLM-graded (ChatGPT)" \
        --out grading/notes_full/copy_diagnostic.md

Hypothesis (written before computing): the lexical metric rewards answers that copy
the quote/section, while the rubric's 3 requires an answer that "tests understanding",
so copying raises groundedness and lowers grades.

Definition (fixed in advance, reusing the frozen tau_quote, no tuning): an answer is a
*copy* if it has >= MIN_TOKENS tokens and its best-window match against the quote OR
the section is >= COPY_TAU (grounding.quote_fidelity with the answer as the 'quote').
Shorter answers are never copies (a 3-word term found in the text is not copying).
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

from evalkit import bootstrap_diff, load_cases
from studyqa.grounding import quote_fidelity, tokens
from studyqa.report import load_runs

COPY_TAU = 0.85  # = frozen TAU_QUOTE
MIN_TOKENS = 6
TQ, TA = 0.85, 0.4


def is_copy(answer: str, quote: str, section: str) -> bool:
    if len(tokens(answer)) < MIN_TOKENS:
        return False
    return max(quote_fidelity(answer, quote), quote_fidelity(answer, section)) >= COPY_TAU


def _fmt_ci(groups: tuple[list[float], list[float]]) -> str:
    copies, others = groups
    if not copies or not others:
        return "n/a (a group is empty)"
    d, lo, hi = bootstrap_diff(copies, others)
    return f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]{' *' if lo > 0 or hi < 0 else ''}"


def copy_diagnostic(run_dirs: list[Path], cases: Path, sheet: Path, key: Path,
                    grader: str) -> str:
    texts = {c.id: c.input["text"] for c in load_cases(cases)}
    runs, _ = load_runs(run_dirs, reground=True)

    # All valid questions in the full run (both modes): copy share and its link to groundedness.
    full = defaultdict(lambda: {"n": 0, "copy": 0, "g_copy": [], "g_other": []})
    for (model, _mode, p), rs in runs.items():
        if p != 0:
            continue
        for r in rs:
            if not (r.output and r.output.get("questions")):
                continue
            for q, g in zip(r.output["questions"]["questions"], r.output["grounding"]):
                c = is_copy(q["answer"], q["source_quote"], texts[r.case_id])
                grounded = float(g["quote_fidelity"] >= TQ and g["answer_support"] >= TA)
                s = full[model]
                s["n"] += 1
                s["copy"] += c
                (s["g_copy"] if c else s["g_other"]).append(grounded)

    # Graded rows: copy flag vs grade, within each model.
    with open(key, encoding="utf-8-sig") as f:
        k = {r["id"]: r for r in csv.DictReader(f)}
    with open(sheet, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    graded = defaultdict(lambda: ([], []))  # model -> (grades of copies, grades of others)
    for r in rows:
        m = k[r["id"]]["model"]
        c = is_copy(r["answer"], r["source_quote"], texts[r["section"]])
        graded[m][0 if c else 1].append(float(r["grade"]))
    pooled = ([g for v in graded.values() for g in v[0]], [g for v in graded.values() for g in v[1]])

    out = [
        f"# Copy diagnostic ({grader})", "",
        f"Copy = answer >= {MIN_TOKENS} tokens with best-window match >= {COPY_TAU} against the "
        "quote or the section. Defined before computing; see module docstring.", "",
        "Predictions: **P1** models with a higher copy share have a lower mean grade; "
        "**P2** within a model, copied answers get lower grades than non-copied ones "
        "(CI of non-copy minus copy above 0); **P3** copied answers are grounded more often "
        "than non-copied ones (the mechanism by which copying would inflate groundedness).", "",
        "## All valid questions, full run (both modes)", "",
        f"| model | questions | copy share | grounded@{TQ}/{TA}: copies | non-copies "
        "| P3: non-copy minus copy, 95% CI |",
        "|---|---|---|---|---|---|"]
    for m, s in sorted(full.items()):
        out.append(f"| {m} | {s['n']} | {s['copy'] / s['n']:.2f} "
                   f"| {statistics.fmean(s['g_copy']) if s['g_copy'] else float('nan'):.2f} "
                   f"| {statistics.fmean(s['g_other']) if s['g_other'] else float('nan'):.2f} "
                   f"| {_fmt_ci((s['g_copy'], s['g_other']))} |")
    out += ["", f"## Graded rows ({grader})", "",
            "| model | graded | copy share | mean grade | grade: copies (n) | non-copies (n) "
            "| P2: non-copy minus copy, 95% CI |",
            "|---|---|---|---|---|---|---|"]
    for m, (cp, ot) in sorted(graded.items()):
        allg = cp + ot
        out.append(f"| {m} | {len(allg)} | {len(cp) / len(allg):.2f} | {statistics.fmean(allg):.2f} "
                   f"| {statistics.fmean(cp) if cp else float('nan'):.2f} ({len(cp)}) "
                   f"| {statistics.fmean(ot) if ot else float('nan'):.2f} ({len(ot)}) "
                   f"| {_fmt_ci((cp, ot))} |")
    cp, ot = pooled
    out.append(f"| all (pooled) | {len(cp) + len(ot)} | {len(cp) / (len(cp) + len(ot)):.2f} "
               f"| {statistics.fmean(cp + ot):.2f} "
               f"| {statistics.fmean(cp) if cp else float('nan'):.2f} ({len(cp)}) "
               f"| {statistics.fmean(ot) if ot else float('nan'):.2f} ({len(ot)}) "
               f"| {_fmt_ci(pooled)} |")
    out += ["", "`*` = 95% CI excludes 0. Unpaired bootstrap (evalkit.bootstrap_diff); "
            "uncorrected for the number of comparisons. P1 has only 3 points (one per model) "
            "and is descriptive: compare the ordering of the copy-share and mean-grade columns. "
            "Model-vs-model rows are confounded by section (each model was graded on its own "
            "sample); P2 is within model, so it is not."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", type=Path, nargs="+")
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--sheet", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--grader", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    md = copy_diagnostic(a.run_dirs, a.cases, a.sheet, a.key, a.grader)
    a.out.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
