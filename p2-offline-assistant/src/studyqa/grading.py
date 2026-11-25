"""Blind grading: export a shuffled sample, import grades, analyse.

    uv run python -m studyqa.grading export runs/full --cases data/full.jsonl --out grading/full
    # fill the `grade` column (1-3) in grading/full/to_grade.csv
    uv run python -m studyqa.grading import runs/full --grades grading/full --grader "hand-graded"
    # grades from another file / grader: --sheet grading/full/graded.csv --grader "LLM-graded (ChatGPT)"

Sampling: per model, N sections drawn (seeded) from those valid in BOTH modes, one
random question per (model, mode, section). The same sections are used for both
modes of a model, so constrained vs json is a paired comparison.

Rubric: 3 = correct, grounded in the section, tests understanding;
        2 = correct but shallow, or partly unsupported by the section;
        1 = wrong, ungrounded, or trivial.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
from collections import defaultdict
from pathlib import Path

from evalkit import Result, compare, load_cases, to_markdown
from studyqa.report import load_runs

MODES = ("json", "constrained")


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2  # average rank for ties
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(set(x)) < 2 or len(set(y)) < 2:
        return float("nan")
    return statistics.correlation(_ranks(x), _ranks(y))


def export(run_dirs: list[Path], cases_path: Path, out: Path, n: int, seed: int,
           key_path: Path | None = None) -> None:
    """key_path: where the model/mode key goes; default out/key.csv. Put it outside
    `out` so the grader never has it in the folder they work in."""
    key_path = key_path or out / "key.csv"
    runs, _ = load_runs(run_dirs, reground=False)  # sampling uses validity only
    sections = {c.id: c.input for c in load_cases(cases_path)}
    rng = random.Random(seed)
    rows = []
    for model in sorted({m for m, _, p in runs if p == 0}):
        by_mode = {mode: {r.case_id: r for r in runs[(model, mode, 0)]} for mode in MODES}
        ok = sorted(cid for cid in by_mode["json"]
                    if by_mode["json"][cid].scores["valid"]
                    and by_mode["constrained"].get(cid) and by_mode["constrained"][cid].scores["valid"])
        if len(ok) < n:
            print(f"WARNING: {model}: only {len(ok)} sections valid in both modes (< {n})")
        for cid in rng.sample(ok, min(n, len(ok))):
            for mode in MODES:
                r = by_mode[mode][cid]
                qi = rng.randrange(len(r.output["questions"]["questions"]))
                q = r.output["questions"]["questions"][qi]
                rows.append({"model": model, "mode": mode, "section": cid, "q_idx": qi,
                             "title": sections[cid]["title"], **q})
    rng.shuffle(rows)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "to_grade.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "section", "title", "question", "answer", "source_quote",
                    "grade", "notes"])
        for i, r in enumerate(rows, 1):
            w.writerow([f"g{i:03d}", r["section"], r["title"], r["question"], r["answer"],
                        r["source_quote"], "", ""])
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with open(key_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "model", "mode", "section", "q_idx"])
        for i, r in enumerate(rows, 1):
            w.writerow([f"g{i:03d}", r["model"], r["mode"], r["section"], r["q_idx"]])
    used = sorted({r["section"] for r in rows})
    (out / "sections.md").write_text("\n\n".join(
        f"## {cid}\n\n**{sections[cid]['title']}**\n\n{sections[cid]['text']}" for cid in used),
        encoding="utf-8")
    print(f"wrote {len(rows)} rows to {out / 'to_grade.csv'} "
          f"(key in {key_path}; don't open it until grading is done)")


def subsample(blank_sheet: Path, key_path: Path, cases_path: Path, out: Path,
              out_key: Path, *, sections_per_model: int = 5, seed: int = 1) -> None:
    """Draw a validation subset from an exported (BLANK) sheet: per model, N sections
    with BOTH modes (so the subset stays paired), re-IDed h01.. and reshuffled. Rows come
    from the blank export, so no earlier grader's grades or notes can leak in. The new
    key has the same columns as export's plus `source_id`, so import works unchanged."""
    with open(blank_sheet, encoding="utf-8-sig") as f:
        sheet = {r["id"]: r for r in csv.DictReader(f)}
    with open(key_path, encoding="utf-8-sig") as f:
        key = list(csv.DictReader(f))
    by_cell = {(k["model"], k["section"], k["mode"]): k for k in key}
    rng = random.Random(seed)
    picked = []
    for model in sorted({k["model"] for k in key}):
        secs = sorted({k["section"] for k in key if k["model"] == model
                       and all((model, k["section"], m) in by_cell for m in MODES)})
        for s in rng.sample(secs, sections_per_model):
            picked += [by_cell[(model, s, m)] for m in MODES]
    rng.shuffle(picked)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "to_grade.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "section", "title", "question", "answer", "source_quote",
                    "grade", "notes"])
        for i, k in enumerate(picked, 1):
            r = sheet[k["id"]]
            w.writerow([f"h{i:02d}", r["section"], r["title"], r["question"], r["answer"],
                        r["source_quote"], "", ""])
    out_key.parent.mkdir(parents=True, exist_ok=True)
    with open(out_key, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "model", "mode", "section", "q_idx", "source_id"])
        for i, k in enumerate(picked, 1):
            w.writerow([f"h{i:02d}", k["model"], k["mode"], k["section"], k["q_idx"], k["id"]])
    sections = {c.id: c.input for c in load_cases(cases_path)}
    used = sorted({k["section"] for k in picked})
    (out / "sections.md").write_text("\n\n".join(
        f"## {cid}\n\n**{sections[cid]['title']}**\n\n{sections[cid]['text']}" for cid in used),
        encoding="utf-8")
    print(f"wrote {len(picked)} rows ({len(used)} sections) to {out / 'to_grade.csv'} "
          f"(key in {out_key}; don't open it until grading is done)")


def agree(sheet_a: Path, key_a: Path, sheet_b: Path, *, label_a: str, label_b: str) -> str:
    """Row-by-row agreement between a subsample's grades (A, keyed via `source_id`
    in its key) and the grades of the sheet it was drawn from (B)."""
    from evalkit import confusion, exact_agreement, weighted_kappa

    def grades(p: Path) -> dict[str, int]:
        with open(p, encoding="utf-8-sig") as f:
            return {r["id"]: int(r["grade"]) for r in csv.DictReader(f)}

    ga, gb = grades(sheet_a), grades(sheet_b)
    with open(key_a, encoding="utf-8-sig") as f:
        key = {r["id"]: r for r in csv.DictReader(f)}
    ids = sorted(ga)
    a = [ga[i] for i in ids]
    b = [gb[key[i]["source_id"]] for i in ids]
    labels = [1, 2, 3]
    m = confusion(a, b, labels)
    dist = lambda xs: " / ".join(str(xs.count(v)) for v in labels)
    lines = [f"# Agreement: {label_a} vs {label_b}", "",
             f"{len(ids)} rows, matched by `source_id`. Grades 1-3.", "",
             "| statistic | value |", "|---|---|",
             f"| Spearman rho | {spearman([float(x) for x in a], [float(x) for x in b]):.2f} |",
             f"| exact agreement | {exact_agreement(a, b):.2f} ({sum(x == y for x, y in zip(a, b))}"
             f"/{len(a)}) |",
             f"| weighted kappa, quadratic | {weighted_kappa(a, b, labels):.2f} |",
             f"| weighted kappa, linear | {weighted_kappa(a, b, labels, weights='linear'):.2f} |",
             f"| mean grade {label_a} | {statistics.fmean(a):.2f} |",
             f"| mean grade {label_b} | {statistics.fmean(b):.2f} |",
             f"| grade counts 1 / 2 / 3, {label_a} | {dist(a)} |",
             f"| grade counts 1 / 2 / 3, {label_b} | {dist(b)} |", "",
             f"Confusion (rows: {label_a}, columns: {label_b}):", "",
             "| | " + " | ".join(f"{label_b} {v}" for v in labels) + " | total |",
             "|---|" + "---|" * (len(labels) + 1)]
    for v, row in zip(labels, m):
        lines.append(f"| {label_a} {v} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    lines.append("| total | " + " | ".join(str(sum(r[j] for r in m)) for j in range(len(labels)))
                 + f" | {len(a)} |")
    return "\n".join(lines)


def import_grades(run_dirs: list[Path], grades_dir: Path, *, grader: str, reground: bool = True,
                  key_path: Path | None = None, sheet: Path | None = None) -> str:
    """`grader` labels who produced the grades (e.g. "hand-graded", "LLM-graded (ChatGPT)") in the
    report and its filename; required so provenance cannot be dropped. `sheet`
    defaults to grades_dir/to_grade.csv; the blank export is never written."""
    sheet = sheet or grades_dir / "to_grade.csv"
    slug = "".join(c if c.isalnum() else "_" for c in grader.lower()).strip("_")
    runs, _ = load_runs(run_dirs, reground=reground)
    with open(key_path or grades_dir / "key.csv", encoding="utf-8-sig") as f:
        key = {r["id"]: r for r in csv.DictReader(f)}
    with open(sheet, encoding="utf-8-sig") as f:
        graded = list(csv.DictReader(f))
    missing = [g["id"] for g in graded if g["grade"].strip() not in {"1", "2", "3"}]
    if missing:
        raise ValueError(f"{len(missing)} rows without a 1-3 grade, e.g. {missing[:5]}")

    # Per (model, mode): Results keyed by section with the grade as a score.
    cells: dict[tuple[str, str], list[Result]] = defaultdict(list)
    pairs = []  # (grade, quote_fidelity, answer_support, grounded@0.85/0.4)
    for g in graded:
        k = key[g["id"]]
        grade = int(g["grade"])
        cells[(k["model"], k["mode"])].append(
            Result(case_id=k["section"], latency_s=0, scores={"grade": (grade - 1) / 2}))
        r = next(x for x in runs[(k["model"], k["mode"], 0)] if x.case_id == k["section"])
        gr = r.output["grounding"][int(k["q_idx"])]
        pairs.append((grade, gr["quote_fidelity"], gr["answer_support"],
                      float(gr["quote_fidelity"] >= 0.85 and gr["answer_support"] >= 0.4)))

    lines = [f"# Grades: {grader}", f"Source sheet: `{sheet.name}`. Grades: **{grader}**.",
             "Grade scaled to [0, 1] for the paired comparison: (grade - 1) / 2.", "",
             "| model | mode | n | mean grade (1-3) |", "|---|---|---|---|"]
    for (model, mode), rs in sorted(cells.items()):
        lines.append(f"| {model} | {mode} | {len(rs)} | "
                     f"{1 + 2 * statistics.fmean(r.scores['grade'] for r in rs):.2f} |")
    lines += ["", "## json (before) -> constrained (after), paired by section"]
    for model in sorted({m for m, _ in cells}):
        if (model, "json") in cells and (model, "constrained") in cells:
            d = compare(cells[(model, "json")], cells[(model, "constrained")])
            lines += ["", f"**{model}**", "", to_markdown(d)]
    hg = [p[0] for p in pairs]
    lines += ["", f"## Does the lexical metric track the grades ({grader})? (Spearman, all graded rows)",
              "", "| metric | rho |", "|---|---|"]
    for name, i in [("quote_fidelity", 1), ("answer_support", 2), ("grounded@0.85/0.4", 3)]:
        lines.append(f"| {name} | {spearman(hg, [p[i] for p in pairs]):.2f} |")
    md = "\n".join(lines)
    (grades_dir / f"grades_report_{slug}.md").write_text(md, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("run_dirs", type=Path, nargs="+")
    e.add_argument("--cases", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--n", type=int, default=20, help="sections per model (x2 modes)")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--key", type=Path, help="key file path (default: OUT/key.csv)")
    i = sub.add_parser("import")
    i.add_argument("run_dirs", type=Path, nargs="+")
    i.add_argument("--grades", type=Path, required=True)
    i.add_argument("--key", type=Path, help="key file path (default: GRADES/key.csv)")
    i.add_argument("--sheet", type=Path, help="graded CSV (default: GRADES/to_grade.csv)")
    i.add_argument("--grader", required=True, help='label for who graded, e.g. "hand-graded" or "LLM-graded (ChatGPT)"')
    s = sub.add_parser("subsample", help="validation subset from a blank exported sheet")
    s.add_argument("--from", dest="src", type=Path, required=True,
                   help="folder of the original export (its blank to_grade.csv)")
    s.add_argument("--cases", type=Path, required=True)
    s.add_argument("--key", type=Path, required=True, help="the original export's key")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--out-key", type=Path, required=True)
    s.add_argument("--sections-per-model", type=int, default=5, help="x2 modes per model")
    s.add_argument("--seed", type=int, default=1)
    g = sub.add_parser("agree", help="row-by-row agreement of a subsample with its source sheet")
    g.add_argument("--sheet", type=Path, required=True, help="graded subsample sheet")
    g.add_argument("--key", type=Path, required=True, help="subsample key (has source_id)")
    g.add_argument("--source-sheet", type=Path, required=True, help="graded source sheet")
    g.add_argument("--label", required=True)
    g.add_argument("--source-label", required=True)
    g.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "agree":
        md = agree(a.sheet, a.key, a.source_sheet, label_a=a.label, label_b=a.source_label)
        a.out.write_text(md, encoding="utf-8")
        print(md)
    elif a.cmd == "subsample":
        subsample(a.src / "to_grade.csv", a.key, a.cases, a.out, a.out_key,
                  sections_per_model=a.sections_per_model, seed=a.seed)
    elif a.cmd == "export":
        export(a.run_dirs, a.cases, a.out, a.n, a.seed, key_path=a.key)
    else:
        print(import_grades(a.run_dirs, a.grades, grader=a.grader, key_path=a.key, sheet=a.sheet))


if __name__ == "__main__":
    main()
